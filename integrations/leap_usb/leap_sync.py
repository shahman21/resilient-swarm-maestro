"""Read Leap Motion Controller 2 on Windows using only Python's standard library.
Sends W/A/D/SPACE to foreground mBlock and serves a localhost dashboard.
The car uses USB; no car Wi-Fi or external Python packages are required.
LeapC layouts checked against Ultraleap's LeapCSharp/LeapC.cs and LeapC docs.
"""
import argparse
import ctypes as C
import math
import os
from pathlib import Path
import sys
import time
import webbrowser

ROLL_SIGN = 1.0  # Left edge down produces a positive palm-normal roll.
TURN_ENTER_DEG = 30.0
TURN_RELEASE_DEG = 15.0

from local_sync import STATE, start_server

DEFAULT_DLL = r'D:\leap motion\Ultraleap\LeapSDK\lib\x64\LeapC.dll'

class Vector(C.Structure):
    _pack_ = 1
    _fields_ = [('x', C.c_float), ('y', C.c_float), ('z', C.c_float)]

class Quaternion(C.Structure):
    _pack_ = 1
    _fields_ = [('x', C.c_float), ('y', C.c_float), ('z', C.c_float), ('w', C.c_float)]

class Palm(C.Structure):
    _pack_ = 1
    _fields_ = [('position', Vector), ('stabilized_position', Vector),
                ('velocity', Vector), ('normal', Vector), ('width', C.c_float),
                ('direction', Vector), ('orientation', Quaternion)]

class HandPrefix(C.Structure):
    # Only the first hand's prefix is read. NEVER index an array with this type:
    # the real LEAP_HAND also includes fingers and arm after this prefix.
    _pack_ = 1
    _fields_ = [('id', C.c_uint32), ('flags', C.c_uint32), ('type', C.c_int32),
                ('confidence', C.c_float), ('visible_time', C.c_uint64),
                ('pinch_distance', C.c_float), ('grab_angle', C.c_float),
                ('pinch_strength', C.c_float), ('grab_strength', C.c_float),
                ('palm', Palm)]

class FrameHeader(C.Structure):
    _pack_ = 1
    _fields_ = [('reserved', C.c_void_p), ('frame_id', C.c_int64), ('timestamp', C.c_int64)]

class TrackingEvent(C.Structure):
    _pack_ = 1
    _fields_ = [('info', FrameHeader), ('tracking_frame_id', C.c_int64),
                ('nHands', C.c_uint32), ('pHands', C.c_void_p), ('framerate', C.c_float)]

class Message(C.Structure):
    _pack_ = 1
    _fields_ = [('size', C.c_uint32), ('type', C.c_int32),
                ('pointer', C.c_void_p), ('device_id', C.c_uint32)]


def decode_hand(frame):
    if frame.nHands == 0:
        return None
    if frame.nHands > 4 or not frame.pHands:
        raise RuntimeError('Unexpected tracking layout. Stop and share this error.')
    hand = C.cast(frame.pHands, C.POINTER(HandPrefix)).contents
    p = hand.palm.position
    normal = hand.palm.normal
    values = (hand.grab_strength, hand.pinch_strength, p.x, p.y, p.z,
              normal.x, normal.y, normal.z)
    if (not all(math.isfinite(v) for v in values) or hand.type not in (0, 1)
            or not -0.01 <= hand.grab_strength <= 1.01
            or not -0.01 <= hand.pinch_strength <= 1.01
            or max(abs(p.x), abs(p.y), abs(p.z)) > 10000):
        raise RuntimeError('Unexpected hand values. Stop and share this error.')
    label = 'FIST' if hand.grab_strength >= 0.8 else ('PINCH' if hand.pinch_strength >= 0.8 else 'OPEN')
    # Copy numbers now: LeapC pointers are invalidated by a subsequent poll.
    roll = math.degrees(math.atan2(normal.x, -normal.y))
    return (label, float(hand.grab_strength), float(hand.pinch_strength),
            float(p.x), float(p.y), float(p.z), roll, float(normal.y))


class KeyInput(C.Structure):
    _fields_ = [('vk', C.c_uint16), ('scan', C.c_uint16), ('flags', C.c_uint32),
                ('time', C.c_uint32), ('extra', C.c_size_t)]

class MouseInput(C.Structure):
    _fields_ = [('dx', C.c_int32), ('dy', C.c_int32), ('data', C.c_uint32),
                ('flags', C.c_uint32), ('time', C.c_uint32), ('extra', C.c_size_t)]

class HardwareInput(C.Structure):
    _fields_ = [('message', C.c_uint32), ('low', C.c_uint16), ('high', C.c_uint16)]

class InputUnion(C.Union):
    _fields_ = [('keyboard', KeyInput), ('mouse', MouseInput), ('hardware', HardwareInput)]

class Input(C.Structure):
    _fields_ = [('type', C.c_uint32), ('data', InputUnion)]

class WindowsKeys:
    def __init__(self):
        self.api = C.WinDLL('user32', use_last_error=True)
        self.api.SendInput.argtypes = [C.c_uint32, C.POINTER(Input), C.c_int]
        self.api.SendInput.restype = C.c_uint32
        self.api.GetForegroundWindow.restype = C.c_void_p
        self.api.GetWindowTextW.argtypes = [C.c_void_p, C.c_wchar_p, C.c_int]
        self.api.GetWindowTextW.restype = C.c_int
        self.api.GetAsyncKeyState.argtypes = [C.c_int]
        self.api.GetAsyncKeyState.restype = C.c_int16
        self.previous_f8 = False
        self.previous_escape = False

    def focused(self):
        text = C.create_unicode_buffer(512)
        self.api.GetWindowTextW(self.api.GetForegroundWindow(), text, len(text))
        return text.value.lower().startswith('mblock')

    def buttons(self):
        f8 = bool(self.api.GetAsyncKeyState(0x77) & 0x8000)
        escape = bool(self.api.GetAsyncKeyState(0x1B) & 0x8000)
        result = (f8 and not self.previous_f8, escape and not self.previous_escape)
        self.previous_f8, self.previous_escape = f8, escape
        return result

    def press(self, name):
        if not self.focused():
            return False
        vk = {'w': 0x57, 'a': 0x41, 'd': 0x44, 'space': 0x20}[name]
        down = Input()
        down.type = 1
        down.data.keyboard.vk = vk
        up = Input()
        up.type = 1
        up.data.keyboard.vk = vk
        up.data.keyboard.flags = 2
        sent = self.api.SendInput(1, C.byref(down), C.sizeof(Input))
        if sent != 1:
            raise OSError(C.get_last_error(), 'SendInput failed. Do not run mBlock as administrator unless this console is at the same permission level.')
        try:
            # Let the Electron event loop observe key-down before key-up.
            time.sleep(0.04)
        finally:
            sent = self.api.SendInput(1, C.byref(up), C.sizeof(Input))
            if sent != 1:
                raise OSError(C.get_last_error(), 'Key release failed.')
        return True

class GestureDriver:
    def __init__(self):
        self.enabled = False
        self.open_since = None
        self.last_seen = -100.0
        self.last_pulse = -100.0
        self.moving = False
        self.label = 'NO HAND'
        self.direction = 'w'
        self.neutral_roll = None
        self.level_since = None
        self.level_sum = 0.0
        self.level_count = 0
        self.smoothed_roll = None
        self.candidate = 'w'
        self.candidate_since = 0.0
        self.turn_changed = False

    def reset_calibration(self):
        self.neutral_roll = None
        self.level_since = None
        self.level_sum = 0.0
        self.level_count = 0
        self.smoothed_roll = None
        self.direction = 'w'
        self.candidate = 'w'
        self.turn_changed = False

    def feed(self, data, t):
        self.last_seen = t
        if data is None:
            self.label = 'NO HAND'
            self.open_since = None
            self.smoothed_roll = None
            if self.neutral_roll is None:
                self.level_since = None
                self.level_sum = 0.0
                self.level_count = 0
            return
        label, grab, pinch, x, y, z, raw_roll, normal_y = data
        self.label = label
        roll = ROLL_SIGN * raw_roll
        # Mild finger curling / inferred pinch during wrist roll must not reject
        # steering. Pinch is not assigned a command here; a fist still stops.
        clearly_open = (grab <= 0.65 and 60 <= y <= 600
                        and normal_y < -0.20 and abs(roll) <= 75)
        if not clearly_open:
            if grab > 0.65:
                self.label = 'STOP: fingers closed grab=%.2f roll=%+.0f' % (grab, roll)
            elif not 60 <= y <= 600:
                self.label = 'STOP: hand height %.0f mm' % y
            else:
                self.label = 'STOP: palm not down roll=%+.0f ny=%.2f' % (roll, normal_y)
            self.open_since = None
            self.smoothed_roll = None
            if self.neutral_roll is None:
                self.level_since = None
                self.level_sum = 0.0
                self.level_count = 0
            return
        if self.open_since is None:
            self.open_since = t
        if self.neutral_roll is None:
            self.label = 'CALIBRATE: palm flat (%.0f deg)' % roll
            if abs(roll) > 15:
                self.level_since = None
                self.level_sum = 0.0
                self.level_count = 0
                return
            if self.level_since is None:
                self.level_since = t
            self.level_sum += roll
            self.level_count += 1
            if t - self.level_since < 0.35:
                return
            self.neutral_roll = self.level_sum / self.level_count
        relative_roll = roll - self.neutral_roll
        if self.smoothed_roll is None:
            self.smoothed_roll = relative_roll
        else:
            self.smoothed_roll += 0.40 * (relative_roll - self.smoothed_roll)
        angle = self.smoothed_roll
        if angle >= TURN_ENTER_DEG:
            requested = 'a'
        elif angle <= -TURN_ENTER_DEG:
            requested = 'd'
        elif self.direction == 'a' and angle > TURN_RELEASE_DEG:
            requested = 'a'
        elif self.direction == 'd' and angle < -TURN_RELEASE_DEG:
            requested = 'd'
        else:
            requested = 'w'
        if requested != self.candidate:
            self.candidate = requested
            self.candidate_since = t
        elif requested != self.direction and t - self.candidate_since >= 0.08:
            self.direction = requested
            self.turn_changed = True
        self.label = '%s roll=%+.0f deg grab=%.2f' % (
            {'w': 'LEVEL/FORWARD', 'a': 'TILT LEFT', 'd': 'TILT RIGHT'}[self.direction], angle, grab)

    def step(self, t, focused, toggle=False, escape=False):
        if not focused:
            self.enabled = False
            self.open_since = None
            self.moving = False
            self.reset_calibration()
            return None
        self.enabled = not escape
        valid = (self.enabled and self.neutral_roll is not None and self.open_since is not None
                 and t - self.open_since >= 0.25 and t - self.last_seen <= 0.25)
        if self.turn_changed and self.moving:
            self.turn_changed = False
            self.moving = False
            return 'space'
        if valid:
            if t - self.last_pulse >= 0.35:
                self.last_pulse = t
                self.moving = True
                self.turn_changed = False
                return self.direction
        elif self.moving:
            self.moving = False
            return 'space'
        return None


def main():
    global ROLL_SIGN
    parser = argparse.ArgumentParser()
    parser.add_argument('--dll', default=DEFAULT_DLL)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--preview', action='store_true', help='Preview the dashboard without Leap/Windows hardware')
    parser.add_argument('--test-left', action='store_true', help='Send A once after 5 seconds, without using Leap')
    parser.add_argument('--invert-roll', action='store_true', help='Reverse left/right if the sensor orientation mirrors them')
    parser.add_argument('--test-key', action='store_true', help='One W press after a 5-second countdown, no Leap connection')
    args = parser.parse_args()
    ROLL_SIGN = -1.0 if args.invert_roll else 1.0
    if args.preview:
        server = start_server(args.port)
        print('Preview only: http://127.0.0.1:%d' % args.port, flush=True)
        try:
            while True:
                time.sleep(0.2)
        except KeyboardInterrupt:
            server.shutdown()
            server.server_close()
        return
    if sys.platform != 'win32':
        raise RuntimeError('Run this file on your Windows computer with Leap attached.')
    if C.sizeof(C.c_void_p) != 8:
        raise RuntimeError('The x64 DLL requires 64-bit Python.')
    if args.test_key or args.test_left:
        keys = WindowsKeys()
        print('TEST: switch to mBlock and click its EMPTY CANVAS within 5 seconds.', flush=True)
        for seconds in range(5, 0, -1):
            print(seconds, flush=True)
            time.sleep(1)
        if not keys.focused():
            print('NOT SENT: the foreground window is not mBlock.', flush=True)
            return
        test_key = 'a' if args.test_left else 'w'
        if keys.press(test_key):
            print('Windows accepted %s. Check the corresponding 0.2-second mBlock movement.' % test_key.upper(), flush=True)
        time.sleep(0.3)
        keys.press('space')
        return
    dll_path = Path(args.dll)
    if not dll_path.is_file():
        raise FileNotFoundError(str(dll_path))
    # Keep the DLL directory handle alive for dependent DLL loading.
    directory_handle = os.add_dll_directory(str(dll_path.parent))
    dll = C.CDLL(str(dll_path))
    dll.LeapCreateConnection.argtypes = [C.c_void_p, C.POINTER(C.c_void_p)]
    dll.LeapCreateConnection.restype = C.c_uint32
    dll.LeapOpenConnection.argtypes = [C.c_void_p]
    dll.LeapOpenConnection.restype = C.c_uint32
    dll.LeapPollConnection.argtypes = [C.c_void_p, C.c_uint32, C.POINTER(Message)]
    dll.LeapPollConnection.restype = C.c_uint32
    dll.LeapSetPolicyFlags.argtypes = [C.c_void_p, C.c_uint64, C.c_uint64]
    dll.LeapSetPolicyFlags.restype = C.c_uint32
    dll.LeapCloseConnection.argtypes = [C.c_void_p]
    dll.LeapCloseConnection.restype = None
    dll.LeapDestroyConnection.argtypes = [C.c_void_p]
    dll.LeapDestroyConnection.restype = None
    connection = C.c_void_p()
    code = dll.LeapCreateConnection(None, C.byref(connection))
    if code:
        raise RuntimeError('LeapCreateConnection: 0x%08X' % code)
    try:
        code = dll.LeapOpenConnection(connection)
        if code:
            raise RuntimeError('LeapOpenConnection: 0x%08X' % code)
        keys = WindowsKeys()
        driver = GestureDriver()
        server = start_server(args.port)
        print('Dashboard: http://127.0.0.1:%d' % args.port, flush=True)
        webbrowser.open('http://127.0.0.1:%d' % args.port)
        print('Show the browser beside mBlock; click mBlock last to control the robot.', flush=True)
        last_data = None
        print('LEAP -> MBLOCK AUTO BRIDGE', flush=True)
        print('mBlock must have: W -> forward 30 RPM -> wait 0.2 s -> stop ALL.', flush=True)
        print('Also add A -> LEFT 30 RPM -> wait 0.2s -> stop ALL; D -> RIGHT with the same timing.', flush=True)
        print('SPACE -> stop ALL encoder motors.', flush=True)
        print('Click the EMPTY mBlock canvas. No F8 is needed.', flush=True)
        print('First hold an OPEN palm facing DOWN and LEVEL for half a second.', flush=True)
        print('LEFT edge down past 30 degrees -> A/LEFT; RIGHT edge down -> D/RIGHT; LEVEL -> W/FORWARD.', flush=True)
        print('Horizontal hand POSITION is ignored. If turns are mirrored, restart with --invert-roll.', flush=True)
        print('FIST/NO HAND = stop. Mild finger curling and inferred pinch do not block tilt.', flush=True)
        print('ESC exits the bridge; Ctrl+C also exits from this console.', flush=True)
        print('Leaving mBlock stops sending keys. Returning allows control after a stable OPEN hand.', flush=True)
        last_print = 0.0
        last_frame_id = None
        dll.LeapGetNow.argtypes = []
        dll.LeapGetNow.restype = C.c_int64
        while True:
            msg = Message()
            msg.size = C.sizeof(Message)
            result = dll.LeapPollConnection(connection, 100, C.byref(msg))
            current = time.monotonic()
            if not result:
                if msg.type == 1:
                    print('CONNECTED to Ultraleap service.', flush=True)
                    dll.LeapSetPolicyFlags(connection, 1, 0)
                elif msg.type == 2:
                    driver.feed(None, current)
                    last_data = None
                    print('Tracking service disconnected.', flush=True)
                elif msg.type == 0x100 and msg.pointer:
                    frame = C.cast(msg.pointer, C.POINTER(TrackingEvent)).contents
                    age_us = int(dll.LeapGetNow()) - int(frame.info.timestamp)
                    if frame.tracking_frame_id != last_frame_id and -10000 <= age_us <= 250000:
                        data = decode_hand(frame)
                        driver.feed(data, current)
                        last_data = data
                        last_frame_id = int(frame.tracking_frame_id)
            focused = keys.focused()
            toggle, escape = keys.buttons()
            if escape:
                print('ESC: bridge stopped.', flush=True)
                break
            key = driver.step(current, focused)
            if key is not None and keys.press(key):
                STATE.pulse(key)
                print('SENT ' + key.upper(), flush=True)
            STATE.publish(driver, focused, last_data if current - driver.last_seen <= 0.25 else None)
            if current - last_print >= 0.5:
                state = 'ENABLED' if driver.enabled else 'DISABLED'
                label = driver.label if current - driver.last_seen <= 0.25 else 'NO HAND'
                print('%s | %s | %s' % (state, label, 'mBlock active' if focused else 'Click EMPTY mBlock canvas'), flush=True)
                last_print = current
    except KeyboardInterrupt:
        print('\nStopped.', flush=True)
    finally:
        STATE.pulse('space')
        if 'driver' in locals():
            driver.enabled = False
            STATE.publish(driver, False, None)
        if 'server' in locals():
            server.shutdown()
            server.server_close()
        # W movements are bounded by the mBlock 0.2-second stop even if this
        # process crashes or focus changes. Send SPACE as an extra stop request.
        try:
            if 'keys' in locals():
                keys.press('space')
        finally:
            dll.LeapCloseConnection(connection)
        dll.LeapDestroyConnection(connection)
        directory_handle.close()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('\nERROR:', type(error).__name__, str(error), flush=True)
        sys.exit(1)
