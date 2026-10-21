# Rocket Mission Lab

A local rocket flight simulator, mission dashboard, and reinforcement learning workbench. MuJoCo integrates the booster dynamics; React and Three.js render recorded telemetry. Vehicle parameters are generic approximations.

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

Open [Mission Control](http://127.0.0.1:5180/) and [API documentation](http://127.0.0.1:8010/docs). For development use `.venv\Scripts\python.exe scripts/dev.py`. Close the launcher with Ctrl+C to stop its web servers. Training uses an independent hidden Windows worker (separate session on Unix). Node.js 22+ and Python 3.11 are the recorded development environment. Linux/macOS use `.venv/bin/python`.

## Mission controls

- Choose Landing, Takeoff, or Combined, set the launch X/Y, landing X/Y, and separation altitude, then select **Run flight**. Coordinates are local meters: X east, Y north, and a flat surface at Z = 0. They are not geographic coordinates.
- Landing starts in the air above the launch coordinates. Takeoff targets the vertical line above launch. Combined launches there, releases a generic 2.5 t unpowered upper stage, and returns the booster to the landing coordinates.
- Separation altitude is configurable from 80 to 1,500 m; site coordinates accept +/-10,000 m. These input limits are not a reachable flight envelope. Fuel, minimum thrust, sensor noise, and control limits can cause a requested mission to fail. Inspect its recorded outcome.
- The default plan transfers from [0, 0] to [80, 40] with separation at 400 m. **Return to launch** and **Separate site** provide quick presets.

The 3D scene uses a white plane and two small site markers. Coastline, grass, roads, water, rocks, facilities, terrain texture downloads, HDR lighting, and shadow passes are removed from the active renderer. Earlier scenery assets are retained for research and are not loaded by the scene.

## Camera and playback

Drag to orbit, right-drag to pan, and scroll/pinch to zoom. Rotate/Pan changes the left-drag tool. The +/- buttons offer precise zoom. Camera distance spans 0.5 m to 100 km; **Mission** frames the two sites and flight altitude. **Rocket** refocuses the booster. Turn Follow off to explore independently. Click the canvas and use WASD to move, Q/E down/up, and Shift to travel faster. Space toggles playback. The camera does not rewrite your orbit, zoom, or pan while following.

The event buttons jump to actual recorded separation, engine cutoff, relight, and outcome. Scrubbing pauses playback. Throttle and gimbal drive the nozzle, colored plume, and exhaust history; engine-off segments do not show an active flame. These are illustrative rendering effects, not a combustion/CFD model. The released stage follows an explicitly labelled ideal ballistic preview; upper-stage propulsion is not simulated.

## Training

The Training page supports individual PPO/SAC jobs and **Train all three missions**. Budgets are environment steps, not optimizer iterations. A three-mission campaign shares a total ceiling up to 100 million steps across alternating landing, takeoff, and combined blocks. It saves model/normalization snapshots, uses a curriculum for altitude and target displacement, and measures fixed development seeds. It stops on exhausted budget or a measured plateau. Small MLP PPO runs on CPU; the renderer uses the GPU. SAC/CUDA remains a selectable single-job option.

A candidate with at least 254/256 development successes receives a separate 10,000-seed nominal evaluation, using a fresh seed range for each candidate. The nominal gate requires a 95% Wilson lower bound of at least 99%. This does not establish stress robustness or real-world safety. Training never substitutes a classical controller for a learned policy.

```powershell
# Explicitly bounded local campaign; logs/status/checkpoints stay on this machine.
.venv\Scripts\python.exe -m rocket_lab.campaign --id my-flight-study --steps 100000000 --block-steps 250000 --plan data/campaign-plan-2026-10-21.json
# After a campaign has stopped, continue its optimizer/normalization snapshots:
.venv\Scripts\python.exe -m rocket_lab.campaign --id my-flight-study --steps 100000000 --block-steps 250000 --resume
```

Use **Stop campaign & save** to stop the whole sequence. Stop flags also work at `data/campaigns/<id>/stop`; a running block saves at a callback. Status is in `/api/campaigns` and `/api/training`. Exact environment/RNG continuation across a restart is not promised. Model binaries are local under ignored `data/checkpoints/`; source pushes do not upload them.

## Validation and limits

The October 21 redesign has executed backend, frontend, production build, local API, browser interaction, and fixed-seed mission pilot checks. See [the dated validation record](docs/VALIDATION-2026-10-21.md) for exact results and limits. Existing 10,000-flight results belong to earlier source/configuration snapshots and are presented as archived experiments. They do not qualify the new controller or custom targets. The new RL campaign is experimental and has not established reliable complete flight.

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
