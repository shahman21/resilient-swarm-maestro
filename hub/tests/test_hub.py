"""Hub tests. Run from hub/:  .venv/bin/python -m pytest -q"""

import asyncio
import json
import random
import socket

import pytest

import server
from server import DEMO_STAGES, Hub

KEYS_5A = {"seq", "step", "bpm", "rule", "notes", "loss_pct", "blackout"}


class FakeSock:
    """Stands in for the UDP socket and counts what would have gone on the wire."""

    def __init__(self):
        self.sent = []

    def sendto(self, data, addr):
        self.sent.append((data, addr))


@pytest.fixture
def hub():
    h = Hub()
    h.sock.close()
    h.sock = FakeSock()
    h.spoken = []
    h.voice.say = lambda text, force=False: h.spoken.append(text)
    return h


def test_packet_has_exactly_5a_keys_and_fits_128_bytes(hub):
    async def run():
        hub._new_beat()

    asyncio.run(run())
    packet = json.loads(hub.packet)
    assert set(packet) == KEYS_5A
    assert packet["seq"] == 1 and packet["step"] == 1
    assert len(packet["notes"]) == 4 and all(isinstance(n, int) for n in packet["notes"])
    assert len(hub.packet) < 128
    # worst case: biggest numbers a long session could reach
    hub.seq, hub.step, hub.bpm, hub.rule = 99999, 99999, 150, "figure8"
    hub.packet_loss_pct, hub.blackout = 100, False
    worst = json.dumps(hub.packet_dict(), separators=(",", ":")).encode()
    assert len(worst) < 128
    # and what goes on the wire is the same object the dashboard is given
    assert hub.sock.sent[0][0] == hub.packet
    assert KEYS_5A <= set(hub.state())


def test_notes_only_change_on_phrase_boundaries(hub):
    changed_on = []

    async def run():
        prev = list(hub.notes)
        for _ in range(96):
            hub._new_beat()
            if hub.notes != prev:
                changed_on.append(hub.step)
                prev = list(hub.notes)

    asyncio.run(run())
    assert len(changed_on) >= 3, "fallback composer should move through its chords"
    assert all(step % 8 == 0 for step in changed_on), changed_on


def test_loss_injector_drops_about_60_percent(hub):
    random.seed(2026)
    hub.packet = b"x"
    hub.packet_loss_pct = 60
    results = [hub._send() for _ in range(2000)]
    dropped = results.count(False) / 2000
    assert 0.50 <= dropped <= 0.70, dropped
    assert len(hub.sock.sent) == results.count(True)


def test_blackout_sends_nothing(hub):
    hub.packet = b"x"
    hub.packet_loss_pct = 0
    hub.blackout = True
    assert not any(hub._send() for _ in range(500))
    assert hub.sock.sent == []
    hub.blackout = False
    assert hub._send() and len(hub.sock.sent) == 1


def test_apply_controls_clamps_and_validates(hub):
    hub.apply_controls({"packet_loss_pct": 250})
    assert hub.packet_loss_pct == 100
    hub.apply_controls({"packet_loss_pct": -5})
    assert hub.packet_loss_pct == 0
    hub.apply_controls({"packet_loss_pct": 59.9})
    assert hub.packet_loss_pct == 59 and isinstance(hub.packet_loss_pct, int)

    # junk is ignored and never blocks the valid fields beside it
    hub.apply_controls({"packet_loss_pct": "lots", "blackout": True, "override_rule": "figure8"})
    assert hub.packet_loss_pct == 59
    assert hub.blackout is True
    assert hub.override_rule == "figure8"
    hub.apply_controls({"packet_loss_pct": None, "blackout": "yes"})
    assert hub.packet_loss_pct == 59 and hub.blackout is True
    hub.apply_controls({"blackout": False})
    assert hub.blackout is False

    hub.apply_controls({"override_rule": "moonwalk"})
    assert hub.override_rule is None
    hub.apply_controls({"override_rule": "pulse"})
    assert hub.override_rule == "pulse"
    hub.apply_controls({"override_rule": None})
    assert hub.override_rule is None

    for junk in ([], "blackout", 7, None, {"unknown": 1}, {"demo": "true"}):
        hub.apply_controls(junk)
    assert (hub.packet_loss_pct, hub.blackout, hub.override_rule) == (59, False, None)
    assert hub._demo_task is None


def test_robot_status_over_udp_shows_in_state(hub, monkeypatch):
    monkeypatch.setattr(server, "hub", hub)  # _StatusProtocol reports to the module-level hub

    async def run():
        loop = asyncio.get_running_loop()
        try:
            transport, _ = await loop.create_datagram_endpoint(
                server._StatusProtocol, local_addr=("127.0.0.1", server.STATUS_PORT))
        except OSError:  # a hub is already running on :5006, use a free port instead
            transport, _ = await loop.create_datagram_endpoint(
                server._StatusProtocol, local_addr=("127.0.0.1", 0))
        port = transport.get_extra_info("sockname")[1]
        assert hub.state()["robot"] is None
        robot = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        robot.sendto(b"not json", ("127.0.0.1", port))
        robot.sendto(json.dumps({"id": "mbot2", "seq": 41, "step": 10, "missed": 7,
                                 "mode": "auto"}).encode(), ("127.0.0.1", port))
        for _ in range(50):
            await asyncio.sleep(0.01)
            if hub.robot:
                break
        robot.close()
        transport.close()

    asyncio.run(run())
    got = hub.state()["robot"]
    assert got is not None
    assert (got["id"], got["seq"], got["step"], got["missed"], got["mode"]) == ("mbot2", 41, 10, 7, "auto")
    assert got["ip"] == "127.0.0.1" and got["age_ms"] >= 0
    assert hub.robot_fresh()


def test_demo_runs_its_stages_in_order(hub):
    hub.demo_scale = 0.01  # 53 s of demo in about half a second
    seen = []  # (stage, loss, blackout) each time the stage changes

    async def run():
        assert hub.state()["demo_stage"] is None
        hub.apply_controls({"demo": True})
        assert hub.start_demo() is False  # already running: second trigger is a no-op
        await asyncio.sleep(0)  # let the demo task take its first step
        for _ in range(3000):
            snap = (hub.demo_stage, hub.packet_loss_pct, hub.blackout)
            if not seen or seen[-1] != snap:
                seen.append(snap)
            if hub._demo_task.done():
                break
            await asyncio.sleep(0.002)

    asyncio.run(run())
    assert seen[:4] == [(s, loss, bo) for s, _, loss, bo in DEMO_STAGES]
    assert [s for s, _, _ in seen] == ["synced", "loss", "blackout", "resync", None]
    assert seen[-1] == (None, 0, False)
    assert hub.state()["demo_stage"] is None
    assert hub.spoken == [
        "Packet loss detected. Robots running on shared rules.",
        "Blackout. Autonomy engaged.",
        "Swarm resynchronized.",
    ]


def test_demo_cancel_restores_a_connected_swarm(hub):
    hub.demo_scale = 0.01

    async def run():
        hub.apply_controls({"demo": True})
        while hub.demo_stage != "blackout":
            await asyncio.sleep(0.002)
        assert hub.blackout is True
        hub.apply_controls({"demo": False})
        await asyncio.sleep(0.02)

    asyncio.run(run())
    assert (hub.demo_stage, hub.packet_loss_pct, hub.blackout) == (None, 0, False)
    assert hub.spoken[-1] == "Swarm resynchronized."


def test_history_falls_back_to_memory_in_10s_buckets(hub):
    for sec, pct in ((1, 100), (5, 80), (12, 40), (18, 60)):
        hub.telemetry_history.append({"t": f"16:05:{sec:02d}", "delivery_pct": pct, "phase_drift": 1.0})
    out = asyncio.run(hub.history())
    assert out["source"] == "memory" and out["bucket_s"] == 10
    assert [(r["t"], r["delivery_pct"]) for r in out["rows"]] == [("16:05:00", 90), ("16:05:10", 50)]


def test_gesture_classifier_holds_and_does_not_flicker():
    from leap_tracker import GESTURE_HOLD_S, GestureClassifier, hand_y_to_bpm

    g = GestureClassifier()
    assert g.update(0.0, 0.0, 0.0) == "orbit"
    # closing into a fist: pinch rises first, for less than the hold time
    assert g.update(0.2, 0.9, 1.00) == "orbit"
    assert g.update(1.0, 1.0, 1.10) == "orbit"
    assert g.update(1.0, 1.0, 1.10 + GESTURE_HOLD_S) == "pulse"
    # a slightly loosened fist stays a fist (hysteresis); a relaxed hand does not
    assert g.update(0.6, 0.3, 2.0) == "pulse"
    g.update(0.4, 0.0, 3.0)
    assert g.update(0.4, 0.0, 3.0 + GESTURE_HOLD_S) == "orbit"
    # pinch with open fingers
    g.update(0.0, 1.0, 4.0)
    assert g.update(0.0, 1.0, 4.0 + GESTURE_HOLD_S) == "figure8"
    assert (hand_y_to_bpm(-1), hand_y_to_bpm(0.5), hand_y_to_bpm(2)) == (80, 115, 150)


def test_link_age_counts_heartbeat_repeats(hub, monkeypatch):
    """At 80 BPM a beat is 750 ms. Repeats every 150 ms must keep the link fresh,
    otherwise the dashboard shows AUTONOMOUS at the end of every beat with 0% loss."""
    clock = [1000.0]
    monkeypatch.setattr(server.time, "monotonic", lambda: clock[0])

    async def run():
        hub._new_beat()

    asyncio.run(run())
    for _ in range(4):  # four repeats, 150 ms apart, same seq
        clock[0] += 0.15
        assert hub._send()
    clock[0] += 0.05
    ld = hub.state()["last_delivered"]
    assert ld["age_ms"] >= 640  # beat packet itself is old...
    assert ld["link_age_ms"] <= 60  # ...but the link is fresh
