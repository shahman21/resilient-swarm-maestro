# Resilient Swarm Maestro — DurHack 2026 Master Blueprint

> **Instructions for Claude / AI Coding Assistants:**
> You are helping a 3-person hackathon team (**Jasmine**, **Marz**, and **Lead/Generalist**) build **Resilient Swarm Maestro** for DurHack 2026. When asked to initialize or scaffold this repository, create the exact directory structure, shared JSON contracts, environment templates, and isolated starter files below so all three teammates can work in parallel without merge conflicts.

---

## 1. Project Concept & Mentor-Validated Architecture

**Resilient Swarm Maestro** is a fault-tolerant, human-conducted swarm choreography and robotics system that blends **spatial hand-gesture control**, **edge robotics**, **digital twin visualization**, and **generative music**.

### Core Design Principles (From Hackathon Mentor Advice)
1. **Physical + Virtual Swarm Interaction:** One physical **mBot2 (CyberPi)** robot dances, flashes LEDs, and plays music on a table alongside **4 virtual sibling robots** rendered on a laptop screen.
2. **Minimal Bandwidth for Massive Scalability:** Instead of streaming heavy $(x, y)$ position telemetry at high frequency (which saturates networks when scaling to hundreds of drones/robots), the central laptop hub broadcasts a **tiny ~45-byte shared behavioral rule packet** (`seq`, `step`, `bpm`, `rule`). Both the physical mBot2 and the virtual robots share the exact same deterministic choreography rules (`"pulse"`, `"orbit"`, `"figure8"`), allowing them to anticipate each other's positions without constant communication.
3. **Resilience Under Failure (The Main Hook):**
   - **Packet Loss Mode (e.g., 60%–80% dropped packets):** Missed steps cause the physical robot to drift slightly out of phase with the virtual swarm. Using sequence numbers (`seq`) and step counters (`step`), the robot detects gaps (`missed_steps`) and smoothly resynchronizes when packets arrive.
   - **Total Blackout Mode (100% disconnect / Wi-Fi off):** The Ultraleap sensor continues tracking locally via USB on the laptop. Meanwhile, after `600ms` without a UDP heartbeat, the mBot2 switches to onboard **MicroPython Autonomous Mode**—turning its LEDs **Amber**, continuing to dance and play beats using its internal clock, avoiding obstacles via its **Ultrasonic Sensor**, and staying inside the table arena using its underside **Quad-RGB Line Sensor**.

---

## 2. Target Prizes & Sponsor Tracks (DurHack 2026)

| Track / Sponsor | Prize | How This Project Wins It |
| :--- | :--- | :--- |
| **Neptune North** (Primary Sponsor) | 1st: £1,000 Voucher / 2nd: Mech Keyboards | Live demo of distributed swarm coordination, packet-loss phase recovery, and total blackout autonomous fallback + state reconciliation. |
| **COMPOSITION** (Overall Theme) | Overall 1st/2nd & Spirit of the Dino | Spatial hand conducting translating human movement into synchronized robotic choreography and generative music. |
| **MLH: ElevenLabs** | Wireless Earbuds | Natural AI voice callouts announcing mode transitions (*"Packet loss detected"*, *"Blackout autonomy engaged"*, *"Swarm resynchronized"*). |
| **MLH: Gemini API** | MLH Swag Kits | Translates hand gesture dynamics into musical chord progressions, scales, and swarm choreography rules. |
| **MLH: Tiger Data** | Stream Deck Mini | Ingests real-time hand coordinates, packet loss metrics, and robot telemetry into PostgreSQL/Timescale for live dashboard charts. |
| **MLH: Entire** | Mini Portable Projector | Initialize and track team commits/agent workflows using `entire init` and `entire graph`. |

---

## 3. Team Delegation & Ownership (Zero-Conflict Folder Isolation)

| Team Member | Role | Assigned Folder | Git Branch | Core Responsibilities |
| :--- | :--- | :--- | :--- | :--- |
| **Jasmine** | Robotics & Embedded Lead | `robot/` | `feat/robot-jasmine` | • Flash MicroPython onto **mBot2 (CyberPi)** using **mBlock 5 (Upload Mode)**.<br>• Connect CyberPi to dedicated **2.4 GHz phone hotspot**.<br>• Build non-blocking UDP listener (`port 5005`) executing shared choreography rules (`pulse`, `orbit`, `figure8`), LED beat sync, and buzzer notes.<br>• Implement `600ms` Watchdog timer for **Blackout Autonomy** (Amber LEDs, internal BPM clock, Ultrasonic `<15cm` obstacle avoidance, Quad-RGB black-tape boundary detection) and `seq`/`step` phase resync. |
| **Marz** | UI & Digital Twin Lead | `dashboard/` | `feat/ui-marz` | • Build single-page web visualizer (`dashboard/index.html` using HTML5 Canvas + Tailwind CSS + Web Audio API).<br>• Render the **Swarm Arena** showing the **Physical mBot2** alongside **4 Virtual Sibling Robots** executing the exact same `pulse`/`orbit`/`figure8` deterministic math.<br>• Visualize desync & recovery when packet loss occurs (ghost position vs. synced position).<br>• Build judge control panel: **Packet Loss Slider (`0%–100%`)**, **Blackout Kill-Switch**, rule selector, and live bandwidth/telemetry charts. |
| **Generalist (You)** | Spatial Hub, Network & AI Lead | `hub/` | `feat/hub-lead` | • Set up GitHub repo, `.env.example`, and `entire init`.<br>• Connect **Ultraleap** via USB to host laptop (`leapc-python-bindings`) to map palm height $\rightarrow$ `bpm` (`80–150`) and gestures/keys $\rightarrow$ `rule`.<br>• Build Python FastAPI/UDP server (`hub/server.py`) broadcasting the ~45-byte JSON rule packet to mBot2 (`UDP :5005`) and streaming telemetry to Marz's UI (`WebSocket /ws`).<br>• Implement the **Packet Loss Noise Injector** and **Blackout Toggle**.<br>• Wire up **Gemini API**, **ElevenLabs voice alerts**, and **Tiger Data** PostgreSQL logging. |

---

## 4. Repository Structure

```text
resilient-swarm-maestro/
├── CLAUDE.md                 # This master specification & delegation guide
├── README.md                 # Quickstart instructions & hotspot/IP config
├── .env.example              # API keys template
├── robot/                    # [JASMINE] mBot2 CyberPi MicroPython firmware
│   └── main.py
├── hub/                      # [GENERALIST] Laptop Python hub, Ultraleap, UDP & AI APIs
│   ├── requirements.txt
│   ├── server.py
│   ├── leap_tracker.py
│   └── ai_services.py
└── dashboard/                # [MARZ] Browser Swarm Visualizer & Judge Controls
    └── index.html
```

---

## 5. Shared Data Contracts (DO NOT BREAK)

### A. Hub $\rightarrow$ Robot UDP Packet (`Port 5005`, ~97 bytes)
Sent once per beat (`60.0 / bpm` seconds) over local 2.4 GHz hotspot. The same object is also sent to the dashboard the instant each beat fires, so screen, robot and speakers all tick off one clock:
```json
{
  "seq": 48,
  "step": 12,
  "bpm": 120,
  "rule": "orbit",
  "notes": [60, 64, 67, 72],
  "loss_pct": 0,
  "blackout": false
}
```
* `seq` (int): Monotonically increasing packet ID (used by Jasmine's robot code to detect dropped packets).
* `step` (int): Global choreography beat counter (used to resynchronize phase after packet loss).
* `bpm` (int): Beats per minute (`80` to `150`), controlled by Ultraleap hand height.
* `rule` (str): Shared deterministic behavior ID (`"pulse"`, `"orbit"`, or `"figure8"`).
* `notes` (int[4]): MIDI note numbers for the current phrase. On every beat, robot buzzer and dashboard synth both play `notes[step % len(notes)]`. Refreshed by Gemini every 8 beats, and only ever changes on a step that is a multiple of 8.
* `loss_pct` (int): Packet-loss injector setting `0`–`100` (informational; the robot can show it).
* `blackout` (bool): Kill-switch state. Always `false` in packets the robot actually receives, because blackout stops all sends; it is there so the dashboard sees the same object.
* Size: compact JSON (`separators=(",", ":")`) is ~97 bytes. Still under one 128-byte read on the robot.

### B. Hub $\leftrightarrow$ Dashboard WebSocket (`ws://localhost:8000/ws`)
**Hub $\rightarrow$ Dashboard (State Broadcast):**
```json
{
  "seq": 42,
  "step": 10,
  "bpm": 120,
  "rule": "orbit",
  "notes": [60, 64, 67, 72],
  "loss_pct": 60,
  "packet_loss_pct": 60,
  "blackout": false,
  "packet_bytes": 97,
  "hand_detected": true,
  "hand_y": 0.52,
  "hand_spread": 0.8,
  "ai_commentary": "Swarm orbiting in C Major at 120 BPM",
  "telemetry_history": [
    {"t": "16:05:01", "delivery_pct": 40, "phase_drift": 1}
  ]
}
```

**Dashboard $\rightarrow$ Hub (Judge Controls from Marz's UI):**
```json
{
  "packet_loss_pct": 60,
  "blackout": false,
  "override_rule": "figure8"
}
```

---

## 6. Shared Choreography Math (Used by Both `robot/main.py` and `dashboard/index.html`)

To prove scalability without streaming coordinates, both Jasmine's robot and Marz's virtual nodes compute movement deterministically from `beat = step % 4`:
* **`"pulse"`**: Beat `0` moves forward / expands radius; Beat `2` moves backward / contracts radius; Beats `1, 3` hold & pulse LEDs.
* **`"orbit"`**: Continuous clockwise circular motion; virtual nodes maintain equal angular spacing ($2\pi / N$) around the arena center.
* **`"figure8"`**: Alternating left/right differential drive arcs (`beats 0–1` curve left, `beats 2–3` curve right).

### Shared beat clock (screen, motors and sound in lockstep)
* One clock lives in the hub. Each beat the hub builds the packet once, sends it over UDP and pushes the same fields to every WebSocket client straight away (not on the next 10 Hz tick).
* **Robot:** on a new `seq` it jumps to `step`, restarts its beat timer, sets motors for `beat = step % 4`, flashes LEDs and plays `notes[step % len(notes)]` on the buzzer. With no packet it keeps going on its own timer with the last `bpm`, `rule` and `notes`.
* **Dashboard:** treats each new `step` as the downbeat. Animations interpolate `t = step + elapsed / beat_ms` at 60 fps; the synth plays `notes[step % len(notes)]` at that moment. The physical-robot twin runs the robot's own dead-reckoning so drift on screen matches drift on the table.
* **MIDI → Hz:** `440 * 2 ** ((midi - 69) / 12)` on both sides.
* **LED colour:** `#00DCFF` cyan when SYNCED, `#FF8C00` amber during packet loss or blackout. The dashboard beat ring uses the physical robot's current colour.

---

## 7. Environment Setup & Claude Scaffolding Commands

### Step 1: Initialize Repo & Entire (Lead/Generalist)
```bash
git init
entire init
cp .env.example .env
```

### Step 2: `.env.example` Contents
```env
MBOT_IP=172.20.10.5
UDP_PORT=5005
GEMINI_API_KEY=your_gemini_key_here
ELEVENLABS_API_KEY=your_elevenlabs_key_here
TIGER_DB_URL=postgresql://user:pass@host:port/tsdb?sslmode=require
```

### Step 3: Prompt for Claude Code
> *"Read `CLAUDE.md` and scaffold the complete initial working codebase for `robot/main.py` (MicroPython for mBot2 CyberPi with non-blocking UDP, 600ms blackout watchdog, ultrasonic + Quad-RGB safety overrides, and sequence phase resync), `hub/server.py` + `hub/leap_tracker.py` + `hub/ai_services.py` (FastAPI + WebSocket + UDP broadcaster with packet-loss simulator and graceful fallback if Ultraleap or API keys aren't connected yet), and `dashboard/index.html` (single-file HTML5 Canvas digital twin with 1 physical + 4 virtual robots, desync ghost visualization, Web Audio synth, and judge controls)."*
---

## 8. Scaffold Notes (added at scaffold time, 2026-11-14)

These are additions, not changes. The contracts in section 5 still hold exactly.

* **Heartbeat repeats.** The hub sends the rule packet once per beat as specified, then re-sends the *same* packet (same `seq`) every `HEARTBEAT_MS` (default 150 ms) until the next beat. Reason: at 80 BPM a beat is 750 ms, longer than the robot's 600 ms watchdog, so per-beat sending alone would trip Blackout Autonomy on every beat. The robot ignores duplicate `seq` values. Each send is dropped independently by the packet-loss injector, so 80% loss will still cause the odd amber flicker. That is realistic and worth showing.
* **Robot status (optional, Robot → Hub UDP `:5006`).** Every 500 ms the robot sends `{"id":"mbot2","seq":41,"step":10,"missed":7,"mode":"synced"}` back to whichever address its last packet came from. `mode` is `"synced"` or `"auto"`. The hub forwards it to the dashboard as `robot`.
* **Extra WebSocket fields (Hub → Dashboard).** Alongside the section 5B fields: `hand_spread` (0 = fist, 1 = open hand), `last_delivered` (`{seq, step, bpm, rule, age_ms, link_age_ms}` of the last packet that was not dropped; `age_ms` is time since that beat's packet first got through, `link_age_ms` is time since *any* packet got through, repeats included, which is what the robot's 600 ms watchdog uses), `robot` (latest status above plus `age_ms`, or `null`), `music` (`{key, scale, chords}` from Gemini or the fallback), `hand_source` (`"leap"`, `"mock"` or `"none"`), `ai` (the current phrase's decision: `{source: "gemini"|"fallback", model, rule, rule_by: "ai"|"hand"|"judge"|"unchanged", notes, key, scale, reason, inputs, phrase_step}`), `override_rule`, and `sends_per_sec`. Dashboard code must treat all of these as optional.
* **Judge demo (optional control + state field).** Dashboard → Hub accepts one more optional key, `{"demo": true}` to start the scripted sequence and `{"demo": false}` to cancel it (`POST /api/demo` and `POST /api/demo?stop=true` do the same). The hub then drives `packet_loss_pct` and `blackout` itself: `synced` 20 s at 0%, `loss` 15 s at 60%, `blackout` 10 s, `resync` 8 s at 0%, then stops. Hub → Dashboard adds optional `demo_stage` (`null`, `"synced"`, `"loss"`, `"blackout"` or `"resync"`), plus `gemini_live` (bool) and `tiger` (`"off"`, `"connecting"`, `"connected"`, `"unreachable"`). Nothing in section 5 changes.
* **History endpoint.** `GET /api/history` returns `{"source": "tiger"|"memory", "bucket_s": 10, "rows": [{"t": "16:05:10", "delivery_pct": 40, "phase_drift": 1.2, "packets": 20}]}`. From Tiger it covers the last 15 minutes; from memory the last 60 seconds with `packets: null`.
* **Dashboard offline mode.** If `ws://localhost:8000/ws` is unreachable the dashboard runs a local copy of the hub loop so Marz can work without the hub running.
