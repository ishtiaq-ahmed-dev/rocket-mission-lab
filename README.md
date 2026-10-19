# Rocket Mission Lab

A local 3D rocket landing and takeoff research lab. MuJoCo runs the rigid-body physics; React/Three.js displays recorded telemetry. Classical controllers and pure PPO/SAC policies use the same physics.

**Open the running interface:** http://127.0.0.1:5180/  
**API documentation:** http://127.0.0.1:8010/docs

## Current qualification

The simulator, classical baselines, replay interface, training jobs, checkpoint library and evaluation tooling are implemented. Real RL training is an ongoing experiment, not a solved flight controller. Early PPO and SAC pilot evaluations had zero successes; they remain visible in the results. Full batch results appear only after an actual evaluation completes.

Latest local checks: 33 backend tests and 19 frontend tests passed, as did TypeScript, lint and the production build. The user confirmed that dragging rotates the camera during playback. Browser automation remains blocked by tool security policy; the latest terrain, sound quality, 4K image export, responsive layout and sustained frame rate still need visual/listening checks. Mac M1 has not been tested on physical Apple hardware.

The classical L4 nominal landing batch completed 10,000/10,000 observed successes under configuration `15b9d2a4ad7e8f68` on seeds 10000–19999; the Wilson 95% lower bound is 99.9616%. This is a scoped simulation result, not certainty. Fourfold-noise stress failed all 32 pilot episodes. The state-potential-v3 PPO run completed 1,001,472 training steps, reached curriculum difficulty 0.20, and still failed all 20 full-distribution development seeds. A separately logged continuation restores that checkpoint for four million additional steps. See the Training tab for its current state.

## Start on this Windows PC

The project `.venv` reuses the already installed CUDA PyTorch through `--system-site-packages`. Additional simulation packages live inside the virtual environment. No other project's files or services are required.

```powershell
cd 'D:\AI SIDE PROJECTS\ROCKET LANDER + LAUNCHER'
.\.venv\Scripts\Activate.ps1
python scripts/dev.py
# or: .\dev.ps1
```

If these ports are already serving Rocket Mission Lab, use the running interface. Do not stop another project's service to free a port. For a clean install:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
# Choose a current CUDA build from the official PyTorch installation selector.
python -m pip install torch --index-url https://download.pytorch.org/whl/cu128
python -m pip install -r requirements.txt
cd frontend
npm ci
cd ..
python scripts/bootstrap.py
python scripts/dev.py
```

Verify GPU support by running `python scripts/bootstrap.py`. `data/runtime.json` records versions, CUDA architectures, GPU name and the result of a real CUDA matrix multiplication. The original validated machine used Python 3.11.9, PyTorch 2.12.0.dev20260408+cu128, CUDA 12.8, driver 617.42, RTX 5070 Ti 16 GB, MuJoCo 3.16.0, SB3 2.8.0, Gymnasium 1.2.3 and CVXPY 1.9.3. This installed nightly build is recorded for provenance, not prescribed as a universally available wheel.

## Mac M1 / Linux

For replay alone, install Node.js 22+ and run `npm ci && npm run dev` inside `frontend`. Without a backend, the four real recorded classical landing replays are available. Backend-dependent missions and training show a clear error rather than invented data.

For CPU simulation and small training tests:

```sh
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cd frontend && npm ci && cd ..
python scripts/bootstrap.py
make dev
```

Apple Metal optimization is not configured. Use `--device cpu` on Apple hardware. Headless MuJoCo requires no native viewer or graphics context.

## Explore the interface

- **Flight lab:** select Landing, Takeoff or Combined; choose Classical or RL and a level. Run a simulation or load a saved checkpoint. Drag to rotate in every camera mode, scroll to zoom, and right-drag to pan. Following preserves manual angles; Reset camera restores framing. Space toggles playback; the time slider scrubs; playback speed ranges from 0.25× to 4×.
- **Compare:** overlay Level 1 against the current flight, or RL against classical, on the same start seed. Solid body and translucent comparison share the same clock.
- **Learning journey:** plays the four real controller versions or checkpoint slots in order. RL slots are labeled Early, Intermediate, Later and Best measured. Best measured can still fail.
- **Training:** start PPO or SAC, choose the device and step budget, inspect live progress and development evaluations, stop with a checkpoint, and replay a saved policy.
- **Results:** inspect sample counts, Wilson confidence intervals, speed, offset and failure breakdowns. Full evaluation and pilot samples are labeled separately.
- **Field notes:** inspect model assumptions, runtime versions and research links.
- **Recording view:** hides dashboard chrome; Escape exits. Capture with your own recorder. No guaranteed frame rate or video encoder is included.
- **Graphics and sound:** Ultra is the default, with 4K terrain maps, 0.5 m cells in the central 360 m square, and 1 m cells across the surrounding 960 m coastal range. Balanced and High reduce detail. 4K mode fits a supersampled canvas toward a UHD-sized budget; the measured buffer resolution and FPS are displayed. The download icon renders a separate 3840×2160 scene PNG. It excludes the HTML dashboard. The speaker button enables locally synthesized, telemetry-driven engine/wind sound. Sound starts muted.
- **Trajectory:** Off by default. Flown shows the actual recorded path up to the playback time; Full shows the complete recording. Neither line is a guidance prediction.

## Training and evaluation

```sh
python -m rocket_lab.train --mission landing --algorithm PPO --steps 1000000 --device cpu
python -m rocket_lab.train --mission landing --algorithm SAC --steps 1000000 --device cuda
python -m rocket_lab.train --mission takeoff --algorithm PPO --steps 1000000
python -m rocket_lab.train --mission takeoff --algorithm SAC --steps 1000000
python -m rocket_lab.train --mission landing --algorithm PPO --steps 4000000 --resume JOB__step-001001472
python -m rocket_lab.evaluate --mission landing --level 4 --episodes 10000
python -m rocket_lab.evaluate --mission landing --level 4 --episodes 10000 --scenario gusts
python -m rocket_lab.evaluate --mission landing --checkpoint JOB__step-000100000 --episodes 10000
python -m rocket_lab.reinforce --episodes 400
python -m tensorboard.main --logdir data/tensorboard --host 127.0.0.1 --port 6006
```

Default checkpoint milestones are 10k, 100k, 500k, 1M, 5M and 10M when within the requested budget, plus initial, quarter-budget, half-budget, three-quarter-budget and final snapshots. PPO finishes its rollout, so the final count may exceed the requested steps. Every checkpoint has `model.zip`, `normalize.pkl` and measured metadata. New jobs also retain a config snapshot. SAC inference avoids allocating a training replay buffer; exact SAC resume with replay is not implemented.

Current curriculum begins at difficulty 0, approximately 3 m above the pad, and widens by 0.025 after 30 successes in a rolling 40-episode window. State-only observations use fixed physical scales; reward normalization is saved. They include position, velocity, quaternion, angular velocity, fuel, clock and relative goal. The policy receives no controller hints or expert demonstrations. Sensor noise retains its physical magnitude despite changed feature scales. Classical guidance also consumes noisy position/velocity/rate estimates. The final controller uses modeled drag feedforward; its wind knowledge is idealized and documented.

PPO continuation restores network/optimizer state, normalization, step count and curriculum difficulty when mission, algorithm and configuration hash match. It starts fresh environment/RNG trajectories and is not bitwise continuation. SAC resume is rejected until replay-buffer persistence is implemented. Old checkpoint replay maps current observations back to the checkpoint's recorded feature scale.

Development checkpoint evaluations use fixed seeds beginning at 20000. Full qualification defaults to 10000–19999. Initial exploratory runs used 12 development seeds beginning at 10000 and are not independent qualification data. Some initial pilot evaluations preceded reward tuning; compare their physical outcomes, not raw reward magnitude across reward versions.

Pick algorithms from measured success and reward at comparable configurations and seed pools. The UI selects the best available measured checkpoint, then chronological checkpoint slots. If every candidate fails, the selected best candidate still fails. Do not interpret this selection as flight readiness.

## Tests

```sh
make test
# Windows without make:
python scripts/check.py
# When a supported browser and local services are available:
make test-browser
```

Tests cover analytic free fall, vacuum energy and momentum, propellant flow, minimum throttle, fuel exhaustion, deterministic seeds, Gymnasium checks, every termination reason, controller improvement, API validation, shared schema, safe training dispatch, interpolation and parser rejection. Playwright tests are supplied but were not executed after browser policy blocked observation. The successful REINFORCE lesson is an actual training smoke test on CartPole, not proof of rocket convergence.

## Layout

```text
config.yaml                 approximate physical, mission, reward and training parameters
rocket_lab/physics.py       headless MuJoCo dynamics
rocket_lab/envs.py          Gymnasium landing/takeoff/combined phase manager
rocket_lab/controllers.py  PID-like feedback, convex guidance and LQR baseline
rocket_lab/train.py         PPO/SAC jobs and checkpoint evaluations
rocket_lab/reinforce.py     single-file educational policy gradient
rocket_lab/evaluate.py      fixed seeds, Wilson interval, CSV/Markdown results
rocket_lab/api.py           FastAPI, simulation and training endpoints
frontend/src/              React/TypeScript, R3F scene, charts and controls
shared/telemetry.schema.json versioned Pydantic JSON Schema
data/runs/                 actual telemetry and metadata
data/checkpoints/          local model weights and normalization (Git ignored)
data/jobs/                 job heartbeat, config and error logs (Git ignored)
data/results/              measured aggregate results and per-seed CSV
docs/                      component explanations, formulas and interview questions
scripts/                   launch, bootstrap and verification commands
```

## Approximate and unverified

The vehicle resembles a generic slender reusable booster. Values are not official Falcon 9 specifications. One rigid body, isotropic quadratic drag, constant gravity, exponential atmosphere and lumped mass/inertia omit lift, grid-fin forces, thrust transients, center-of-mass migration, slosh, heating, structural loads and contact stability. Touchdown uses a center-of-mass height plane, not tilted landing-leg collision geometry. Fuel burn is mass-flow consistent; it is not a thermochemical engine simulation.

Takeoff is a short vertical ascent to 400 m with a velocity target, not orbital launch. Combined mode switches policies/controllers at a physical phase boundary and does not reset the vehicle state. Ship mode changes appearance only. The convex planner relaxes minimum thrust and constant mass; infeasible solves fall back to documented feedback. L4 uses LQR plus descent feedforward instead of claiming a globally optimal flight.

Terrain, scanned rocks, vegetation and facilities share a visual height function, with level road/foundation areas and stitched mesh resolutions. The pad surface sits 7.5 cm above the approximate physics plane. This visual ground is independent of MuJoCo's flat contact plane. Licensed CC0 scan/HDR/PBR assets are bundled locally; see `frontend/public/assets/ATTRIBUTION.md`. The environment is an illustrative coast, not a surveyed launch site. A 4K buffer does not by itself establish photorealism.

The UI has responsive styles and keyboard controls, but screen-reader, Mac, sustained frame-rate and video-production validation are pending. The completed classical nominal batch does not close every-controller/checkpoint 10,000-seed evaluation, robustness or final RL performance gates.

## What I'd tell a skeptic

This demonstrates simulation, guidance, RL experimentation and evidence handling. A pleasing replay is not proof of safe control. Success on one seed is not a reliability rate, and zero observed failures is not certainty. A policy checkpoint is not an aerospace qualification. Inspect the per-seed CSV, model normalization, config version, training curve and failure modes before making a performance claim.

Research sources: [docs/RESEARCH.md](docs/RESEARCH.md). Major decisions and discovered failure modes: [DECISIONS.md](DECISIONS.md).
