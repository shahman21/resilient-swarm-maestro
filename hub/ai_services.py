"""Gemini (music + commentary), ElevenLabs (voice callouts), Tiger Data (telemetry).

Every service is optional. Missing keys or network errors fall back quietly so
the demo never stops because an API is down.
"""

import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import httpx

# ---------------------------------------------------------------------------
# Gemini: every 8 beats, gesture dynamics -> next 4-note phrase + rule
# ---------------------------------------------------------------------------

RULES = ("pulse", "orbit", "figure8")
# Fast "lite" models first: a phrase is only 8 beats (3 to 6 s), so latency matters most.
GEMINI_MODELS = ("gemini-3.5-flash-lite", "gemini-flash-lite-latest", "gemini-3.8-flash")
SEMITONE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

FALLBACK_MUSIC = {
    "pulse": {"key": "A", "scale": "minor", "chords": ["Am", "F", "C", "G"]},
    "orbit": {"key": "C", "scale": "major", "chords": ["C", "Am", "F", "G"]},
    "figure8": {"key": "D", "scale": "dorian", "chords": ["Dm", "G", "Em", "A"]},
}


def chord_to_notes(name: str, base: int = 60) -> list[int]:
    """'Am' -> [69, 72, 76, 81]: root, third, fifth, octave as MIDI numbers near middle C."""
    name = name or "C"
    root = base + SEMITONE.get(name[0].upper(), 0)
    rest = name[1:]
    if rest[:1] == "#":
        root, rest = root + 1, rest[1:]
    elif rest[:1] == "b":
        root, rest = root - 1, rest[1:]
    if rest.startswith("dim"):
        third, fifth = 3, 6
    elif rest.startswith("m") and not rest.startswith("maj"):
        third, fifth = 3, 7
    else:
        third, fifth = 4, 7
    if root >= base + 8:  # keep phrases in a comfortable buzzer range
        root -= 12
    return [root, root + third, root + fifth, root + 12]


def clean_notes(raw) -> list[int] | None:
    try:
        notes = [int(n) for n in raw][:4]
    except (TypeError, ValueError):
        return None
    if len(notes) != 4:
        return None
    return [max(48, min(84, n)) for n in notes]


class GeminiComposer:
    """Call request() on every 8-beat boundary. The answer is held in `pending` and the
    hub swaps it in on the *next* boundary, so phrases always change on step % 8 == 0."""

    def __init__(self):
        self.key = os.getenv("GEMINI_API_KEY", "")
        if self.key.startswith("your_"):
            self.key = ""
        # First entry is tried first. A model that answers 404 (retired / not on this key)
        # is dropped for the rest of the run and the next one takes over.
        first = os.getenv("GEMINI_MODEL", "") or GEMINI_MODELS[0]
        self.models = [first] + [m for m in GEMINI_MODELS if m != first]
        self._busy = False
        self._phrase = 0
        self.live = False  # True once a real Gemini answer has been accepted
        m = FALLBACK_MUSIC["orbit"]
        self.current = {**m, "notes": chord_to_notes(m["chords"][0]), "rule": None,
                        "commentary": "Swarm orbiting in C major"}
        self.pending = None

    @property
    def enabled(self) -> bool:
        return bool(self.key)

    @property
    def model(self) -> str:
        return self.models[0]

    async def _generate(self, body: dict) -> dict:
        async with httpx.AsyncClient(timeout=6) as client:
            while True:
                r = await client.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
                    json=body, headers={"x-goog-api-key": self.key},
                )
                if r.status_code == 404 and len(self.models) > 1:
                    print(f"[gemini] model {self.models.pop(0)} not available, trying {self.model}")
                    continue
                if r.status_code >= 400:
                    # never echo the request (it carries the key); status + model is enough
                    raise RuntimeError(f"HTTP {r.status_code} from {self.model}")
                return json.loads(r.json()["candidates"][0]["content"]["parts"][0]["text"])

    def take_pending(self):
        """Hub calls this on the 8-beat boundary. Returns the new phrase or None."""
        p, self.pending = self.pending, None
        if p:
            self.current = p
        return p

    def request(self, rule: str, bpm: int, hand_y: float, hand_velocity: float, hand_spread: float):
        self._phrase += 1
        if not self.enabled:
            self.pending = self._fallback(rule, bpm)
            return
        if self._busy:
            return  # previous call still out; keep the current phrase
        self._busy = True
        asyncio.create_task(self._ask(rule, bpm, hand_y, hand_velocity, hand_spread))

    def _fallback(self, rule, bpm):
        m = FALLBACK_MUSIC.get(rule, FALLBACK_MUSIC["orbit"])
        chord = m["chords"][self._phrase % 4]
        mood = "calm" if bpm < 100 else "driving" if bpm < 130 else "frantic"
        return {**m, "notes": chord_to_notes(chord), "rule": None,
                "commentary": f"Swarm {rule} on {chord} in {m['key']} {m['scale']}, {bpm} BPM, {mood}"}

    async def _ask(self, rule, bpm, hand_y, hand_velocity, hand_spread):
        prompt = (
            "You conduct a dancing robot swarm (1 real mBot2, 4 virtual) from a human hand.\n"
            f"Current rule: {rule}. Tempo: {bpm} BPM. Hand height 0-1: {hand_y:.2f}. "
            f"Vertical speed: {hand_velocity:+.2f}/s. Finger spread 0 (fist) to 1 (open): {hand_spread:.2f}.\n"
            "Choose the next 8-beat phrase:\n"
            "- notes: exactly 4 MIDI note numbers between 55 and 84, one per beat, played on a buzzer.\n"
            "- rule: one of pulse, orbit, figure8 (pulse = punchy, orbit = flowing, figure8 = playful).\n"
            "- key, scale, and a 4-chord loop with simple names like C, Am, F#m, Bb.\n"
            "- commentary: at most 12 words for a live dashboard.\n"
            'Reply as JSON: {"notes":[int,int,int,int],"rule":str,"key":str,"scale":str,'
            '"chords":[str,str,str,str],"commentary":str}'
        )
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.9},
        }
        try:
            data = await self._generate(body)
            self.live = True
            notes = clean_notes(data.get("notes"))
            chords = [str(c) for c in data.get("chords", [])][:4]
            if not notes:
                raise ValueError(f"bad notes {data.get('notes')!r}")
            self.pending = {
                "notes": notes,
                "rule": data.get("rule") if data.get("rule") in RULES else None,
                "key": str(data.get("key", self.current["key"])),
                "scale": str(data.get("scale", self.current["scale"])),
                "chords": chords if len(chords) == 4 else self.current["chords"],
                "commentary": str(data.get("commentary", ""))[:120],
            }
        except Exception as exc:
            print(f"[gemini] falling back: {type(exc).__name__} {exc}")
            self.live = False
            self.pending = self._fallback(rule, bpm)
        finally:
            self._busy = False


# ---------------------------------------------------------------------------
# ElevenLabs: spoken mode-transition callouts (cached per phrase)
# ---------------------------------------------------------------------------

class VoiceAnnouncer:
    CACHE = Path(__file__).parent / ".voice_cache"
    MIN_GAP_S = 3.0

    def __init__(self):
        self.key = os.getenv("ELEVENLABS_API_KEY", "")
        if self.key.startswith("your_"):
            self.key = ""
        self.voice_id = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
        self.use_say = os.getenv("VOICE_FALLBACK_SAY", "1") == "1" and shutil.which("say")
        self.player = shutil.which("afplay") or shutil.which("ffplay") or shutil.which("mpg123")
        self._last = 0.0
        self.CACHE.mkdir(exist_ok=True)

    def say(self, text: str, force: bool = False):
        """force=True skips the anti-chatter gap. Mode transitions use it so a rule-change
        line a second earlier can never swallow "Blackout" or "Swarm resynchronized"."""
        now = time.time()
        if not force and now - self._last < self.MIN_GAP_S:
            return
        self._last = now
        print(f"[voice] {text}")
        try:
            asyncio.create_task(self._speak(text))
        except RuntimeError:
            pass  # no running event loop (unit tests, shutdown)

    async def _speak(self, text: str):
        if self.key and self.player:
            path = self.CACHE / (hashlib.sha1(f"{self.voice_id}:{text}".encode()).hexdigest() + ".mp3")
            try:
                if not path.exists():
                    async with httpx.AsyncClient(timeout=10) as client:
                        r = await client.post(
                            f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}",
                            headers={"xi-api-key": self.key, "accept": "audio/mpeg"},
                            json={"text": text, "model_id": "eleven_flash_v2_5"},
                        )
                        if r.status_code >= 400:
                            raise RuntimeError(f"HTTP {r.status_code} {r.text[:160]}")
                        path.write_bytes(r.content)
                await self._play([self.player, str(path)] if "ffplay" not in self.player
                                 else [self.player, "-nodisp", "-autoexit", "-loglevel", "quiet", str(path)])
                return
            except Exception as exc:
                print(f"[voice] ElevenLabs failed, falling back: {exc}")
        if self.use_say:
            await self._play(["say", text])

    @staticmethod
    async def _play(cmd):
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        await proc.wait()


# ---------------------------------------------------------------------------
# Tiger Data (Timescale / Postgres): batched telemetry inserts
# ---------------------------------------------------------------------------

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS swarm_telemetry (
    time            TIMESTAMPTZ NOT NULL DEFAULT now(),
    seq             INTEGER,
    step            INTEGER,
    bpm             INTEGER,
    rule            TEXT,
    packet_loss_pct INTEGER,
    blackout        BOOLEAN,
    delivered       BOOLEAN,
    phase_drift     INTEGER,
    hand_detected   BOOLEAN,
    hand_y          REAL,
    robot_mode      TEXT
);
"""


HISTORY_SQL = """
SELECT time_bucket('10 seconds', time)                               AS bucket,
       round(100.0 * count(*) FILTER (WHERE delivered) / count(*))   AS delivery_pct,
       round(avg(phase_drift)::numeric, 2)                           AS phase_drift,
       count(*)                                                      AS packets
FROM swarm_telemetry
WHERE time > now() - make_interval(mins => $1)
GROUP BY bucket
ORDER BY bucket;
"""


class TelemetryStore:
    """Connects in the background and keeps retrying, so a blocked port or a paused
    database never delays hub startup, and telemetry starts flowing by itself when the
    laptop moves to a network that can reach Tiger."""

    FLUSH_S = 2.0
    RETRY_S = 15.0
    MAX_QUEUE = 5000

    def __init__(self):
        self.url = os.getenv("TIGER_DB_URL", "")
        if "user:pass@host" in self.url:
            self.url = ""
        self.pool = None
        self.queue: list[tuple] = []
        self.status = "off"  # "off" | "connecting" | "connected" | "unreachable"
        self._tasks: list[asyncio.Task] = []

    @property
    def enabled(self) -> bool:
        return self.pool is not None

    async def start(self):
        if not self.url:
            print("[tiger] TIGER_DB_URL not set, telemetry kept in memory only")
            return
        self.status = "connecting"
        self._tasks = [asyncio.create_task(self._connect_loop()),
                       asyncio.create_task(self._flush_loop())]

    async def stop(self):
        for t in self._tasks:
            t.cancel()
        if self.pool:
            await self._flush()
            await self.pool.close()

    async def _connect_loop(self):
        while self.pool is None:
            try:
                import asyncpg

                pool = await asyncpg.create_pool(self.url, min_size=1, max_size=2, timeout=8)
                async with pool.acquire() as con:
                    await con.execute(CREATE_SQL)
                    try:
                        await con.execute(
                            "SELECT create_hypertable('swarm_telemetry', 'time', if_not_exists => TRUE);"
                        )
                    except Exception:
                        pass  # plain Postgres without Timescale is fine
                self.pool = pool
                self.status = "connected"
                print("[tiger] connected")
            except Exception as exc:
                if self.status != "unreachable":
                    # exception text only: asyncpg never puts the DSN in it
                    print(f"[tiger] not reachable ({type(exc).__name__} {exc}); "
                          f"telemetry in memory, retrying every {self.RETRY_S:.0f}s")
                self.status = "unreachable"
                await asyncio.sleep(self.RETRY_S)

    def record(self, row: tuple):
        if self.url and len(self.queue) < self.MAX_QUEUE:
            self.queue.append((time.time(), *row))

    async def _flush(self):
        if not self.queue or not self.pool:
            return
        rows, self.queue = self.queue, []
        try:
            async with self.pool.acquire() as con:
                await con.executemany(
                    "INSERT INTO swarm_telemetry (time, seq, step, bpm, rule, packet_loss_pct, blackout, "
                    "delivered, phase_drift, hand_detected, hand_y, robot_mode) "
                    "VALUES (to_timestamp($1),$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)",
                    rows,
                )
        except Exception as exc:
            print(f"[tiger] insert failed ({len(rows)} rows dropped): {type(exc).__name__} {exc}")

    async def _flush_loop(self):
        while True:
            await asyncio.sleep(self.FLUSH_S)
            await self._flush()

    async def history(self, minutes: int = 15) -> list[dict] | None:
        """10-second buckets of delivery % and mean phase drift, or None if Tiger is off."""
        if not self.pool:
            return None
        try:
            async with self.pool.acquire() as con:
                rows = await con.fetch(HISTORY_SQL, minutes)
        except Exception as exc:
            print(f"[tiger] history query failed: {type(exc).__name__} {exc}")
            return None
        return [{
            "t": r["bucket"].astimezone().strftime("%H:%M:%S"),
            "delivery_pct": int(r["delivery_pct"]),
            "phase_drift": float(r["phase_drift"] or 0),
            "packets": r["packets"],
        } for r in rows]
