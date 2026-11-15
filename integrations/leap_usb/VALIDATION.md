# Validation and acceptance

## Completed in the development environment

- Python syntax compilation of bridge and local server.
- JavaScript syntax checks of dashboard scripts and the lattice module.
- HTTP checks for dashboard, command-state endpoint and bundled assets.
- Deterministic pose checks: forward duration, turning direction, pulse expiry, stop and stale state.
- Mock DOM/canvas execution of dashboard startup, USB state merge and animation loop.

## Observed on the user's Windows machine before packaging

The user reported success with Leap hand detection, physical mBlock keyboard actions, injected-key testing and 30° tilt steering. These reports concern the earlier bridge used to build this package.

## Not verified here

Combined Windows/Leap/USB/browser operation has not been hardware-tested in the development environment. No claim of measured robot pose, exact path matching, zero latency, or complete browser visual verification is made.

## Hardware acceptance checklist

- [ ] Real W/A/D keys each cause the expected bounded 0.2-second movement.
- [ ] Space stops all encoder motors.
- [ ] Ultraleap Control Panel tracks one hand.
- [ ] `--test-key` and `--test-left` reach mBlock with correct focus.
- [ ] Combined launcher opens the local page.
- [ ] Level, left tilt and right tilt update both physical action and dashboard command.
- [ ] Fist and no-hand stop; returning to mBlock requires level calibration.
- [ ] Switching to browser blocks new motion keys; existing bounded action finishes.
- [ ] Exit stops issuing keys and process closes.
- [ ] Dashboard labels pose as estimated and does not present demo metrics as telemetry.
