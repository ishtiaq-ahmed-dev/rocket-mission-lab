# Project history

A condensed record of earlier revisions. The individual dated notes, validation
logs and the old README were merged here in November 2026; their full text is
in git history (commit `6c66788` and earlier). Numbers quoted below describe
those earlier snapshots, not the current flight.

| Date | Revision | What it established |
| --- | --- | --- |
| 19 Oct 2026 | Python laboratory and first RL iteration | MuJoCo free-body 400 m subscale vehicle, Gymnasium environments, PPO/SAC, curriculum, fixed-seed evaluation. PPO landing policies did not qualify; diagnoses (action collapse, throttle exploration, horizon) are summarised in the Python lab notes `docs/03-mdp.md` to `docs/06-ppo.md`. |
| 20 Oct 2026 | Combined takeoff/landing, CUDA comparison | Ascent goal and pad-accuracy experiments, conservative PPO updates; still no learned policy met the success gate. |
| 21 Oct 2026 | Mission controls and flight fidelity | Local-metre flight plans, retargeting, thrust-axis-aligned plume, hold-down release before liftoff, engine shutdown before staging, first-foot touchdown detection, React mission-control dashboard and its validation run. |
| 21 Oct 2026 | Rocket structure review | Falcon 9 appearance from the SpaceX user's guide and NASA launch/landing sequence: tank layout, interstage, grid fins, four legs. |
| 21 Oct 2026 | Performance | Code-split bundle, render budget and LOD checks for the dashboard. |
| 23 Oct 2026 | Native Isaac Sim runtime | Isaac Sim 6 viewport, FastAPI telemetry bridge, seeded native variations; acceptance limits recorded (no real-world claim). |
| 23 Oct 2026 | Real-time playback and pad spacing | 1:1 playback clock, pads more than 1 km apart, distinct TAKEOFF/LANDING markings. |
| 24 Oct 2026 | Cinematic replay | Offline Isaac film renderer, broadcast overlay and narration (`scripts/broadcast.py`, local Kokoro TTS model in ignored `data/models/`). |
| 28 Oct 2026 | Pad labels, distance and timing | Distance rule enforced at every public entry point; physical timing checks. |
| 30 Oct 2026 | Falcon 9 RTLS replay | Single-page Three.js replay of a full orbital mission with WGS-84 / ISO 2533 anchors, scripted predictor-corrector guidance. |
| 1 Nov 2026 | International-standard profile | Public Falcon 9 Block 5 anchors, `scripts/check_standards.js`. |
| 2 Nov 2026 | **Neural flight policy** | Scripted guidance removed from the page. A trained network flies the whole mission; the boostback no longer thrusts toward the ground; the return was rebuilt around real RTLS practice. See [FLIGHT-POLICY.md](FLIGHT-POLICY.md). |
| 8 Nov 2026 | **Real ground imagery** | The procedural coastline was replaced by public-domain USGS imagery (NAIP, Landsat, Blue Marble) in six nested layers from the pad apron to the Gulf of Mexico, with land/water masks. LZ-1 was moved to the pad centre measured on that imagery (145 m east of the old coordinate) and the policy retrained with DAgger on the corrected geometry. |
| 8 Nov 2026 | **Falcon 9 RTLS timeline** | The teacher was retuned to the public Falcon 9 RTLS timeline (MECO near 60 km with the return propellant kept, booster apogee ~128 km, ten-second entry burn at 66 km, landing burn T+7:24, touchdown T+7:49, against Ax-4's T+7:22 and T+7:39), with drag-aware landing ignition and smooth terminal insertion guidance. The network was retrained from scratch, then again (warm-started) after a throttle bucket before max-Q moved max-Q to T+1:11 as on Falcon 9: 297/300 held-out missions against the teacher's 298. |
| 9 Nov 2026 | **Terminal landing redesign** | The teacher's final-metres control was rebuilt: a terminal gate with a gentle last deceleration (1.4 m/s touchdowns), braking-limited zero-effort-miss divert with the aerodynamic side force in its prediction, a tilt that fades instead of flipping where thrust and aerodynamic forces cancel, glide aiming at an undiverted landing burn, and a lofted boostback on low arcs: 2,300/2,300 stress flights. The network was retrained with DAgger and hard-example mining: 299/300 held-out, matching the teacher. |
| 10 Nov 2026 | **Predictive inputs** | The booster network grew to 4 × 384 and gained two inputs computed from its own state (vacuum impact point, undiverted touchdown point), the cues for boostback cutoff and landing divert. Retrained from scratch with DAgger and four hard-example mining loops on a shared machine (memory-aware, restartable orchestration): 299/300 held-out with no crash, 1,998/2,000 selection, 99.7 % on 6,000 fresh seeds. |
| 10 Nov 2026 | **Smooth landing, real flip timing** | The teacher's landing divert was replaced by two constant leans solved with the full flight model (no more swinging back and forth), the flip moved to six seconds after separation at up to 12°/s, and two look-ahead errors were fixed (pad position at the touchdown instant; a stale boostback cutoff plan). The network was retrained with DAgger and a crash-aware mining loop: 298/300 held-out (teacher 300/300), 1,997/2,000 selection, landing lean path 49° against 119°. The replay gained engine fire and deluge steam at ignition instead of dust, a wide thin-air plume at altitude, no false heating glow after separation, and no wires over the pad. |
| 10 Nov 2026 | **Landing faults fixed** | The network's rare crashes (about 1 in 1,000) were traced to the teacher's labels: an engine that went out during the landing burn was told to stay off, a booster rising above the pad was told to keep thrusting, and a 2-4° step in the landing lean at 150 m disturbed the network's engine choice. The teacher now relights, cuts and falls instead of climbing, and fades the lean; its boostback planner returns the best plan it predicted (2,000/2,000 selection, 2,300/2,300 stress). 278,423 mislabelled rows were removed and training flights carry engine faults. Four DAgger rounds, with the training set on the GPU: 300/300 and 1,000/1,000 held-out, 6,000/6,000 fresh flights (previous network 5,987), and recovery from a forced engine fault in 399 of 400 flights (previously 25). |
| 12 Nov 2026 | **Repository cleanup** | The October Python laboratory (`rocket_lab/`: MuJoCo subscale vehicle, Gymnasium environments, PPO/SAC training, FastAPI service, Isaac film tooling), its configs, tests, notes and evidence files were removed; none of it was used by the replay or the flight policy. The README was rewritten around the neural flight, with figures generated from the simulator. The lab remains in git history before this commit. |

## Lessons carried forward

- Results belong to a specific source and configuration snapshot. Earlier
  10,000-flight and qualification files did not qualify later controllers, which
  is why the stale result archives were removed rather than kept as evidence.
- A replay must never correct the vehicle after the fact (no snapping onto the
  pad, no hidden stabilising torque). Every current touchdown is the integrated
  state at first contact.
- Learned controllers failed when trained from scratch with sparse rewards on
  the subscale task. The flight policy that now flies the replay is trained by
  imitation of a physically consistent teacher with DAgger, and is evaluated
  closed-loop on dispersed flights it never saw.
