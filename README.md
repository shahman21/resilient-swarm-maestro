# Resilient Swarm Maestro

DurHack 2026. One physical mBot2 and four virtual robots dance to the same tiny rule packet. Drop packets or kill the Wi-Fi and the swarm keeps going, then snaps back into phase.

Full spec and team split: [CLAUDE.md](CLAUDE.md).

## Quickstart (laptop)

```bash
cd hub
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example ../.env     # then fill in MBOT_IP and any API keys you have
uvicorn server:app --host 0.0.0.0 --port 8000
```

Open http://localhost:8000. The dashboard is served by the hub. You can also open `dashboard/index.html` straight from disk: with no hub running it switches to offline mode and simulates the hub in the browser.

Everything degrades gracefully:

| Missing | What happens |
| --- | --- |
| Ultraleap | `LEAP_MOCK=1` (default) fakes a slowly rising and falling hand. Set `LEAP_MOCK=0` to hold BPM at 120 instead. |
| `GEMINI_API_KEY` | Chords and commentary come from a fixed lookup table. |
| `ELEVENLABS_API_KEY` | Voice callouts use macOS `say`, or are skipped on other systems. |
| `TIGER_DB_URL` | Telemetry stays in memory only. |
| mBot2 | UDP packets go nowhere. The dashboard still shows the estimated physical twin. |

## Network setup (on the day)

1. Turn on a phone hotspot and force it to 2.4 GHz (iPhone: enable "Maximise Compatibility").
2. Connect the laptop and the CyberPi to it. iPhone hotspots hand out `172.20.10.x` addresses.
3. Put the hotspot name and password into `WIFI_SSID` / `WIFI_PASSWORD` at the top of `robot/main.py`. Don't commit them.
4. Flash `robot/main.py` with mBlock 5 in Upload mode. The CyberPi screen shows its IP once connected.
5. Put that IP in `.env` as `MBOT_IP` and restart the hub. `MBOT_IP=255.255.255.255` broadcasts to the whole hotspot if you can't read the screen.
6. Check macOS isn't blocking Python on the firewall (System Settings → Network → Firewall).

## Ultraleap

The Python bindings aren't on PyPI. Install the Ultraleap Gemini tracking software, then:

```bash
git clone https://github.com/ultraleap/leapc-python-bindings
cd leapc-python-bindings
pip install -r requirements.txt
python -m build leapc-cffi && pip install leapc-cffi/dist/leapc_cffi-*.tar.gz
pip install -e leapc-python-api
```

Controls: palm height sets BPM (80 to 150). Fist = `pulse`, open palm = `orbit`, pinch = `figure8`. On the dashboard, keys `1` `2` `3` override the rule and `0` hands control back to the gesture.

## Team

| Who | Folder | Branch |
| --- | --- | --- |
| Jasmine | `robot/` | `feat/robot-jasmine` |
| Marz | `dashboard/` | `feat/ui-marz` |
| Lead | `hub/` | `feat/hub-lead` |

Only edit your own folder. If a contract in CLAUDE.md section 5 needs to change, agree it in the group chat first.

## Entire

```bash
entire init
entire graph
```
