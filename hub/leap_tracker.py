"""Ultraleap hand tracking -> (hand_y, rule) for the hub.

Runs in a background thread. If the leapc-python-bindings aren't installed or no
device is connected, falls back to a mock hand (LEAP_MOCK=1) or to "no hand".

Mapping (tuned on the team's Leap Motion Controller 2, desk-mounted, 2026-11-14):
  palm height 320 mm .. 500 mm  -> hand_y 0.0 .. 1.0  -> bpm 80 .. 150
  fist  (grab  > 0.8)           -> "pulse"
  pinch (pinch > 0.8, no fist)  -> "figure8"
  open or relaxed hand          -> "orbit"
A gesture has to hold for GESTURE_HOLD_S before the rule changes, and lets go at a lower
threshold than it engages at, so closing into a fist never flickers through "pinch".

Measured: open hand grab 0.00 / pinch 0.00, relaxed hand grab up to 0.41, fist grab 1.00
(and pinch 1.00, which is why fist is checked first), pinch pose pinch 1.00 / grab 0.00.
Override the height range for another desk with PALM_MIN_MM / PALM_MAX_MM in .env.
"""

import math
import os
import threading
import time

PALM_MIN_MM = float(os.getenv("PALM_MIN_MM", "320"))
PALM_MAX_MM = float(os.getenv("PALM_MAX_MM", "500"))
GRAB_ON, GRAB_OFF = 0.8, 0.55    # relaxed hands reach about 0.4
PINCH_ON, PINCH_OFF = 0.8, 0.5
GESTURE_HOLD_S = 0.25
BPM_MIN = 80
BPM_MAX = 150
HAND_TIMEOUT_S = 0.5


def hand_y_to_bpm(hand_y: float) -> int:
    hand_y = max(0.0, min(1.0, hand_y))
    return int(round(BPM_MIN + hand_y * (BPM_MAX - BPM_MIN)))


class GestureClassifier:
    """grab / pinch strengths -> rule, with hysteresis and a short hold time."""

    def __init__(self):
        self.rule = "orbit"
        self._candidate = "orbit"
        self._since = 0.0

    def update(self, grab: float, pinch: float, now: float) -> str:
        if grab > GRAB_ON or (self.rule == "pulse" and grab > GRAB_OFF):
            want = "pulse"
        elif pinch > PINCH_ON or (self.rule == "figure8" and pinch > PINCH_OFF and grab <= GRAB_ON):
            want = "figure8"
        else:
            want = "orbit"
        if want != self._candidate:
            self._candidate, self._since = want, now
        if want != self.rule and now - self._since >= GESTURE_HOLD_S:
            self.rule = want
        return self.rule


class LeapTracker:
    def __init__(self):
        self.hand_detected = False
        self.hand_y = 0.5
        self.hand_spread = 1.0  # 0 = fist, 1 = open hand
        self.gesture_rule = None  # None = no opinion
        self.source = "none"  # "leap" | "mock" | "none"
        self._last_seen = 0.0
        self._lock = threading.Lock()
        self._stop = threading.Event()

    # ---- public -------------------------------------------------------
    def start(self):
        if self._try_start_leap():
            return
        if os.getenv("LEAP_MOCK", "1") == "1":
            self.source = "mock"
            threading.Thread(target=self._mock_loop, daemon=True).start()
            print("[leap] Ultraleap not available, using mock hand")
        else:
            print("[leap] Ultraleap not available, BPM held at default")

    def stop(self):
        self._stop.set()

    def snapshot(self):
        with self._lock:
            if self.source == "leap" and time.time() - self._last_seen > HAND_TIMEOUT_S:
                self.hand_detected = False
            return {
                "hand_detected": self.hand_detected,
                "hand_y": round(self.hand_y, 3),
                "hand_spread": round(self.hand_spread, 3),
                "gesture_rule": self.gesture_rule if self.hand_detected else None,
                "source": self.source,
            }

    # ---- real device --------------------------------------------------
    def _try_start_leap(self) -> bool:
        try:
            import leap  # type: ignore
        except Exception:
            return False

        tracker = self
        gestures = GestureClassifier()

        class _Listener(leap.Listener):
            def on_connection_event(self, event):
                print("[leap] connected to tracking service")

            def on_tracking_event(self, event):
                if not event.hands:
                    return
                hand = event.hands[0]
                y_mm = hand.palm.position.y
                norm = (y_mm - PALM_MIN_MM) / (PALM_MAX_MM - PALM_MIN_MM)
                grab = getattr(hand, "grab_strength", 0.0)
                pinch = getattr(hand, "pinch_strength", 0.0)
                rule = gestures.update(grab, pinch, time.time())
                with tracker._lock:
                    # light smoothing so BPM doesn't jitter
                    tracker.hand_y = 0.8 * tracker.hand_y + 0.2 * max(0.0, min(1.0, norm))
                    tracker.hand_spread = 0.7 * tracker.hand_spread + 0.3 * (1.0 - max(0.0, min(1.0, grab)))
                    tracker.gesture_rule = rule
                    tracker.hand_detected = True
                    tracker._last_seen = time.time()

        def _run():
            try:
                conn = leap.Connection()
                conn.add_listener(_Listener())
                with conn.open():
                    while not self._stop.is_set():
                        time.sleep(0.1)
            except Exception as exc:  # device unplugged, service down, etc.
                print(f"[leap] tracking stopped: {exc}")
                with self._lock:
                    self.hand_detected = False

        self.source = "leap"
        threading.Thread(target=_run, daemon=True).start()
        print("[leap] using Ultraleap")
        return True

    # ---- mock ---------------------------------------------------------
    def _mock_loop(self):
        t0 = time.time()
        while not self._stop.is_set():
            t = time.time() - t0
            with self._lock:
                self.hand_detected = True
                # one slow sweep every ~40 s so BPM visibly changes
                self.hand_y = 0.5 + 0.4 * math.sin(t * 2 * math.pi / 40)
                self.hand_spread = 0.5 + 0.5 * math.sin(t * 2 * math.pi / 13)
                self.gesture_rule = None  # mock leaves the rule to Gemini / the judge
                self._last_seen = time.time()
            time.sleep(0.05)
