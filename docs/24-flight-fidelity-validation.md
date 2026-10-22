# Flight fidelity and dashboard revision — 21 October 2026

## What changed

- The light mission dashboard follows the supplied reference: restrained purple controls, white rounded cards, telemetry charts, mission setup, sites and an event log. Playback, simulation, recorded results and training have distinct labels. Inherited dark coordinate inputs and fullscreen overflow were corrected during browser review.
- Bell, plume and smoke share one thrust-axis conversion. The renderer no longer adds a second gimbal lag or wall-clock throttle smoothing. Vacuum expansion preserves the nozzle-exit width. Smoke diminishes with atmospheric density. These effects remain illustrative rather than CFD.
- Launch and landing labels are distinct. Concrete pads remain fixed in world coordinates. Nearby target commands reuse prepared ground instead of overlaying coplanar disks. Only the active-target ring changes selection; its radius is the recorded landing tolerance.
- Launch supports hold an upright vehicle while its engine spools. Release requires a sustained thrust margin; clamps and tower arms open from the recorded release time. Recovery legs remain stowed during ascent and deploy on descent.
- Combined flight completes main-engine shutdown before stage release. The released unpowered body is independently integrated in MuJoCo with gravity, drag and inherited angular/linear motion. Archived flights retain an explicitly labelled ballistic preview.
- Engine torque uses the rendered 17.9 m lever and the free-joint local torque frame. A regression verifies that body-fixed gimbal torque does not invent roll during rotation.
- Touchdown detects the first tilted foot sole and retains impact velocity and coordinates. Landing success requires center error at most **1 m**, tilt below 5 degrees, and both center/contact speed below 2 m/s. The concrete pad size is separate from this tolerance. Guidance spends real time and fuel acquiring the target before the final descent; the renderer never snaps a rocket onto the cross.
- Multiple retarget commands preserve the complete preceding flight and initial plan. A learned actor sees the new target before its next action. Playback shows targets only after their command times. Arbitrary commands can remain unreachable and fail.
- Exterior audio uses approximate propagation delay, distance attenuation and altitude attenuation; onboard mode retains synthesized structural sound. Neither mode is an actual engine recording or an acoustic solver.

## Separately identified suborbital study

Select **Suborbital study** in the flight-plan editor, then **Combined**. Its default cutoff command is at 100 km. It uses a separate generic vehicle with 140,000 kg nominal propellant, 22,000 kg dry mass, 3.2 MN thrust, 360 s Isp and a 6% steady throttle floor. These are explicit research assumptions, not proprietary vehicle data.

Gravity decreases with altitude. The dry-air atmosphere uses standard hydrostatic layers through 84.852 km geopotential altitude and a continuous approximate tail above that point. Coast, recovery ignition, target acquisition and touchdown follow integrated dynamics. The spherical horizon and sky fade are rendering aids; they do not add forces. The Mission camera frames the measured apogee rather than only the separation altitude.

## Executed evidence

Dynamics identity: `05d6ce3a455c4bbc0d0cb5df846fae29a755c6e21dd4684a0d7e5479bf6c22dd`.

The source-frozen [flight journal](evidence/2026-10-21/fidelity-v19-pilots.json) contains seeds 51,000 onward, configuration hashes, terminal values and apogees for every row:

| Development pilot | Observed successes |
| --- | ---: |
| Same-pad landing / takeoff / combined | 100 / 100 each |
| Separate-site landing / takeoff / combined | 100 / 100 each |
| Default 80 m east / 40 m north transfer, all three missions | 100 / 100 each |
| Landing with target changes at 3 s and 6 s | 100 / 100 |
| 100 km separation and booster recovery | 16 / 16 |

Total: **1,016 / 1,016 classical development flights**. The 16 suborbital flights reached approximately 221 km apogee; maximum touchdown offset was 0.079 m and maximum center speed 0.826 m/s. These small samples are not 10,000-seed qualification. Earlier failures are retained in [the pre-acquisition snapshot](evidence/2026-10-21/fidelity-v19-before-capture.json); they motivated the physical target-acquisition hold.

Executed final regression checks: **85 Python tests; 44 frontend tests; TypeScript/production build and ESLint**. This includes dispatch, checkpoint recovery, changed-dynamics rejection and memory-headroom coverage. [Live validation](evidence/2026-10-21/flight-fidelity-live-validation.json) confirms the production loopback HTTP service, schema, source identity and retrievable mission telemetry. The final live custom-site combined flight landed 0.0573 m from its target at 0.1877 m/s.

Earlier browser review found the inherited dark fields and fullscreen cropping, which were corrected. Final browser control subsequently returned **“Local browser use is disabled in Work settings.”** The latest logarithmic-depth shaders, fullscreen layout, narrow-screen layout and playback-input changes therefore still need final visual verification. Build and API success do not establish WebGL appearance, frame rate or perceived sound quality. No final screenshot is claimed.

## Training

The earlier v18 campaign plateaued at 16,194,212 aggregate steps. It is retained as failed/partial research, with no reliable landing or combined policy. Its optimizer is not resumed into the revised physics.

The new v19 study has a **100 million environment-step ceiling**, alternating landing, takeoff and combined blocks. It uses separate 256/256/128 actor/value networks, bounded action means, target and altitude curriculum, seeded retargets, real optimizer/normalization snapshots and a 12-round plateau gate. Every block checks source identity; a changed dynamics file halts continuation rather than silently reusing the model.

The [compute pilot](evidence/2026-10-21/policy-compute-benchmark.json) measured 4,096 easy-start PPO steps: CPU about 1,151 steps/s, CUDA about 197 steps/s on the RTX 5070 Ti. This measures that small workload only. A larger GPU workload may differ. The campaign uses CPU on this evidence. A larger budget is not a claim of convergence.

Candidates need at least 254/256 development successes before a separate 10,000-seed nominal gate. Learned policies never substitute a classical controller. All counts above are classical, not RL results.

Campaign `mission-campaign-1792595301877641600` initially failed during an observed host memory allocation failure at 106,496 landing steps. The latest compatible persisted checkpoint was 100,000 steps; 6,496 unsaved steps were discarded. The preview also encountered allocation failures in that interval. This establishes concurrent memory pressure, not a proven source of that pressure.

The campaign was resumed from the compatible snapshot and started its takeoff block. Recovery preserves saved optimizer and normalization state, while environments and RNG restart under the recorded seed policy. The training callback now waits when available physical memory is below 2 GiB or available commit is below 4 GiB; it keeps reporting status and accepts Stop while waiting. This is a best-effort headroom gate, not a guarantee against rapid host-wide exhaustion. It changes no Windows memory settings and stops no unrelated process. The [recovery snapshot](evidence/2026-10-21/flight-fidelity-training-recovery.json) records the observed state; it is not a continuously updated qualification result.

## Remaining qualification boundaries

This revision is an inspectable research simulator, not a flight-certified digital twin. It still lacks validated vehicle identification, powered upper-stage/orbital flight, coast RCS, Mach-dependent aerodynamic coefficients, thermal/reentry loads, structural flexibility, slosh, Earth rotation/downrange curvature, compliant multi-foot contact and post-touchdown toppling. Attached-stage center-of-mass/inertia distribution remains a lumped approximation. The atmosphere above the standard layers is approximate. Ship motion and ocean contact are not dynamically simulated.

International presentation should state those assumptions, show failure evidence and distinguish classical pilots, learned-policy development, held-out statistics, stress testing and real-hardware validation. No claim of universal divert reachability, arbitrary fault recovery or real-flight safety is supported by the current evidence.

## Primary sources

- [NASA rocket control](https://www1.grc.nasa.gov/beginners-guide-to-aeronautics/rocket-control/) — thrust vectoring and rotation about the center of gravity.
- [NASA launch / recovery sequence](https://www.nasa.gov/wp-content/uploads/2020/08/falcon9_launch_and_landing.pdf) — actual sequence of ascent, cutoff, staging and recovery burns.
- [NASA PACE staging account](https://science.nasa.gov/blogs/pace/2024/02/08/coming-up-falcon-9-max-q-main-engine-cutoff-and-stage-separation/) — main-engine cutoff precedes separation.
- [NASA rocket weight](https://www1.grc.nasa.gov/beginners-guide-to-aeronautics/rocket-weight/) — altitude-dependent inverse-square gravity.
- [U.S. Standard Atmosphere, 1976](https://ntrs.nasa.gov/citations/19770009539) — hydrostatic atmosphere reference; the implemented high-altitude tail is explicitly approximate.
- [MuJoCo force convention discussion](https://github.com/google-deepmind/mujoco/discussions/2350) and [simulation documentation](https://mujoco.readthedocs.io/en/stable/programming/simulation.html) — generalized forces versus Cartesian wrenches.
