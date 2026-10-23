# Native simulation acceptance and remaining validation

23 October 2026. This register defines project tests; it is not a claim of flight certification or compliance approval.

NASA-STD-7009B is used as a reference for separating implementation verification, real-world validation, input provenance and uncertainty. The project has no delegated NASA technical authority and no measured vehicle data for real-world validation. See [the standard](https://standards.nasa.gov/node/263).

| Capability | Acceptance evidence | Current boundary |
|---|---|---|
| Built-in rigid-body physics | Native PhysX advances position and quaternion; CUDA dynamics diagnostic reads the active solver setting | Generic booster and separate unpowered payload |
| Fuel and engine | Spool, gimbal slew, thrust torque and mass flow are tested; each body owns its own mass | Lumped inertia and fixed center of mass; no identified engine map |
| Gravity | Native vacuum drop compared with analytic acceleration and numerical integration error | Constant gravity for the research vehicle; inverse-square vertical gravity for the separate suborbital study |
| Launch support | Hold under gravity; release only after sustained positive thrust margin | One physical fixed restraint represents four displayed clamps |
| Payload release | Engine completes shutdown before the USD joint is disabled; release preserves velocity | Conservative cylinder collider inside the displayed fairing; no upper-stage propulsion |
| Target changes | Actual HTTP control test and seeded native flights | Targets outside physical reach must retain failure outcomes |
| Landing | First contact: speed below 2 m/s, tilt below 5 degrees, coordinate error at most 1 m | Research acceptance limits, not real vehicle operational limits |
| Settling | Four additional physical seconds with engine cutoff; final speed below 0.15 m/s, tilt below 5 degrees and position error at most 1 m | Fixed deployed feet; no articulated landing gear or structural flex |
| Pause and stepping | Real dashboard/backend/runner test: frozen paused clock and exactly 0.1 s single step | Timeline stop terminates the runner; resume uses the saved physical state |
| Rendering | Native RTX image exports; Flow must report active simulated volume blocks | PBR procedural geometry is an engineering prototype; Flow is illustrative combustion, not compressible exhaust CFD |
| Camera | Native viewport orbit/pan/zoom; explicit free/follow/site/vehicle modes | Manual camera assessment is separate from solver correctness |
| Transport | Latest-frame snapshot, 64 KiB packet cap, 16-command queue, WebSocket and HTTP validation | Loopback only; no remote flight-control service |
| Performance | Native page loads no Three canvas or Recharts; bounded 120-sample SVG plots; no automatic training/session startup | Isaac still has material native RAM/GPU cost; record process memory rather than promise a lightweight desktop app |
| ML | Existing observation/action contract, normalization and known local checkpoints are reusable; native PPO runner saves separate artifacts | Native policies remain unqualified; historical MuJoCo results do not transfer |

## Evidence provenance

New runner reports include the exact configuration, its SHA-256, a source-file SHA-256 manifest, seed, SDK/build, renderer, actual PhysX GPU flag and a source-change-during-run flag. A run with changed source files is exploratory until repeated with fixed files. Reports and exports are under `docs/evidence/2026-10-23/`; runtime logs and checkpoints stay outside source commits.

The first 8-flight native development sample passed 8/8, including four target changes. Its Wilson 95% interval is approximately 67.6% to 100%; eight successful trials do not establish a high reliability level. That initial sample used first-contact acceptance. The later runner adds physical settling and must be evaluated again under that stronger criterion.

The repeated 100 km separation study reached approximately 221 km during its ballistic coast and returned under native PhysX with engine cutoff and stable settling. These small numerical errors use exact simulated navigation and a generic deterministic vehicle configuration; they are not claims of measured navigation or real rocket precision.

## Required work before real-world claims

1. Identify a specific reference vehicle and obtain source-traceable mass, tank, center-of-mass, inertia, engine, gimbal, ignition and aerodynamic data.
2. Validate forces and moments against independent reference cases or measurements, including Mach-dependent coefficients, atmosphere/wind uncertainty and high-altitude reference-frame assumptions.
3. Add and qualify missing modeled hardware where required: articulated gear, compliance, RCS/grid-fin actuation, structural flex and fuel slosh. Do not disguise missing actuators with direct pose changes.
4. Complete timestep convergence, CPU/GPU comparisons, larger independent seed samples, sensor delay/noise and actuator/fuel/navigation fault drills. Report confidence intervals and all failures.
5. Review rendering against real reference footage, including materials, exposure, hot-gas appearance, lighting and camera behavior. Assess path-traced volume visibility separately from successful volume allocation.
6. Qualify native ML checkpoints with recorded training provenance and independent holdout evaluations before using them as evidence.

More training cannot substitute for missing vehicle data or a validated force model.
