# How to run the demo (Windows laptop)

Two parts, two web pages. They can run at the same time.

| Part | What it shows | Start | Page |
| --- | --- | --- | --- |
| **A. Swarm + resilience** | 5–501 robots, packet loss, blackout, resync | double-click `start_demo.bat` | http://localhost:8000 |
| **B. Leap drives the real robot** | Hand tilt steers the mBot2 over USB | double-click `integrations\leap_usb\START_WINDOWS.bat` | http://127.0.0.1:8765 |

---

## 0. Get the latest code (do this first)

In a terminal in the repo folder:

```bash
git checkout main
git pull
```

---

## A. Swarm + resilience dashboard

**Start**
1. Double-click **`start_demo.bat`** in the repo folder.
   - A black window opens ("Swarm Maestro hub"). **Leave it open.**
   - The browser opens http://localhost:8000 after ~4 s. If not, type that address.
2. Click **Start Audio** on the page (browsers need a click before sound).
3. Check the top-left shows **hub live**.

**Run the judge demo** (about 53 s: synced 20 s → 60% loss 15 s → blackout 10 s → resync 8 s)
- Click **Run Demo** on the page.
- To cancel early: click **Run Demo** again, or in a terminal:
  ```bash
  curl -X POST "http://localhost:8000/api/demo?stop=true"
  ```
  It always ends at 0% loss, blackout off.

**Handy controls on the page**
- Swarm size **5 / 21 / 101 / 501**
- Keys **1 2 3** = pulse / orbit / figure-8, **0** = hand control back
- Packet-loss slider and **Blackout kill-switch**

**Stop**
- Close the black hub window, **or** double-click **`stop_demo.bat`**.

**Restart** (if the page freezes): `stop_demo.bat`, then `start_demo.bat`.

---

## B. Leap Motion drives the real robot (USB)

**Before starting**
1. Plug **robot (CyberPi)** and **Leap Motion** into the laptop by USB. Turn on the mBot2 base power.
2. Check Ultraleap Control Panel sees your hand.
3. Open **mBlock** → connect CyberPi → **Live** mode (not Upload).
4. In mBlock, these four key blocks must exist (test each with the real keyboard):

   | Key | Blocks |
   | --- | --- |
   | W | forward 30 RPM → wait 0.2 s → stop all encoder motors |
   | A | turn left 30 RPM → wait 0.2 s → stop all encoder motors |
   | D | turn right 30 RPM → wait 0.2 s → stop all encoder motors |
   | Space | stop all encoder motors |

**Start**
1. Double-click **`integrations\leap_usb\START_WINDOWS.bat`**. Leave its black window open.
2. The browser opens http://127.0.0.1:8765.
3. Put the browser on the left half of the screen (**Win + ←**) and mBlock on the right (**Win + →**).
4. **Click an empty spot in mBlock last.** mBlock must be the active window, or keys don't reach the robot.
5. Hold your hand palm-down and level for about half a second to calibrate.

**Steering**

| Hand | Robot |
| --- | --- |
| Palm level | forward |
| Left edge down ~30° | turn left |
| Right edge down ~30° | turn right |
| Back within ~15° of level | forward again |
| Fist or hand away | **stop** |

**If you click the browser**, the robot stops getting commands. Click empty mBlock canvas again and re-calibrate (palm level for half a second).

**Stop**
- Make a fist (robot stops), then press **Ctrl+C** in the black window, or just close it.
- Emergency: switch off the mBot2 base power.

**Quick fixes**
- Port already in use: close the old black window, or run `py leap_sync.py --port 8766` in that folder and open http://127.0.0.1:8766
- Left and right are swapped: `py leap_sync.py --invert-roll`
- Robot doesn't move: click mBlock canvas, press **W** on the keyboard. If that does nothing, mBlock's Live connection dropped; reconnect it.
- Page says "Waiting for Leap bridge": make sure you started `START_WINDOWS.bat` from `integrations\leap_usb`.

**Safety:** first run with the wheels raised off the table. On the floor, leave space and watch the USB cable.

---

## Demo day checklist

- [ ] `git pull` on main
- [ ] Laptop charging, volume up
- [ ] `start_demo.bat` → localhost:8000 → Start Audio → hub live
- [ ] mBlock Live connected, W/A/D/Space tested
- [ ] `START_WINDOWS.bat` (leap_usb) → 127.0.0.1:8765 → click mBlock → calibrate
- [ ] One rehearsal of **Run Demo** and one lap of hand steering
