# Leap Motion → mBot2 + Dashboard (USB, Windows)

Use one Leap Motion Controller 2 to control a physical mBot2 and the team's creative dashboard on the same Windows computer. The bridge reads LeapC with Python `ctypes`, sends W/A/D/Space to the foreground mBlock app, and publishes command state to a local browser page.

**This is an optional standalone integration.** It does not replace the repository's root `dashboard/`, `hub/`, or `robot/`, and does not run the existing UDP/WebSocket hub. It uses its own dashboard copy and local HTTP server. No robot Wi-Fi is needed; both USB cables stay connected.

## Quick start

1. Install 64-bit Python and Ultraleap tracking software/SDK. Confirm hand tracking in Ultraleap Control Panel.
2. Connect Leap and mBot2 by USB. Turn on the base battery. Connect CyberPi in mBlock desktop **Live** mode.
3. Build four keyboard stacks in mBlock (see table below). Verify them with your physical keyboard.
4. Stop previous Leap bridge scripts. Double-click `START_WINDOWS.bat` in this folder.
5. The browser opens `http://127.0.0.1:8765`. Tile it beside mBlock, then click the empty mBlock canvas **last**.
6. Hold one open hand palm-down and level for about half a second. Tilt to steer. Keep mBlock foreground.

| Event in mBlock | Connected blocks |
|---|---|
| W pressed | Forward at 30 RPM → wait 0.2 s → stop all encoder motors |
| A pressed | Turn left at 30 RPM → wait 0.2 s → stop all encoder motors |
| D pressed | Turn right at 30 RPM → wait 0.2 s → stop all encoder motors |
| Space pressed | Stop all encoder motors |

| Hand input | Action |
|---|---|
| Palm level | Forward |
| Left edge down by about 30° | Left turn |
| Right edge down by about 30° | Right turn |
| Return within about 15° of level | Forward again |
| Fist or no hand | Stop |

Read the complete [中文操作流程](GUIDE_ZH.md) and [quick reference](START_HERE.txt).

## Requirements and configuration

- Windows desktop, 64-bit Python, mBlock desktop, Leap Motion Controller 2 and compatible Ultraleap tracking software with `LeapC.dll`.
- Existing user setup: mBlock 5.6.0, 64-bit Python 3.13.9 (Anaconda). This is the observed setup, not a compatibility guarantee for every Python/firmware release.
- Uses Python standard library only. No `pip install`, compiler, Python Leap bindings, Node.js, FastAPI, or cloud credentials are needed for this integration.
- Vendor SDK DLLs/drivers are **not** distributed here. Use the DLL supplied with your Ultraleap installation.
- Default DLL: `D:\leap motion\Ultraleap\LeapSDK\lib\x64\LeapC.dll`. Override on other machines:

```bat
py leap_sync.py --dll "C:\your\Ultraleap\LeapC.dll"
```

Run commands in this folder, in Command Prompt, not inside Python's `>>>` prompt.

```bat
py leap_sync.py                     
py leap_sync.py --invert-roll       
py leap_sync.py --port 8766          
py leap_sync.py --test-key           
py leap_sync.py --test-left          
py leap_sync.py --preview            
```

`--test-key` sends one W pulse after five seconds if mBlock is foreground; `--test-left` tests A. `--preview` serves only the webpage and never connects to Leap or sends keys.

## Architecture and data

One process handles Leap frames, calibration, filtered roll and direction decisions. Accepted Windows key injections also update the local command state. The dashboard polls `/api/control_state` approximately every 60 ms. The server listens on `127.0.0.1` only.

- Enter turn: 30°, release turn: 15°; constants in `leap_sync.py`.
- Angle smoothing: 0.40; direction confirmation: 0.08 s; key pulse interval: 0.35 s.
- Hand height gate: 60–600 mm; closed-hand gate: grab strength >0.65.
- Keys are pulses; each mBlock action stops after 0.2 s. Turning uses the existing left/right turn blocks, not continuous proportional differential steering.
- `local_sync.py` estimates pose using 30 RPM, wheel diameter 0.065 m, track width 0.115 m and 0.2 s pulses. Update it if the mBlock blocks change.
- State fields include `connected`, `focused`, `enabled`, `hand`, `roll`, `command`, `seq`, `pose`, `pose_source` and `robot_feedback`.

**Pose is a command estimate, not measured robot location.** Windows accepting an injected key does not confirm that mBlock executed it. Wheel slip, battery, floor and serial timing can cause drift. There is no encoder telemetry return or position correction. Music/formation/background statistics remain demo visuals, separate from USB control status.

Clicking the browser stops new movement key injection because mBlock loses focus. The current bounded mBlock action may finish its 0.2 s interval. Return to the empty mBlock canvas and recalibrate. Use a fist/remove the hand to stop; Escape or Ctrl+C exits the bridge. Start with wheels raised and check all four keyboard stacks before floor use.

## Files

| File | Purpose |
|---|---|
| `START_WINDOWS.bat` | Windows launch entry |
| `leap_sync.py` | LeapC reader, angle steering, key injection, server launch |
| `local_sync.py` | Local HTTP state and estimated pose |
| `dashboard/index.html` | Team visual interface with USB mode |
| `dashboard/usb-sync.js` | Polls and displays shared command state |
| `dashboard/swarm-lattice.mjs` | Team 3D visuals with Leap roll input |
| `dashboard/vendor/` | Bundled rendering dependencies and license texts |
| `GUIDE_ZH.md` | Full Chinese setup and troubleshooting |
| `VALIDATION.md` | Validation scope and hardware acceptance checklist |

## Provenance and validation

Dashboard source is the team's `main` snapshot: index blob `a6aec37e5325a42882b87dca94d346ae2ebfdd13`, lattice blob `5e1b24346eb4b73e9ed1fffc1c3d1f6041c02f28`. This copy is not automatically updated when the team edits its root dashboard. Preserve the team's source/assets and repository licensing. Vendor notices are in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

The user confirmed the earlier Leap reader, keyboard bridge and tilt steering on their hardware. The combined dashboard package passed syntax, HTTP, pose and simulated UI checks; combined real Windows/USB/browser acceptance is still required. See [VALIDATION.md](VALIDATION.md).
