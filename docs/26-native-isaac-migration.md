# Native Isaac runtime and dashboard

23 October 2026. The default workspace uses native NVIDIA PhysX and RTX. The web page is a lightweight telemetry/control console; it creates no WebGL canvas. **Legacy replay** retains the earlier MuJoCo renderer and evidence for comparison.

## Shared installation

Isaac Sim 6.2.0 is installed at `D:\AppInstalled\NVIDIA\IsaacSim\6.2.0`, outside the checkout and reusable by other projects. The official 10.53 GB archive was checked against NVIDIA's published MD5 `86dabd127e9e8c225c239b41a8e3909b`. The user explicitly accepted the NVIDIA agreement; acceptance is recorded alongside the shared installation. The launcher changes no global PATH, driver, firewall or Windows memory setting.

The RTX 5070 Ti and driver 617.42 have executed native CUDA PhysX successfully. PyTorch in this shared Python environment is **2.11.0+cpu**: the official CUDA-wheel download failed, so GPU ML is not claimed. Native PhysX/Warp CUDA execution is independent of that CPU inference/training fallback. Bundled CUDA, USD, Kit and scientific-library versions are retained. Optional vendor SimReady/authentication dependency warnings are not a clean `pip check` qualification; the exercised core runtime is qualified separately.

## Running and controlling a flight

Open the local dashboard on port 5180. Choose the mission, research/suborbital vehicle study, separate launch and landing coordinates, separation height and rendering mode. **Start native flight** starts one explicitly requested session, paused. Resume physics when the camera is ready.

The dashboard provides retargeting, engine cutoff, cutoff-before-release, manual throttle/two-axis gimbal, pause/resume, one 0.1-second physical step and stop. Camera choices include free orbit, vehicle following and site/vehicle framing. Native orbit/pan/zoom remain available. Experimental conditions expose the fixed seed, physics timestep, generic parameter variation, navigation noise and optional CUDA dynamics.

No native session or large training campaign starts on page load. RTX real-time is the normal visual mode; path tracing and NVIDIA Flow exhaust are explicit choices. Optional synthesized engine audio is loaded only after activation and follows engine telemetry with distance delay from the ground origin. It is not a recording of a real rocket.

```powershell
# Native viewport; add --start-paused to set up the camera first.
powershell -File scripts/run_isaac.ps1
powershell -File scripts/run_isaac.ps1 -PathTracing -Flow --start-paused

# Physics, transport, analytic gravity and separation diagnostics.
powershell -File scripts/diagnose_isaac.ps1
powershell -File scripts/diagnose_isaac.ps1 -GpuPhysics
powershell -File scripts/diagnose_isaac.ps1 -Visual -Flow

# One reproducible target change, with honest physical outcomes.
powershell -File scripts/run_isaac.ps1 -Headless --retarget-at 30 120 -30

# Native development sample with seeded variations and noisy navigation.
powershell -File scripts/run_isaac.ps1 -Headless --randomized --sensor-noise --qualification-runs 8

# Explicit bounded PPO study. Its checkpoint is not automatically qualified.
powershell -File scripts/run_isaac.ps1 -Headless --train-steps 100000
```

Pass `-IsaacRoot` to the PowerShell wrapper or set `ROCKET_ISAAC_ROOT` for the dashboard launcher to use a different shared installation. `--full-experience` restores NVIDIA's full base application for SDK troubleshooting. The reduced experiences under `config/` are the normal launch path.

## Physics and control architecture

`rocket_lab/isaac/physics.py` creates native USD rigid bodies, inertias, collision shapes, ground contact and live fixed joints. PhysX owns pose, velocity, contact and free 6-DoF motion. This does not integrate MuJoCo and copy its animation into Isaac. Fuel burn uses `F = mdot Isp g0`; engine spool and gimbal slew precede the applied force and nozzle visualization.

A launch restraint holds the vehicle until a sustained positive thrust margin. Payload release waits for complete engine shutdown, disables the connector and restores inter-body collision. A generic 12 kN, 0.2 s pusher applies a balanced force pair with corresponding connector moments; it never injects a position or velocity jump. The diagnostic checks linear impulse and angular momentum against actual native inertia readback. Live actor states are preserved when the USD topology changes so an actor rebuild cannot restore stale velocity defaults.

A full physical reset clears previous contact/constraint state between episodes. The runner continues four physical seconds after a successful touchdown, shuts down the engine and verifies upright, low-speed settling. Pause, stepping and stop remain effective during that contact verification. A target command changes the goal and landing marker, not the vehicle state. Unreachable targets retain failure outcomes.

`rocket_lab/isaac/guidance.py` adapts the existing classical controller for compound payload inertia and estimates engine variation from measured motion. Its prediction model is separate from the physical engine parameters. A single gimballed engine is underactuated: six motion degrees of freedom do not supply six independent control actuators.

`rocket_lab/envs.py` retains the 21-element policy observation and three-action contract, rewards and mission phases through an injected physics factory. `rocket_lab/isaac/policy.py` loads known local PPO/SAC checkpoints and saved normalization without creating a MuJoCo world. Transferred policies remain experimental. Native PPO artifacts and normalization are saved separately under `data/isaac/`. A 64-step native training/checkpoint smoke test has executed; it is not a trained landing policy or an Isaac Lab batch benchmark.

## Resource use and transport

The reduced headless experience loaded 95 extensions versus 308 in the full base diagnostic. Sampled private memory during flight was approximately 2.7 GB versus 6.0 GB in the full experience. These are point samples, not peak or isolated-system benchmarks. The visual experience retains the native camera, RTX and USD inspection tools while omitting unrelated robot planners and sensor suites. Headless mode renders no frames and creates no Flow effects. CUDA dynamics is explicit because CPU physics can be cheaper for a two-body scene.

The native dashboard entry bundle is approximately 243 KB before gzip; archived charts and Three.js load only when opened. Native plots retain at most 120 samples. Hidden tabs suspend telemetry polling and audio processing. The socket server holds one latest frame, caps packets at 64 KiB and queues at most 16 commands. Its I/O runs on a background thread. `/api/native/status`, `/api/native/start`, `/api/native/command` and `/api/native/stream` bridge the loopback service. Dashboard-owned session identity survives backend restarts, preventing duplicate startup while the existing process is still loading or stopping.

## Evidence and boundaries

Inspect reports and native render exports under `docs/evidence/2026-10-23/`. New reports include the configuration, configuration SHA-256, source manifest, seed, SDK/build, renderer, actual GPU-dynamics setting and source-change flag. Failed exploratory samples are retained separately.

See [the acceptance register](27-native-acceptance.md) for criteria and remaining validation. This is a generic research vehicle with approximate drag/inertia, fixed deployed gear and an unpowered payload. It has no identified Mach-dependent aerodynamic table, fuel slosh, moving center of mass, structural flexibility, re-entry heating, upper-stage propulsion or validated RCS. Accurate equations and successful simulation tests do not establish real vehicle accuracy or certification.

## Simulator choice and sources

There is no universally perfect rocket simulator. Isaac supplies native rigid-body/contact physics and RTX graphics. JSBSim specializes in flight dynamics; Basilisk specializes in spacecraft dynamics. The vehicle data, force model, numerical verification and validation against independent measurements determine credibility.

- [NVIDIA downloads](https://docs.isaacsim.omniverse.nvidia.com/6.2.0/installation/download.html)
- [NVIDIA hardware/driver requirements](https://docs.isaacsim.omniverse.nvidia.com/6.2.0/installation/requirements.html)
- [Native physics fundamentals](https://docs.isaacsim.omniverse.nvidia.com/latest/physics/simulation_fundamentals.html)
- [Core API migration](https://docs.isaacsim.omniverse.nvidia.com/6.2.0/migration_guides/isaac_sim_6_0/core_api_to_core_experimental.html)
- [NVIDIA Flow](https://docs.omniverse.nvidia.com/extensions/latest/ext_fluid-dynamics/using.html)
- [JSBSim](https://jsbsim-team.github.io/jsbsim-reference-manual/)
- [Basilisk](https://hanspeterschaub.info/basilisk/)
- [NASA model/simulation credibility standard](https://standards.nasa.gov/node/263)
