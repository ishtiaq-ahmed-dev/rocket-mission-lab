# Project history

A condensed record of earlier revisions. The individual dated notes, validation
logs and the old README were merged here in November 2026; their full text is
in git history (commit `2e44adf` and earlier). Numbers quoted below describe
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
