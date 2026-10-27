# Rocket Mission Lab

Native Isaac Sim migration is in progress. See [native runtime, controls and validation boundaries](docs/26-native-isaac-migration.md). The shared Isaac installation is outside this checkout; the default dashboard page receives native telemetry without browser 3D rendering.

A local rocket flight simulator, mission dashboard, and reinforcement learning workbench. MuJoCo integrates the booster dynamics; React and Three.js render recorded telemetry. Vehicle parameters are generic approximations.

See the [23 October Isaac Sim browser experience & visual center](docs/29-isaac-sim-browser-experience.md) for the removal of the in-browser WebGL canvas, the real-time Isaac Sim Flight Deck, native RTX camera previews, 2D range radar, and full mission video player.

See the [23 October real-time fidelity, pad separation and markings revision](docs/28-realtime-separation-and-pad-fidelity.md) for 1:1 real-time playback synchronization, mandatory > 1 km pad separation, explicit TAKEOFF and LANDING circle stencils, and ISS Orbital Systems / NVIDIA Isaac Sim branding.

See the [21 October flight fidelity revision and executed evidence](docs/24-flight-fidelity-validation.md) for the latest dashboard, first-foot contact, staging, repeated retargeting and suborbital study. The older sections below describe the preceding baseline where they differ.

The [PC performance revision](docs/25-performance-optimization.md) adds a lighter default graphics mode, page-specific polling and one production HTTP server. Long training is currently stopped with checkpoints retained; starting it remains an explicit action.

## Run locally

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
cd frontend
npm ci
npm run build
cd ..
.venv\Scripts\python.exe scripts/serve.py
```

Open [Mission Control](http://127.0.0.1:5180/) and [API documentation](http://127.0.0.1:5180/api/docs). The production preview serves the built dashboard and API from one Python server; Node is only needed for building or development. For development use `.venv\Scripts\python.exe scripts/dev.py`. Close the launcher with Ctrl+C to stop its web servers. Training uses an independent hidden Windows worker (separate session on Unix). Node.js 22+ and Python 3.11 are the recorded development environment. Linux/macOS use `.venv/bin/python`.

## Mission controls

- Choose Landing, Takeoff, or Combined, set the launch X/Y, landing X/Y, and separation altitude, then select **Run flight**. Coordinates are local meters: X east, Y north, and a flat surface at Z = 0. They are not geographic coordinates.
- Landing starts in the air above the launch coordinates. Takeoff targets the vertical line above launch. Combined launches there, releases a generic 2.5 t unpowered upper stage, and returns the booster to the landing coordinates.
- Separation altitude is configurable from 80 to 1,500 m; site coordinates accept +/-10,000 m. These input limits are not a reachable flight envelope. Fuel, minimum thrust, sensor noise, and control limits can cause a requested mission to fail. Inspect its recorded outcome.
- The default flight plan transfers from [0, 0] to [1200, 400] with stage separation at 1,500 m (1.26 km surface distance, strictly exceeding the mandatory > 1 km pad separation constraint). **Standard Pad (>1.2 km)**, **Downrange (2.5 km)**, and **Long-Range (5.1 km)** provide instant presets.
- To divert during a flight, open **Mission plan** or the setup panel, enter a new landing X/Y, and choose **Retarget at T+…**. The applied target is the last confirmed one; takeoff has no landing pad to move, and a command after the flight ends is rejected. This feature requires the local engine and is never faked in offline replay.

The interface uses a light mission-control workspace with Overview, Flight deck, Telemetry, and Mission plan tabs, recorded-value KPI cards, charts, event log, and a compact retarget card. Terrain, vegetation, roads, facilities, ocean, HDR lighting, and shadows remain active; Balanced is the default quality. Launch and landing pads follow the applied coordinates, with prepared flat sites at Z = 0 separated by > 1,000 m and labelled with high-contrast TAKEOFF and LANDING stencils. The offshore environment remains available. Upper grid fins are articulated with roll/pitch/yaw aerodynamics. Four articulated landing legs feature body hinges, telescopic braces, footpads, and 0.6 m nominal nozzle clearance. The launch pad adds a flame trench, hold-down clamps, propellant lines, and a lattice service tower; the engine adds a bell, cooling tubes, stiffener rings, and actuator housings. See [rocket structure research and rendering limits](docs/22-rocket-structure.md).

## Camera and playback

- **6 Dedicated Aerospace Camera Views**:
  - `[1]` **Orbit**: 360° free inspection orbit around the booster.
  - `[2]` **Chase**: Dynamic velocity-aligned chase camera with aerodynamic lag.
  - `[3]` **Tower**: Optical tracking camera mounted on the launch service tower.
  - `[4]` **Engine**: Onboard perspective mounted on the interstage looking down at the gimbaling engine and grid fins.
  - `[5]` **Pad LZ-1**: Ground telephoto camera positioned at the touchdown landing pad.
  - `[6]` **Corridor**: Wide mission framing spanning launch site, trajectory arc, and recovery zone.
  - `[T]` **Top-down**: Overhead nadir view looking directly down onto the vehicle.
- **Controls & Navigation**: Drag to orbit, right-drag to pan, and scroll/pinch to zoom. Rotate/Pan switches the left-drag tool. Use WASD to fly through the scene, Q/E for down/up, and Shift to accelerate. Press `H` to toggle the telemetry HUD overlay, `Space` for play/pause, `F` to focus, and `R` to reset framing.
- **1:1 Real-Time Synchronization**: Playback clock operates in exact 1:1 physical wall-clock time at 1.0× speed, with 0.25×, 0.5×, 2×, and 4× rate multipliers.

The event buttons jump to actual recorded separation, engine cutoff, relight, and outcome. Scrubbing pauses playback. Throttle and gimbal drive the nozzle, colored plume, and exhaust history; engine-off segments do not show an active flame. These are illustrative rendering effects, not a combustion/CFD model. The released stage is drawn only from the integrated `upper_stage` state (gravity and drag, no thrust); runs without that state show no released stage. Upper-stage propulsion is not simulated.

## Training

The Training page supports individual PPO/SAC jobs and **Train all three missions**. Budgets are environment steps, not optimizer iterations. A three-mission campaign shares a total ceiling up to 100 million steps across alternating landing, takeoff, and combined blocks. It saves model/normalization snapshots, uses a curriculum for altitude and target displacement, and measures fixed development seeds. Landing and combined episodes also receive seeded mid-flight landing-target changes from `training.retarget_probability`, so the learned policy sees a moving goal during training rather than only in evaluation. It stops on exhausted budget or a measured plateau. Small MLP PPO runs on CPU; the renderer uses the GPU. SAC/CUDA remains a selectable single-job option.

A candidate with at least 254/256 development successes receives a separate 10,000-seed nominal evaluation, using a fresh seed range for each candidate. The nominal gate requires a 95% Wilson lower bound of at least 99%. This does not establish stress robustness or real-world safety. Training never substitutes a classical controller for a learned policy.

```powershell
# Explicitly bounded local campaign; logs/status/checkpoints stay on this machine.
.venv\Scripts\python.exe -m rocket_lab.campaign --id my-flight-study --steps 100000000 --block-steps 250000 --plan data/campaign-plan-2026-10-21.json
# After a campaign has stopped, continue its optimizer/normalization snapshots:
.venv\Scripts\python.exe -m rocket_lab.campaign --id my-flight-study --steps 100000000 --block-steps 250000 --resume
```

Use **Stop campaign & save** to stop the whole sequence. Stop flags also work at `data/campaigns/<id>/stop`; a running block saves at a callback. Status is in `/api/campaigns` and `/api/training`. Exact environment/RNG continuation across a restart is not promised. Model binaries are local under ignored `data/checkpoints/`; source pushes do not upload them.

## Validation and limits

The [October 21 validation record](docs/VALIDATION-2026-10-21.md) documents an earlier feature revision. The later light mission-control theme, surface-clipped plume, and mid-flight retarget polish were not part of those executed counts, so this README does not present them as already validated. Re-run the commands below for the current tree. The subsequent appearance restoration has its own [revision checks](docs/22-rocket-structure.md#revision-checks). Existing 10,000-flight results belong to earlier source/configuration snapshots and are presented as archived experiments. They do not qualify the new controller or custom targets. The new RL campaign is experimental and has not established reliable complete flight.

```powershell
.venv\Scripts\python.exe -m pytest tests -q
.venv\Scripts\python.exe scripts/validate_mission_plans.py --episodes 100
.venv\Scripts\python.exe scripts/validate_live.py
cd frontend
npm run test
npm run lint
npm run build
```

[Mission/physics contracts](docs/21-mission-controls.md) · [Research](docs/RESEARCH.md) · [Earlier implementation and experiment history](docs/archive/README-2026-10-20.md).
