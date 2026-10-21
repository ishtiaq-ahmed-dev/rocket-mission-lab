# Mission geometry, rendering, and training contracts

Updated 21 October 2026.

## Coordinates and targets

`FlightPlan` contains `launch: [x, y]`, `landing: [x, y]`, and `separation_altitude`. The Pydantic request boundary rejects nonfinite/out-of-range values and extra fields. All values are local SI coordinates on Z = 0, not GPS. Surface elevation is intentionally fixed to match the white plane and existing contact approximation.

The request travels through `/simulate` -> `configure_flight` -> `RocketEnv` -> `ClassicalController` or the selected learned policy -> recorded `RunMeta.flight_plan` -> frontend markers and telemetry. Launch and landing are distinct phase targets. Takeoff checks lateral error against launch; landing checks against the destination. Custom mission configurations are copied, never written into the baseline YAML.

The fixed-scale position observations use launch-relative coordinates. Relative goal features remain in the observation. This removes absolute translation from policy inputs while retaining actual world coordinates in telemetry and sensor estimates. Training-only target/altitude curricula do not change evaluation goals.

## Booster dynamics and separation

MuJoCo integrates the booster as a generic rigid body under gravity, gimballed thrust, lever-arm torque, variable propellant mass, drag, wind, and sensor noise. Thrust consumes fuel through effective specific impulse. The classical controller uses bounded lateral references, a simple state estimator, descent clearance during a transfer, and engine-off commands when the requested thrust is below the physical minimum. The lower final descent reference improves touchdown speed under noise. These are approximate feedback controls, not a real launch vehicle flight computer.

A combined mission attaches a generic 2,500 kg upper-stage mass during ascent. At the selected altitude, successful ascent checks trigger its removal from the returning booster. Separation preserves position, attitude, velocity, fuel, and clock; there is no ejection impulse. A timestamped separation event records released mass and state. Booster inertia scales with mass as an approximation; payload center-of-mass migration and a full two-body flexible vehicle are not modeled.

The released stage is a **visual ballistic preview** under constant gravity, with no powered upper-stage flight, aerodynamic integration, or collision response. Its drawing is hidden after it reaches the surface. The booster is the dynamically integrated object. Stage separation must not be described as an orbital launch simulation.

## Reachability and outcomes

Accepted coordinate and altitude ranges are input bounds. They do not certify reachability. A long transfer can exhaust the landing reserve. Low separation, strong wind, thrust loss, or noise can produce a crash or missed pad. Actual speed, tilt, offset, and failure reason remain visible. The default controller has measured failures in the current fixed-seed combined pilots; see the dated validation record.

## Graphics and camera

The active world contains one white plane, two site markers, three simple lights, the rocket, and optional telemetry trails/ghosts. It does not load the retained terrain assets, vegetation, roads, facilities, ocean, or HDR environment. Shadow maps are disabled. Vehicle parts use moderate geometry budgets, a local 1K canvas texture, and ordinary materials. Plume rendering uses an axisymmetric shell with normal alpha blending so its color remains visible on white. Smoke ages are deterministic from recorded time, making pause/scrub repeatable. Plume/particles are illustrative, not a solver for exhaust gas flow.

The on-demand canvas renders during playback, camera movement, or UI changes. Pausing stops the playback clock. The selected output quality controls pixel ratio; Balanced defaults to 1. Camera controls permit orbit, screen-space pan, cursor zoom, two-finger touch, +/- zoom, keyboard translation, independent/free view, mission framing, and follow translation without overwriting user framing. Camera distance is 0.5 m to 100 km. The camera stays above the white surface. Export stills use a separate 3840 x 2160 render request and restore the preview buffer afterward; latest 4K export has not been visually qualified.

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
