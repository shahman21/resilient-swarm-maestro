"""Resilient Swarm Maestro hub.

  Ultraleap -> bpm/rule -> ~45-byte UDP rule packet -> mBot2 (:5005)
                         -> WebSocket state          -> dashboard (/ws)
  mBot2 status (:5006)   -> forwarded to dashboard as `robot`

Run:  uvicorn server:app --host 0.0.0.0 --port 8000
"""

import asyncio
import json
import os
import random
import socket
import time
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

from ai_services import GeminiComposer, TelemetryStore, VoiceAnnouncer  # noqa: E402
from leap_tracker import LeapTracker, hand_y_to_bpm  # noqa: E402

MBOT_IP = os.getenv("MBOT_IP", "172.20.10.5")
UDP_PORT = int(os.getenv("UDP_PORT", "5005"))
STATUS_PORT = int(os.getenv("STATUS_PORT", "5006"))
HEARTBEAT_S = int(os.getenv("HEARTBEAT_MS", "150")) / 1000.0
RULES = ("pulse", "orbit", "figure8")


class Hub:
    def __init__(self):
        # shared rule state (contract 5A)
        self.seq = 0
        self.step = 0
        self.bpm = 120
        self.rule = "orbit"
        self.notes = [60, 64, 67, 72]
        self.ai_rule = None  # Gemini's rule suggestion for this phrase
        # judge controls (contract 5B)
        self.packet_loss_pct = 0
        self.blackout = False
        self.override_rule = None
        # bookkeeping
        self.packet = b""
        self.beat_started = time.monotonic()
        self.this_beat_delivered = False
        self.delivered_window = deque(maxlen=20)
        self.last_delivered = None  # dict(seq, step, bpm, rule, t)
        self.sends = deque(maxlen=200)  # monotonic timestamps of send attempts
        self.telemetry_history = deque(maxlen=60)
        self.robot = None  # latest status from the mBot2
        self.robot_seen = 0.0
        self.clients: set[WebSocket] = set()
        self._prev_hand_y = 0.5
        self._prev_hand_t = time.monotonic()
        self.hand_velocity = 0.0
        self._was_lossy = False
        self._was_blackout = False

        self.leap = LeapTracker()
        self.composer = GeminiComposer()
        self.voice = VoiceAnnouncer()
        self.store = TelemetryStore()

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.sock.setblocking(False)

    # ---- packet path -------------------------------------------------
    def _send(self):
        """One send attempt through the packet-loss injector."""
        self.sends.append(time.monotonic())
        if self.blackout or random.random() * 100 < self.packet_loss_pct:
            return False
        try:
            self.sock.sendto(self.packet, (MBOT_IP, UDP_PORT))
        except OSError:
            pass  # hotspot down / no route: same as a dropped packet from the robot's view
        if not self.last_delivered or self.last_delivered["seq"] != self.seq:
            self.last_delivered = {
                "seq": self.seq, "step": self.step, "bpm": self.bpm,
                "rule": self.rule, "t": time.monotonic(),
            }
        self.this_beat_delivered = True
        return True

    def _new_beat(self):
        if self.seq > 0:
            self.delivered_window.append(self.this_beat_delivered)
        self.seq += 1
        self.step += 1
        self.this_beat_delivered = False
        self._update_controls()
        self.packet = json.dumps(self.packet_dict(), separators=(",", ":")).encode()
        self.beat_started = time.monotonic()
        delivered = self._send()
        asyncio.create_task(self.push())  # dashboard hears the beat now, not on the next 10 Hz tick
        snap = self.leap.snapshot()
        self.store.record((
            self.seq, self.step, self.bpm, self.rule, int(self.packet_loss_pct), self.blackout,
            delivered, int(round(self.phase_drift())), snap["hand_detected"], snap["hand_y"],
            (self.robot or {}).get("mode"),
        ))

    def _update_controls(self):
        snap = self.leap.snapshot()
        now = time.monotonic()
        dt = max(1e-3, now - self._prev_hand_t)
        self.hand_velocity = (snap["hand_y"] - self._prev_hand_y) / dt
        self._prev_hand_y, self._prev_hand_t = snap["hand_y"], now
        if snap["hand_detected"]:
            self.bpm = hand_y_to_bpm(snap["hand_y"])
        if self.step % 8 == 0:
            # phrase boundary: swap in the phrase Gemini prepared, then ask for the next one
            phrase = self.composer.take_pending()
            if phrase:
                self.notes = phrase["notes"]
                self.ai_rule = phrase.get("rule")
            self.composer.request(self.rule, self.bpm, snap["hand_y"], self.hand_velocity,
                                  snap["hand_spread"])
        new_rule = self.override_rule or snap["gesture_rule"] or self.ai_rule or self.rule
        if new_rule != self.rule:
            self.rule = new_rule
            self.voice.say(f"Switching to {'figure eight' if new_rule == 'figure8' else new_rule}")

    async def beat_loop(self):
        next_beat = time.monotonic()
        next_hb = next_beat + HEARTBEAT_S
        while True:
            now = time.monotonic()
            if now >= next_beat:
                self._new_beat()
                next_beat += 60.0 / self.bpm
                if next_beat < now:  # fell behind (laptop slept etc.)
                    next_beat = now + 60.0 / self.bpm
                next_hb = now + HEARTBEAT_S
            elif now >= next_hb:
                self._send()  # heartbeat repeat of the same packet (same seq)
                next_hb = now + HEARTBEAT_S
            await asyncio.sleep(max(0.001, min(next_beat, next_hb) - time.monotonic()))

    def packet_dict(self) -> dict:
        """Contract 5A. The exact object the robot gets; the dashboard gets the same fields."""
        return {
            "seq": self.seq, "step": self.step, "bpm": self.bpm, "rule": self.rule,
            "notes": self.notes, "loss_pct": int(self.packet_loss_pct), "blackout": self.blackout,
        }

    async def push(self):
        if not self.clients:
            return
        msg = json.dumps(self.state())
        dead = []
        for ws in list(self.clients):
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)

    # ---- derived metrics ---------------------------------------------
    def robot_fresh(self):
        return self.robot is not None and time.monotonic() - self.robot_seen < 1.5

    def phase_drift(self) -> float:
        """Beats between the true swarm phase and where the physical robot is (or should be)."""
        now = time.monotonic()
        true_phase = self.step + (now - self.beat_started) * self.bpm / 60.0
        if self.robot_fresh():
            return max(0.0, abs(self.step - self.robot["step"]))
        ld = self.last_delivered
        if not ld:
            return 0.0
        est = ld["step"] + (now - ld["t"]) * ld["bpm"] / 60.0
        return abs(true_phase - est)

    def delivery_pct(self) -> int:
        if not self.delivered_window:
            return 100
        return int(round(100 * sum(self.delivered_window) / len(self.delivered_window)))

    def check_transitions(self):
        lossy = self.packet_loss_pct >= 50
        if self.blackout and not self._was_blackout:
            self.voice.say("Blackout. Autonomy engaged.")
        elif lossy and not self._was_lossy and not self.blackout:
            self.voice.say("Packet loss detected. Robots running on shared rules.")
        elif (self._was_blackout and not self.blackout) or (self._was_lossy and not lossy):
            if not self.blackout and not lossy:
                self.voice.say("Swarm resynchronized.")
        self._was_lossy, self._was_blackout = lossy, self.blackout

    def state(self) -> dict:
        snap = self.leap.snapshot()
        now = time.monotonic()
        ld = self.last_delivered
        recent_sends = sum(1 for t in self.sends if now - t < 1.0)
        return {
            # contract 5A fields, then 5B
            **self.packet_dict(),
            "packet_loss_pct": self.packet_loss_pct,
            "blackout": self.blackout,
            "packet_bytes": len(self.packet),
            "hand_detected": snap["hand_detected"],
            "hand_y": snap["hand_y"],
            "hand_spread": snap["hand_spread"],
            "ai_commentary": self.composer.current.get("commentary", ""),
            "telemetry_history": list(self.telemetry_history),
            # extensions (CLAUDE.md section 8)
            "last_delivered": None if not ld else {
                "seq": ld["seq"], "step": ld["step"], "bpm": ld["bpm"], "rule": ld["rule"],
                "age_ms": int((now - ld["t"]) * 1000),
            },
            "robot": None if not self.robot else {
                **self.robot, "age_ms": int((now - self.robot_seen) * 1000),
            },
            "music": {k: self.composer.current[k] for k in ("key", "scale", "chords")},
            "hand_source": snap["source"],
            "override_rule": self.override_rule,
            "sends_per_sec": recent_sends,
            "beat_phase": round(min(1.0, (now - self.beat_started) * self.bpm / 60.0), 3),
            "gemini": self.composer.enabled,
        }

    async def broadcast_loop(self):
        last_hist = 0.0
        while True:
            now = time.time()
            if now - last_hist >= 1.0:
                last_hist = now
                self.telemetry_history.append({
                    "t": datetime.now().strftime("%H:%M:%S"),
                    "delivery_pct": self.delivery_pct(),
                    "phase_drift": round(self.phase_drift(), 2),
                })
            self.check_transitions()
            await self.push()
            await asyncio.sleep(0.1)

    def apply_controls(self, data: dict):
        if "packet_loss_pct" in data:
            self.packet_loss_pct = max(0, min(100, int(data["packet_loss_pct"])))
        if "blackout" in data:
            self.blackout = bool(data["blackout"])
        if "override_rule" in data:
            r = data["override_rule"]
            self.override_rule = r if r in RULES else None

    def on_robot_status(self, data: bytes, addr):
        try:
            msg = json.loads(data.decode())
        except Exception:
            return
        if isinstance(msg, dict) and "step" in msg:
            self.robot = {
                "id": msg.get("id", "mbot2"), "seq": int(msg.get("seq", 0)),
                "step": int(msg.get("step", 0)), "missed": int(msg.get("missed", 0)),
                "mode": msg.get("mode", "synced"), "ip": addr[0],
            }
            self.robot_seen = time.monotonic()


hub = Hub()


class _StatusProtocol(asyncio.DatagramProtocol):
    def datagram_received(self, data, addr):
        hub.on_robot_status(data, addr)


@asynccontextmanager
async def lifespan(app: FastAPI):
    hub.leap.start()
    await hub.store.start()
    loop = asyncio.get_running_loop()
    transport, _ = await loop.create_datagram_endpoint(
        _StatusProtocol, local_addr=("0.0.0.0", STATUS_PORT)
    )
    tasks = [asyncio.create_task(hub.beat_loop()), asyncio.create_task(hub.broadcast_loop())]
    print(f"[hub] sending rule packets to {MBOT_IP}:{UDP_PORT}, robot status on :{STATUS_PORT}")
    print(f"[hub] Gemini {'on' if hub.composer.enabled else 'off (fallback chords)'}, "
          f"ElevenLabs {'on' if hub.voice.key else 'off'}")
    yield
    for t in tasks:
        t.cancel()
    transport.close()
    hub.leap.stop()


app = FastAPI(title="Resilient Swarm Maestro hub", lifespan=lifespan)


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    hub.clients.add(ws)
    try:
        await ws.send_text(json.dumps(hub.state()))
        while True:
            text = await ws.receive_text()
            try:
                hub.apply_controls(json.loads(text))
            except (ValueError, TypeError):
                pass
    except WebSocketDisconnect:
        pass
    finally:
        hub.clients.discard(ws)


@app.get("/api/state")
def get_state():
    return hub.state()


app.mount("/", StaticFiles(directory=ROOT / "dashboard", html=True), name="dashboard")
