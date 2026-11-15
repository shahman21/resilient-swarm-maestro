"""Local-only command state and estimated pose. This is NOT robot telemetry."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path
import threading
import time

class SyncState:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.lock = threading.RLock()
        self.updated = None
        self.pose_t = clock()
        self.x = self.y = 0.0
        self.heading = -math.pi / 2
        self.extent = 0.65
        self.active_key = 'space'
        self.expires = self.pose_t
        self.seq = 0
        self.status = {'hand': 'NO HAND', 'enabled': False, 'focused': False, 'roll': None, 'grab': None, 'height': None}

    def _advance(self, t):
        until = min(t, self.expires)
        duration = max(0.0, until - self.pose_t)
        # Matches 30 RPM / 0.2 s mBlock blocks. Dimensions are estimates.
        v = 30 * math.pi * 0.065 / 60
        if self.active_key == 'w':
            self.x += math.cos(self.heading) * v * duration
            self.y += math.sin(self.heading) * v * duration
        elif self.active_key == 'a':
            self.heading -= 2 * v / 0.115 * duration
        elif self.active_key == 'd':
            self.heading += 2 * v / 0.115 * duration
        self.pose_t = t
        self.extent = max(self.extent, math.hypot(self.x, self.y) / 0.7)

    def pulse(self, key):
        with self.lock:
            t = self.clock()
            self._advance(t)
            self.active_key = key
            self.expires = t + (0.2 if key in ('w', 'a', 'd') else 0)
            self.seq += 1

    def publish(self, driver, focused, data=None):
        with self.lock:
            self.updated = self.clock()
            self.status.update(hand=driver.label, enabled=bool(driver.enabled), focused=bool(focused),
                               roll=driver.smoothed_roll,
                               grab=data[1] if data else None,
                               height=data[4] if data else None)

    def snapshot(self):
        with self.lock:
            t = self.clock()
            self._advance(t)
            age = t - self.updated if self.updated is not None else None
            fresh = age is not None and age <= 0.7
            key = self.active_key if fresh and t < self.expires else 'space'
            return {**self.status, 'connected': fresh, 'age_ms': None if age is None else round(age * 1000),
                    'seq': self.seq, 'command': {'w': 'forward', 'a': 'left', 'd': 'right'}.get(key, 'stop'),
                    'key': key, 'pose': {'x': self.x, 'y': self.y, 'heading': self.heading, 'extent': self.extent},
                    'pose_source': 'command_estimate', 'robot_feedback': False}

STATE = SyncState()

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, directory=None, **kwargs):
        super().__init__(*args, directory=directory, **kwargs)

    def log_message(self, *_args):
        pass

    def handle(self):
        try:
            super().handle()
        except (BrokenPipeError, ConnectionResetError):
            pass  # Browser refreshed or cancelled an HTTP request.

    def do_GET(self):
        path = self.path.split('?', 1)[0]
        if path == '/api/control_state':
            body = json.dumps(STATE.snapshot(), allow_nan=False).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == '/api/history':
            body = b'{"source":"memory","bucket_s":10,"rows":[]}'
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == '/ws':
            self.send_error(404, 'USB local bridge does not use the original UDP/WebSocket hub')
            return
        return super().do_GET()


def start_server(port=8765):
    directory = str(Path(__file__).resolve().parent / 'dashboard')
    server = ThreadingHTTPServer(('127.0.0.1', port), partial(Handler, directory=directory))
    threading.Thread(target=server.serve_forever, name='dashboard-server', daemon=True).start()
    return server
