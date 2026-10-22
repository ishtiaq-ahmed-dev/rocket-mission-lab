# Mission geometry, rendering, and training contracts

Updated 21 October 2026.

## Coordinates and targets

`FlightPlan` contains `launch: [x, y]`, `landing: [x, y]`, and `separation_altitude`. The Pydantic request boundary rejects nonfinite/out-of-range values and extra fields. All values are local SI coordinates on Z = 0, not GPS. Surface elevation remains fixed for the existing contact approximation; rendered coastal pads and their prepared ground use that same Z = 0 plane.

The request travels through `/simulate` -> `configure_flight` -> `RocketEnv` -> `ClassicalController` or the selected learned policy -> recorded `RunMeta.flight_plan` -> frontend markers and telemetry. Launch and landing are distinct phase targets. Takeoff checks lateral error against launch; landing checks against the destination. Custom mission configurations are copied, never written into the baseline YAML.

The fixed-scale position observations use launch-relative coordinates. Relative goal features remain in the observation. This removes absolute translation from policy inputs while retaining actual world coordinates in telemetry and sensor estimates. Training-only target/altitude curricula do not change evaluation goals.

### In-flight retargeting

`POST /simulate` accepts an optional `retarget: {time, landing}`. The engine reruns the deterministic flight from the start and applies the command at the first physics step at or after `time`, so the result is a recorded, reproducible branch rather than an interactive client-side edit. `RunMeta.retargets` records the applied event (`t`, previous target, new target), `RunMeta.flight_plan.landing` reflects the final target, and the run ID includes a retarget hash. A single request carries one mid-flight command; repeat the request with the newly recorded telemetry if another change is needed.

Landing and combined missions accept retargets; takeoff has no landing target and is rejected. Negative or nonfinite times and out-of-range coordinates are rejected, as is a command scheduled after the recorded flight ends. The mission timeout is extended to 300 s for a divert. Classical guidance clears its plan, holds a shallow descent while it translates, and resumes terminal descent near the new site; learned policies receive the new target in their observation and are not given hand-authored divert commands. A long divert can still exhaust propellant or miss the pad, and accepted coordinates are not a reachability guarantee.

For training, `training.retarget_probability`, `retarget_max_offset`, and `retarget_min_altitude` sample at most one seeded command per landing episode when the environment is in training mode; the command is applied only if the vehicle is still above `retarget_min_altitude` when its delay elapses. Sampling uses its own seeded stream, so it does not disturb the state and sensor-noise draws shared with evaluation; replays remain deterministic. Evaluation environments never auto-retarget. The dashboard's **Retarget** action requires the local API; offline telemetry playback cannot create new flights.

## Booster dynamics and separation

MuJoCo integrates the booster as a generic rigid body under gravity, gimballed thrust, lever-arm torque, variable propellant mass, drag, wind, and sensor noise. Thrust consumes fuel through effective specific impulse. The classical controller uses bounded lateral references, a simple state estimator, descent clearance during a transfer, and engine-off commands when the requested thrust is below the physical minimum. The lower final descent reference improves touchdown speed under noise. These are approximate feedback controls, not a real launch vehicle flight computer.

A combined mission attaches a generic 2,500 kg upper-stage mass during ascent. At the selected altitude, successful ascent checks trigger its removal from the returning booster. Separation preserves position, attitude, velocity, fuel, and clock; there is no ejection impulse. A timestamped separation event records released mass and state. Booster inertia scales with mass as an approximation; payload center-of-mass migration and a full two-body flexible vehicle are not modeled.

The released stage is a **visual ballistic preview** under constant gravity, with no powered upper-stage flight, aerodynamic integration, or collision response. Its drawing is hidden after it reaches the surface. The booster is the dynamically integrated object. Stage separation must not be described as an orbital launch simulation.

## Reachability and outcomes

Accepted coordinate and altitude ranges are input bounds. They do not certify reachability. A long transfer can exhaust the landing reserve. Low separation, strong wind, thrust loss, or noise can produce a crash or missed pad. Actual speed, tilt, offset, and failure reason remain visible. The default controller has measured failures in the current fixed-seed combined pilots; see the dated validation record.

## Graphics and camera

The coastal world remains active: terrain, vegetation, roads, facilities, ocean, local HDR environment, and shadows. The flight workspace uses a light mission-control theme with a chart-first overview and separate Overview, Flight deck, Telemetry, and Mission plan tabs. Both pads follow the applied plan; terrain earthworks and vegetation exclusion prevent ground or grass through the pads. Upper grid fins are omitted by request. Four fixed-length leg shells rotate about lower hinges, with telescoping braces and articulated footpads. The fully deployed soles match local Y = -20 m and the central nozzle retains 0.6 m clearance. The launch pad adds a flame trench, four hold-down clamps, propellant lines, and a lattice service tower with swing arms. These are rendered mechanisms; leg compliance, foot friction and tip-over are not separately integrated. See [the structure research](22-rocket-structure.md).

The nozzle is a rendered bell with an inner liner, exit rim, stiffener rings, cooling tubes, and actuator housings. Plume rendering retains the axisymmetric shell and actual throttle/gimbal inputs. A smoothed ignition/cutoff power and altitude-driven plume expansion keep the flame continuous through throttle transitions. The plume length is truncated by the local surface clearance, so the flame stops at the pad or terrain during final descent instead of passing through it. Smoke ages are deterministic from recorded time, making pause/scrub repeatable, and the emission follows the gimballed nozzle exit. Plume/particles and synthesized audio are illustrative, not solvers for exhaust gas flow or combustion acoustics.

The on-demand canvas renders during playback, camera movement, or UI changes. Pausing stops the playback clock. The selected output quality controls pixel ratio; Balanced defaults to 1. Camera controls permit orbit, screen-space pan, cursor zoom, two-finger touch, +/- zoom, keyboard translation, independent/free view, mission framing, and follow translation without overwriting user framing. Camera distance is 0.5 m to 100 km. The camera stays above sampled coastal terrain, the water surface, and the landing deck. Export stills use a separate 3840 x 2160 render request and restore the preview buffer afterward; latest 4K export has not been visually qualified.

## Experiment identity

New run IDs include the dynamics source digest as well as configuration, seed, mission, and controller/checkpoint. Custom runs are indexed and retrievable through the same API as baseline runs. Stage events are additive optional fields in schema 1.1; archived 1.0/1.1 telemetry remains readable. Source/config identities prevent overwriting an older recorded run with a newly tuned controller. Historical result files remain archived; the Results current view requires matching dynamics and configuration. Custom plans appear under their configuration hashes.

Automatic learned-policy selection first looks for compatible mission geometry and physical configuration. A directly trained combined policy is preferred when available; legacy two-policy phase chaining remains available before one exists. Explicit checkpoint playback remains available and is labelled experimental. A trained actor does not inherit another actor's reliability evidence.

## Three-mission campaign

The total budget is shared across alternating PPO mission blocks. Each block resumes actor, critic, optimizer and normalization snapshots with recorded lineage. It does not promise exact RNG or environment restoration. The supervisor can stop/save and resume from completed block state. On Windows, the API launches an independent hidden WMI worker with its own log; Unix uses a separate session. A real API dispatch and campaign survival across web-server restart were observed. Failed jobs record diagnostics. Checkpoint/status writes are atomic, disk availability is checked, and episode history is bounded for long runs.

Fixed 256-seed development samples drive selection. Plateau detection considers successes, physical errors, and curriculum advancement. Candidates reaching 254/256 trigger a 10,000-seed nominal gate; held-out seed ranges differ across candidates. A 99% Wilson lower bound passes that nominal gate, while stress robustness remains a separate requirement. A 100-million-step ceiling is not a performance promise. The dashboard exposes actual counters and failed gates.

## Primary references

- [NASA Glenn: rocket thrust equations](https://www.grc.nasa.gov/WWW/K-12/BGP/rktthsum.html): effective thrust and propellant-flow context; nozzle thermodynamics are not integrated here.
- [Three.js: OrbitControls](https://threejs.org/docs/pages/OrbitControls.html): orbit/pan/dolly, distance bounds, and cursor zoom.
- [Stable-Baselines3: RL tips](https://stable-baselines3.readthedocs.io/en/master/guide/rl_tips.html): evaluation separation, variability, and reproducibility limits.
