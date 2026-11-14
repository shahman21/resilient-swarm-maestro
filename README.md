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

## Hub: demo, history, tests

**Startup check.** The hub prints one line per service, for example `[hub] Gemini on (gemini-3.5-flash-lite), ElevenLabs on, Tiger connecting`, then `[tiger] connected`. Run it with `PYTHONUNBUFFERED=1` if you redirect the output to a file. `GET /api/state` also carries `gemini_live` (a real Gemini answer has arrived) and `tiger` (`off`, `connecting`, `connected` or `unreachable`).

* Gemini: `GEMINI_MODEL` picks the model (default `gemini-3.5-flash-lite`). If a model has been retired the hub moves on to the next one in `GEMINI_MODELS` by itself.
* Tiger: the hub connects in the background and retries every 15 s, queueing rows meanwhile. Tiger listens on a high port (not 5432), which university and venue Wi-Fi often blocks. If it says `unreachable`, switch to the phone hotspot.

**Judge demo.** One trigger runs the whole resilience story and then hands control back:

| Stage (`demo_stage`) | Seconds | Loss | Blackout | Voice callout |
| --- | --- | --- | --- | --- |
| `synced` | 20 | 0% | off | |
| `loss` | 15 | 60% | off | "Packet loss detected. Robots running on shared rules." |
| `blackout` | 10 | 60% | on | "Blackout. Autonomy engaged." |
| `resync` | 8 | 0% | off | "Swarm resynchronized." |

Start it by sending `{"demo": true}` over `/ws`, or:

```bash
curl -X POST localhost:8000/api/demo
```

Cancel with `{"demo": false}` or `curl -X POST "localhost:8000/api/demo?stop=true"`. Cancelling, or the demo finishing, always leaves the swarm at 0% loss with blackout off. The WebSocket state carries `demo_stage` (`null` when no demo is running). `DEMO_TIME_SCALE=0.25` runs it four times faster for rehearsal.

**History.** `GET /api/history` returns 10-second buckets for charts:

```json
{"source": "tiger", "bucket_s": 10, "rows": [{"t": "16:05:10", "delivery_pct": 40, "phase_drift": 1.2, "packets": 20}]}
```

`source` is `tiger` (last 15 minutes from the `swarm_telemetry` table) or `memory` (last 60 seconds, `packets` is `null`) when Tiger is off. The SQL, plus packets per rule and blackout seconds, is in `hub/tiger_queries.sql`:

```bash
psql "$TIGER_DB_URL" -f hub/tiger_queries.sql
```

**Tests.** They run offline (no keys, no database, no sound) in about a second:

```bash
cd hub && .venv/bin/python -m pytest -q
```

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
