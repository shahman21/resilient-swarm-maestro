# Resilient Swarm Maestro
## Dashboard simulation test report

**Tester:** Marz
**Environment:** Chrome, local dashboard on port 8001, **offline sim** mode
**Scope:** Browser simulation of packet loss, blackout, and recovery

### Results

| Test | Procedure | Observed result |
| --- | --- | --- |
| Formation change at 60% simulated packet loss | Set **Packet loss** to 60% and select **figure8**. | The simulated mBot2 briefly fell behind the target trajectory. It visibly caught up after approximately **3 seconds**. |
| Formation change at 60% simulated packet loss | Keep **Packet loss** at 60% and select **pulse**. | The simulated mBot2 visibly caught up in **under 1 second**. |
| Simulated blackout | Activate **Blackout** and observe the mBot2 icon and its target. | The simulated mBot2 turned **amber** and deviated from the target trajectory. Whether it continued its own beat was not separately verified. |
| Recovery after blackout | Turn off **Blackout** and observe the mBot2 icon relative to its target. | The simulated mBot2 **quickly caught up**. An exact recovery time was not measured. |

### Interpretation

The figure8 and pulse timings are visual estimates from the observed runs. The simulation randomly drops individual sends and can send the same beat more than once. The two timings therefore describe what happened in these runs. A repeatable comparison would need the same starting formation and packet-loss sequence, plus a consistent definition of when the icon has caught up.

The blackout and recovery were visible in browser simulation. Live Hub behaviour, physical mBot2 motion, and onboard beat continuity remain unverified.

### Next integration check

Repeat **60% packet loss → formation change → blackout → restore** on the Hub-served dashboard with Aditya and Jasmine. Check the physical mBot2 separately, including whether it keeps its own beat during the outage. Record the time from restoring communication to visible resynchronisation.
