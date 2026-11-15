# mBot2 + CyberPi, mBlock UPLOAD mode. No network required.
# Physical controls: triangle(B) toggles pause/resume; square is unused.
import time
import cyberpi
import mbot2
import mbuild

MAX_RPM = 200          # Requested wheel speed, not a guarantee of actual speed.
NEAR_CM = 8           # Ultrasonic proximity, not touch detection.
BACK_MS = 200         # Brief reverse; rear is NOT monitored by the front sensor.
HOLD_MS = 100
COOLDOWN_MS = 200


def now():
    return time.ticks_ms()


def diff(a, b):
    return time.ticks_diff(a, b)


def read_distance():
    try:
        d = mbuild.ultrasonic2.get(1)
        if isinstance(d, (int, float)) and 0 < d <= 300:
            return d
    except Exception:
        pass
    try:
        d = cyberpi.ultrasonic2.get(1)
        if isinstance(d, (int, float)) and 0 < d <= 300:
            return d
    except Exception:
        pass
    return None


def read_light():
    try:
        return cyberpi.get_bri()
    except Exception:
        return None


def read_yaw():
    try:
        value = cyberpi.get_yaw()
        if isinstance(value, (int, float)):
            return value
    except Exception:
        pass
    return None


def show(text):
    try:
        cyberpi.display.show_label(text, 12, 0, 0, 0)
    except Exception:
        cyberpi.console.clear()
        cyberpi.console.println(text)


class Motion:
    def __init__(self):
        self.action = 'READY'
        self.phase = 0
        self.angle = 0.0
        self.active_ms = 0
        self.last_yaw = None

    def start(self, action, yaw):
        if action != 'BACK' and yaw is None:
            self.action = 'YAW ERROR'
            return False
        self.action = action
        self.phase = 0
        self.angle = 0.0
        self.active_ms = 0
        self.last_yaw = yaw
        return True

    def running(self):
        return self.action in ('SPIN', 'BACK', 'EIGHT')

    def update(self, dt, yaw):
        if not self.running():
            return (0, 0)
        self.active_ms += dt
        if self.action == 'BACK':
            if self.active_ms >= BACK_MS:
                self.action = 'READY'
                return (0, 0)
            return (-MAX_RPM, -MAX_RPM)
        if yaw is None or self.last_yaw is None:
            self.action = 'YAW ERROR'
            return (0, 0)
        delta = (yaw - self.last_yaw + 180) % 360 - 180
        self.last_yaw = yaw
        if abs(delta) > 80:
            self.action = 'YAW JUMP'
            return (0, 0)
        self.angle += abs(delta)
        if self.active_ms > 5000:
            self.action = 'TURN TIMEOUT'
            return (0, 0)
        if self.angle >= 360:
            if self.action == 'EIGHT' and self.phase == 0:
                self.phase = 1
                self.angle = 0
                self.active_ms = 0
            else:
                self.action = 'READY'
                return (0, 0)
        if self.action == 'SPIN':
            return (MAX_RPM, -MAX_RPM)
        # Tangent circles in opposite directions, continuously driven.
        # One outer wheel runs at MAX_RPM, the inner wheel is held at zero.
        if self.phase == 0:
            return (MAX_RPM, 0)
        return (0, MAX_RPM)


class Commands:
    """Responsive edge detection; every accepted action is still one-shot."""
    def __init__(self, base_light, noise, t):
        self.clap_level = max(30, min(85, int(noise + 15)))
        self.quiet_level = self.clap_level - 5
        self.light_reference = float(base_light) if base_light is not None and base_light >= 3 else None
        self.dark_limit = self.light_reference - max(2, self.light_reference * 0.08) if self.light_reference is not None else None
        self.light_release = self.light_reference - max(1, self.light_reference * 0.025) if self.light_reference is not None else None
        self.previous_sound = noise
        self.reset(t, initial=True)

    def reset(self, t, initial=False):
        self.reset_at = t
        self.initial = initial
        self.quiet_since = None
        self.cover_since = self.near_since = None
        self.sound_ready = False
        self.cover_ready = self.near_ready = False

    def update(self, t, loud, light, distance):
        rise = loud - self.previous_sound
        self.previous_sound = loud
        # Follow slow room-light changes only while NOT being covered.
        # Freeze the reference as soon as a possible cover crosses the threshold.
        if (light is not None and self.light_reference is not None
                and self.cover_since is None and light > self.dark_limit):
            self.light_reference += 0.02 * (light - self.light_reference)
            self.dark_limit = self.light_reference - max(2, self.light_reference * 0.08)
            self.light_release = self.light_reference - max(1, self.light_reference * 0.025)
        dark = light is not None and self.dark_limit is not None and light <= self.dark_limit
        normal_light = light is not None and self.light_release is not None and light >= self.light_release
        close = distance is not None and 2 <= distance <= NEAR_CM
        front_clear = distance is not None and distance > NEAR_CM + 2
        # Each sensor re-arms independently. No global "all sensors clear" gate.
        if normal_light:
            self.cover_ready = True
            self.cover_since = None
        elif dark and self.cover_ready:
            if self.cover_since is None:
                self.cover_since = t
        else:
            self.cover_since = None
        if front_clear:
            self.near_ready = True
            self.near_since = None
        elif close and self.near_ready:
            if self.near_since is None:
                self.near_since = t
        else:
            self.near_since = None
        cover = self.cover_since is not None and diff(t, self.cover_since) >= 60
        near = self.near_since is not None and diff(t, self.near_since) >= 80

        # Loudness rise triggers immediately; no need to wait for a pulse to end.
        sound_allowed = self.initial or diff(t, self.reset_at) >= 700
        clap = False
        if not sound_allowed:
            self.sound_ready = False
            self.quiet_since = None
        elif loud < self.quiet_level:
            if self.quiet_since is None:
                self.quiet_since = t
            if diff(t, self.quiet_since) >= 60:
                self.sound_ready = True
        else:
            clap = self.sound_ready and loud >= self.clap_level and rise >= 10
            self.sound_ready = False
            self.quiet_since = None
        action = 'BACK' if near else ('EIGHT' if cover else ('SPIN' if clap else None))
        if action is not None:
            self.reset(t)
        return action


def main():
    mbot2.drive_speed(0, 0)
    cyberpi.led.on(0, 0, 0)
    show('SETUP\nHands away; stay quiet\nKeep robot still')
    time.sleep(1)
    lights, sounds = [], []
    for i in range(20):
        l = read_light()
        if l is not None:
            lights.append(l)
        sounds.append(cyberpi.get_loudness())
        time.sleep(0.02)
    base = sorted(lights)[len(lights)//2] if lights else None
    noise = sorted(sounds)[len(sounds)//2]
    detector = Commands(base, noise, now())
    motion = Motion()
    paused = False
    previous_b = False
    last_toggle = now() - 500
    last_tick = now()
    screen_time = now()
    stop_time = now()
    command = (0, 0)
    peak = 0

    def set_wheels(want):
        mbot2.drive_speed(want[0], -want[1])

    while True:
        t = now()
        dt = min(100, max(0, diff(t, last_tick)))
        last_tick = t
        triangle = cyberpi.controller.is_press('b')
        edge = triangle and not previous_b
        previous_b = triangle
        if edge and diff(t, last_toggle) >= 180:
            last_toggle = t
            paused = not paused
            set_wheels((0, 0))
            command = (0, 0)
            motion.last_yaw = read_yaw()
            detector.reset(t)
            show('PAUSED\nTriangle: resume' if paused else 'CONTINUE')
        if paused:
            motion.last_yaw = read_yaw()
            if diff(t, stop_time) >= 250:
                set_wheels((0, 0))
                stop_time = t
            time.sleep(0.01)
            continue
        yaw = read_yaw()
        if motion.running():
            want = motion.update(dt, yaw)
            if not motion.running():
                detector.reset(t)
                set_wheels((0, 0))
                command = (0, 0)
                show('STOPPED\nWait for a new gesture')
        else:
            # No command means STOP, with zero-speed refreshed while waiting.
            want = (0, 0)
            if diff(t, stop_time) >= 250:
                set_wheels((0, 0))
                stop_time = t
            loud = cyberpi.get_loudness()
            peak = max(peak, loud)
            light = read_light()
            distance = read_distance()
            action = detector.update(t, loud, light, distance)
            if action is not None:
                if motion.start(action, yaw):
                    want = motion.update(0, yaw)
                show(motion.action + '\nTriangle: pause/go')
            if not motion.running() and diff(t, screen_time) >= 250:
                screen_time = t
                lt = '-' if light is None else str(int(light))
                dst = '-' if distance is None else str(int(distance))
                show('READY / STOPPED\nClap:spin Near:back\nCover:8 Triangle:pause\nS:%d Need:%d\nL:%s Dark:%s D:%s' %
                     (peak, detector.clap_level, lt, '-' if detector.dark_limit is None else str(int(detector.dark_limit)), dst))
                peak = 0
        if want != command:
            set_wheels(want)
            command = want
        time.sleep(0.01)


try:
    main()
finally:
    mbot2.drive_speed(0, 0)
