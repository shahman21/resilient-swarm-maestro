# Resilient Swarm Maestro - mBot2 (CyberPi) firmware
# Owner: Jasmine. Flash with mBlock 5 in Upload mode (Python editor).
#
# Loop (never blocks for more than a few ms):
#   1. drain UDP :5005, take the newest packet, resync step/bpm/rule from it
#   2. advance the beat on the internal clock (so missed packets don't stop the dance)
#   3. 600 ms with no packet -> AUTONOMOUS mode (amber LEDs, same choreography on own clock)
#   4. safety overrides in every mode: ultrasonic < 15 cm, black tape under Quad-RGB
#   5. every 500 ms send a status packet back to the hub (:5006)
#
# API names below are from the mBlock 5 CyberPi / mBot2 Python docs. Anything marked
# VERIFY is worth checking on the real robot first; each one is wrapped so a wrong
# name logs once instead of crashing the dance.

import time
import json
import cyberpi
import mbot2
import mbuild

try:
    import usocket as socket
except ImportError:
    import socket

# ---- config (do not commit real hotspot details) --------------------------
WIFI_SSID = ""              # TODO: fill in your 2.4GHz hotspot name (do not commit)
WIFI_PASSWORD = ""          # TODO: fill in hotspot password (do not commit)
UDP_PORT = 5005
STATUS_PORT = 5006
WATCHDOG_MS = 600
OBSTACLE_CM = 15
DRIVE_RPM = 40          # base wheel speed; keep low on a table
STATUS_EVERY_MS = 500
USE_TAPE = False        # False = floor demo, no black-tape boundary
# Offline interaction (AUTONOMOUS mode only): clap = next rule, cover the CyberPi = spin
RULES = ("pulse", "orbit", "figure8")
CLAP_LEVEL = 70         # loudness 0-100 that counts as a clap; raise if it changes rule by itself
CLAP_GAP_MS = 800       # ignore claps closer together than this
BEEP_GUARD_MS = 150     # ignore the microphone right after our own buzzer note
COVER_RATIO = 0.35      # covered = light below 35% of the room light measured at start-up
COVER_HOLD_MS = 300
SPIN_MS = 1200
MY_IP = ""              # filled in after Wi-Fi connects; kept on the status screen

# LED colour matches the dashboard beat ring: cyan = SYNCED, amber = packet loss / blackout
CYAN = (0, 220, 255)      # #00DCFF
AMBER = (255, 140, 0)     # #FF8C00
NOTE_SECS = 0.06          # buzzer blocks for this long; keep it short so the loop stays responsive
RED = (255, 0, 0)

# ---- small helpers --------------------------------------------------------
_warned = {}
_last_beep = [0]


def warn_once(key, exc):
    if key not in _warned:
        _warned[key] = True
        print("[warn]", key, exc)


def now_ms():
    return time.ticks_ms()


def read_ip():
    """Current IP, or "0.0.0.0" if the hotspot hasn't assigned one yet."""
    try:
        import network
        ip = network.WLAN(network.STA_IF).ifconfig()[0]
        if ip and ip != "0.0.0.0":
            return ip
    except Exception:
        pass
    try:
        ip = cyberpi.wifi.get_ip()
        if ip and ip != "0.0.0.0":
            return str(ip)
    except Exception:
        pass
    return "0.0.0.0"


def since(t):
    return time.ticks_diff(time.ticks_ms(), t)


def leds(rgb, brightness=1.0):
    r, g, b = rgb
    try:
        cyberpi.led.on(int(r * brightness), int(g * brightness), int(b * brightness))
    except Exception as e:
        warn_once("led", e)


def drive(left, right):
    """left/right in RPM, positive = forward for both wheels."""
    try:
        # mBot2: EM2 (right) is mirrored, so forward is (+, -). VERIFY on your robot.
        mbot2.drive_speed(left, -right)
    except Exception as e:
        warn_once("drive", e)


def stop():
    try:
        mbot2.EM_stop("ALL")
    except Exception:
        drive(0, 0)


def midi_to_hz(n):
    return 440.0 * 2 ** ((n - 69) / 12.0)


def beep(freq, secs=NOTE_SECS):
    try:
        cyberpi.audio.play_tone(freq, secs)  # blocks for `secs`, keep it short
    except Exception as e:
        warn_once("buzzer", e)
    _last_beep[0] = now_ms()


def measure_room_light():
    try:
        total = 0
        for _ in range(5):
            total += cyberpi.get_bri()
            time.sleep(0.1)
        return max(total / 5, 5)
    except Exception as e:
        warn_once("light", e)
        return 50


def local_event(st):
    """AUTONOMOUS mode only. Returns "clap", "cover" or None."""
    try:
        loud = cyberpi.get_loudness()
    except Exception as e:
        warn_once("loudness", e)
        loud = 0
    was_quiet = st.last_loud < CLAP_LEVEL - 20
    st.last_loud = loud
    if (loud >= CLAP_LEVEL and was_quiet and since(_last_beep[0]) > BEEP_GUARD_MS
            and since(st.last_clap) > CLAP_GAP_MS):
        st.last_clap = now_ms()
        return "clap"
    try:
        light = cyberpi.get_bri()
    except Exception as e:
        warn_once("light", e)
        return None
    st.last_light = light
    if light < st.room_light * COVER_RATIO:
        if st.cover_since is None:
            st.cover_since = now_ms()
        if not st.covered and since(st.cover_since) > COVER_HOLD_MS:
            st.covered = True
            return "cover"
    elif light > st.room_light * 0.6:
        st.cover_since = None
        st.covered = False
    return None


def distance_cm():
    try:
        d = mbuild.ultrasonic2.get(1)  # VERIFY port index
        return d if d and d > 0 else 300
    except Exception as e:
        warn_once("ultrasonic", e)
        return 300


def on_tape():
    """True if any Quad-RGB probe sees the black boundary tape."""
    if not USE_TAPE:
        return False
    try:
        # bitmask of probes over a line, 0 = none. VERIFY: some firmware uses
        # mbuild.quad_rgb_sensor.is_line("any", 1) instead.
        return mbuild.quad_rgb_sensor.get_line_sta("all", 1) != 0
    except Exception as e:
        warn_once("quad_rgb", e)
        return False


def show(lines):
    try:
        cyberpi.console.clear()
        for line in lines:
            cyberpi.console.println(line)
    except Exception as e:
        warn_once("display", e)


# ---- networking -----------------------------------------------------------
def connect_wifi():
    global MY_IP
    show(["Swarm Maestro", "Wi-Fi..."])
    leds((40, 40, 40))
    try:
        cyberpi.wifi.connect(WIFI_SSID, WIFI_PASSWORD)
        t0 = now_ms()
        while not cyberpi.wifi.is_connect() and since(t0) < 15000:
            time.sleep(0.2)
    except Exception as e:
        warn_once("wifi", e)
    ok = False
    try:
        ok = cyberpi.wifi.is_connect()
    except Exception:
        pass
    ip = "0.0.0.0"
    for _ in range(20):          # wait up to 10 s for the hotspot to hand out an IP
        ip = read_ip()
        if ip != "0.0.0.0":
            break
        time.sleep(0.5)
    MY_IP = ip
    show(["Swarm Maestro", "Wi-Fi " + ("OK" if ok else "FAILED"), ip])
    time.sleep(3)           # leave the IP readable before the status screen takes over
    return ok


def open_socket():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("0.0.0.0", UDP_PORT))
    s.setblocking(False)
    return s


# ---- choreography ---------------------------------------------------------
# Shared with dashboard/index.html. beat = step % 4.
#   pulse:   beat 0 forward, beat 2 backward, beats 1 & 3 hold + LED pulse
#   orbit:   continuous clockwise arc
#   figure8: beats 0-1 curve left, beats 2-3 curve right
def choreography(rule, beat):
    v = DRIVE_RPM
    if rule == "pulse":
        if beat == 0:
            return v, v
        if beat == 2:
            return -v, -v
        return 0, 0
    if rule == "orbit":
        return v, int(v * 0.45)          # left faster -> clockwise
    if rule == "figure8":
        if beat in (0, 1):
            return int(v * 0.4), v       # curve left
        return v, int(v * 0.4)           # curve right
    return 0, 0


# ---- state ----------------------------------------------------------------
class State:
    def __init__(self):
        self.seq = 0
        self.step = 0
        self.bpm = 120
        self.rule = "orbit"
        self.notes = [60, 64, 67, 72]
        self.loss_pct = 0
        self.recent_gap = False     # a seq gap since the last resync -> show amber
        self.last_rx = now_ms() - WATCHDOG_MS - 1
        self.next_beat = now_ms()
        self.missed = 0
        self.mode = "auto"          # "synced" | "auto"
        self.hub_addr = None
        self.escape_until = 0       # safety manoeuvre end time
        self.escape_turn = 1
        self.spin_until = 0         # "cover the light" spin end time
        self.room_light = 50
        self.last_light = 0
        self.last_loud = 0
        self.last_clap = now_ms()
        self.cover_since = None
        self.covered = False

    def beat_ms(self):
        return int(60000 / max(30, self.bpm))


def handle_packet(st, pkt, addr):
    seq = int(pkt.get("seq", 0))
    if seq == st.seq:
        st.last_rx = now_ms()       # heartbeat repeat: link is alive, nothing new
        st.hub_addr = addr
        return False
    if seq < st.seq and since(st.last_rx) < 2000:
        return False                # stale / reordered (an older seq after 2 s silence = hub restarted)
    if st.seq and seq > st.seq + 1:
        st.missed += seq - st.seq - 1
        st.recent_gap = True
    else:
        st.recent_gap = False
    st.seq = seq
    st.bpm = int(pkt.get("bpm", st.bpm))
    st.rule = pkt.get("rule", st.rule)
    notes = pkt.get("notes", st.notes)
    if isinstance(notes, list) and notes:
        st.notes = notes            # kept and reused if Wi-Fi drops
    st.loss_pct = int(pkt.get("loss_pct", st.loss_pct))
    st.last_rx = now_ms()
    st.hub_addr = addr
    # Phase resync: jump to the hub's step and restart the beat clock now.
    old_step = st.step
    st.step = int(pkt.get("step", st.step))
    st.next_beat = time.ticks_add(now_ms(), st.beat_ms())
    return st.step != old_step      # only re-trigger the beat if our own clock hadn't already


def on_beat(st):
    beat = st.step % 4
    colour = AMBER if (st.mode == "auto" or st.recent_gap) else CYAN
    leds(colour, 1.0 if beat in (0, 2) else 0.35)
    # same note the dashboard synth plays on this step
    beep(midi_to_hz(st.notes[st.step % len(st.notes)]))


def main():
    global MY_IP
    connect_wifi()
    sock = open_socket()
    st = State()
    st.room_light = measure_room_light()   # don't cover the CyberPi while it starts up
    last_status = now_ms()
    last_screen = now_ms()
    current_drive = (0, 0)
    last_ip = now_ms()
    stop()

    while True:
        # 1. drain socket, keep newest packet
        newest = None
        while True:
            try:
                data, addr = sock.recvfrom(128)
            except OSError:
                break
            try:
                newest = (json.loads(data), addr)
            except Exception:
                pass
        if newest:
            if handle_packet(st, newest[0], newest[1]):
                on_beat(st)

        # 2. watchdog -> mode
        mode = "synced" if since(st.last_rx) < WATCHDOG_MS else "auto"
        if mode != st.mode:
            st.mode = mode
            show(["MODE: " + ("SYNCED" if mode == "synced" else "AUTONOMOUS")])
            if mode == "auto":
                leds(AMBER)

        # 2b. offline interaction: only when the hub is silent
        if st.mode == "auto":
            ev = local_event(st)
            if ev == "clap":
                st.rule = RULES[(RULES.index(st.rule) + 1) % 3] if st.rule in RULES else "pulse"
                show(["AUTO: clap", "-> " + st.rule])
                last_screen = now_ms()
            elif ev == "cover":
                st.spin_until = time.ticks_add(now_ms(), SPIN_MS)
                show(["AUTO: covered", "spin!"])
                last_screen = now_ms()

        # 3. internal clock: advance beat even with no packets
        if time.ticks_diff(now_ms(), st.next_beat) >= 0:
            st.step += 1
            st.next_beat = time.ticks_add(st.next_beat, st.beat_ms())
            if time.ticks_diff(now_ms(), st.next_beat) > 0:
                st.next_beat = time.ticks_add(now_ms(), st.beat_ms())
            on_beat(st)

        # 4. safety overrides (all modes)
        if since(st.escape_until) < 0:
            want = (-DRIVE_RPM, -DRIVE_RPM) if since(st.escape_until) < -350 else \
                   (DRIVE_RPM * st.escape_turn, -DRIVE_RPM * st.escape_turn)
        elif distance_cm() < OBSTACLE_CM or on_tape():
            leds(RED)
            st.escape_turn = -st.escape_turn
            st.escape_until = time.ticks_add(now_ms(), 700)   # 350 ms reverse, 350 ms spin
            want = (-DRIVE_RPM, -DRIVE_RPM)
        elif st.mode == "auto" and since(st.spin_until) < 0:
            want = (DRIVE_RPM, -DRIVE_RPM)                    # spin on the spot
        else:
            want = choreography(st.rule, st.step % 4)
        if want != current_drive:
            drive(want[0], want[1])
            current_drive = want

        # 5. status back to hub
        if st.hub_addr and since(last_status) >= STATUS_EVERY_MS:
            last_status = now_ms()
            msg = json.dumps({"id": "mbot2", "seq": st.seq, "step": st.step,
                              "missed": st.missed, "mode": st.mode})
            try:
                sock.sendto(msg.encode(), (st.hub_addr[0], STATUS_PORT))
            except OSError:
                pass

        # keep trying until the hotspot has given us a real IP
        if MY_IP in ("", "0.0.0.0") and since(last_ip) >= 1000:
            last_ip = now_ms()
            MY_IP = read_ip()

        if since(last_screen) >= 1000:
            last_screen = now_ms()
            show([("SYNC " if st.mode == "synced" else "AUTO ") + st.rule,
                  MY_IP or "no IP",
                  "bpm%d s%d" % (st.bpm, st.step),
                  "miss%d loss%d" % (st.missed, st.loss_pct),
                  "L%d B%d/%d" % (st.last_loud, st.last_light, st.room_light)])

        time.sleep(0.005)


main()
