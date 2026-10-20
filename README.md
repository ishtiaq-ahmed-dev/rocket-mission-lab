# Rocket Mission Lab

A local 3D rocket landing and takeoff research lab. MuJoCo runs the rigid-body physics; React/Three.js displays recorded telemetry. Classical controllers and pure PPO/SAC policies use the same physics.

**Open the running interface:** [Rocket Mission Lab](http://127.0.0.1:5180/)

**API documentation:** [Local API docs](http://127.0.0.1:8010/docs)

## Current qualification

The simulator, classical baselines, replay interface, training jobs, checkpoint library and evaluation tooling are implemented. Real RL training is an ongoing experiment, not a solved flight controller. Early PPO and SAC pilot evaluations had zero successes; they remain visible in the results. Full batch results appear only after an actual evaluation completes.

Latest checks: 32 frontend tests, TypeScript, lint and the production build passed. The full backend suite passed 55 tests, including API transport, training dispatch, physics, continuation, selection, rewards and actual replay checkpoint attribution. Production localhost HTTP checks pass for the current source. The user confirmed rotation earlier, then reported a 3D startup fallback after the performance update. The scheduler host-call binding and generic fallback were corrected; actual scene recovery still needs confirmation. Browser automation remains blocked by tool security policy; the latest terrain, sound quality, 4K image export, responsive layout and sustained frame rate still need visual/listening checks. Mac M1 has not been tested on physical Apple hardware.

The classical L4 nominal landing batch completed 10,000/10,000 observed successes under configuration `15b9d2a4ad7e8f68` on seeds 10000–19999; the Wilson 95% lower bound is 99.9616%. This is a scoped simulation result, not certainty. Fourfold-noise stress failed all 32 pilot episodes. The v13 takeoff checkpoint at 2,761,136 lineage steps scored 254/256 on the full 400 m development mission (Wilson 95% interval 97.20–99.79%); two runs missed the pad-radius constraint. Its separate frozen nominal batch completed 9,836/10,000 successes (98.36%; Wilson interval 98.0919–98.5910%): 89 pad misses, 65 tilt failures and 10 speed failures. Stress pilots expose further limits, including 0/32 with 20% thrust loss. Landing remains weaker: the v10 continuation at 8,908,272 lineage steps scored 65/256 (25.39%; interval 20.45–31.06%), compared with 45/256 for its earlier actor. Conservative v15 updates and the v16 ground-speed reward did not beat it in the completed trials. A separate frozen landing batch is running; a five-million-step continuation uses larger 256-episode checkpoint samples. Training curves, fixed first-seed failures, and explicitly selected successful examples are available in the Training page. See [the iteration evidence](docs/MODEL-ITERATION-2026-10-19.md) and `data/results/`; development samples do not establish reliability.

## Start on this Windows PC

The project `.venv` reuses the already installed CUDA PyTorch through `--system-site-packages`. Additional simulation packages live inside the virtual environment. No other project's files or services are required.

```powershell
cd 'D:\AI SIDE PROJECTS\ROCKET LANDER + LAUNCHER'
.\.venv\Scripts\Activate.ps1
npm --prefix frontend run build
python scripts/serve.py
# For hot-reload development: python scripts/dev.py
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

- **Flight lab:** select Landing, Takeoff or Combined; choose Classical or RL and a level. Run a simulation or load a saved checkpoint. Use Rotate or Pan to choose what left-drag does; scroll zooms toward the cursor. Shift-drag or right-drag also pans in Rotate mode. Follow can be disabled independently. Following preserves manual angles; Reset camera restores framing. Space toggles playback; the time slider scrubs; playback speed ranges from 0.25× to 4×.
- **Compare:** overlay Level 1 against the current flight, or RL against classical, on the same start seed. Solid body and translucent comparison share the same clock.
- **Learning journey:** plays the four real controller versions or checkpoint slots in order. RL slots are labeled Early, Intermediate, Later and Best measured. Best measured can still fail.
- **Training:** start PPO or SAC, choose the device and step budget, inspect live progress and development evaluations, stop with a checkpoint, and replay a saved policy.
- **Results:** inspect sample counts, Wilson confidence intervals, speed, offset and failure breakdowns. Full evaluation and pilot samples are labeled separately.
- **Field notes:** inspect model assumptions, runtime versions and research links.
- **Recording view:** hides dashboard chrome; Escape exits. Capture with your own recorder. No guaranteed frame rate or video encoder is included.
- **Graphics and sound:** High is now the default: 4K ground textures, 2 m central cells, 4 m coastal cells, 24 m distant cells and 1.25x pixel ratio. Ultra and 4K are explicit heavier options. The production preview renders on demand while paused; playback defaults to a 60 FPS budget with 30/120/144 options under advanced controls. Water uses environment reflection in one scene color pass. Rocks use distance-based detail, grass skips its shadow pass, and grid-fin bars are batched. The download icon still exports a 3840x2160 scene PNG. Sound starts muted and requires the speaker button. Actual GPU usage and sustained FPS are unqualified after this change.
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

Pick algorithms from measured success and physical outcomes at comparable configurations and seed pools. The frontend compares checkpoints with identical vehicle/world/mission settings, using each checkpoint's largest full-task sample and Wilson lower bound, followed by sample size, rate and landing physical error; it excludes raw reward across profiles. Ascent speed magnitude is not treated as landing impact speed. It supplies the chosen ID explicitly to the API, then uses chronological earlier slots from that job. Direct API default selection still follows the baseline family; use an explicit checkpoint for variants. If every candidate fails, the selected best candidate still fails. This development-selection rule does not establish flight readiness.

The Difficulty checks table loads saved 32-seed stage probes. Its Watch seed buttons open actual recorded flights using the first seed at each stage, without selecting by outcome. A visible development banner states difficulty, seed and training steps. These files also work without the simulation API. `python scripts/validate_model_artifacts.py` checks summary totals, checkpoint identity, telemetry schema, physical outcomes and public/build asset links; it does not inspect a browser.

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

## Latest model experiment

The original PPO continuation completed 5,003,264 steps and still had 0/20 full-task successes. The 3,751,104-step checkpoint was retained as the measured starting point. Separate development probes on seeds 21000-21031 gave 26/32 successes at difficulty 0.20, 19/32 at 0.40, 4/32 at 0.60 and 0/32 at 1.00. These are stage probes, not qualification.

`config/training-v4.yaml` is an explicit training variant with unchanged physics and observations: a lateral-speed potential, stronger offset costs, longer GAE horizon and smaller PPO updates. Actor-only warm start transfers this project's own trained PPO actor and keeps the critic, optimizer and reward statistics fresh. The 20 initial physical evaluation rows matched the parent exactly. Source snapshots, hashes and transfer lineage are saved with new jobs.

```powershell
python scripts/training_worker.py landing-ppo-lateral-v4-pilot --steps 200000 --warm-start landing-ppo-state-potential-v3-continued__step-003751104 --config config/training-v4.yaml
python -m rocket_lab.probe landing-ppo-lateral-v4-pilot__step-003951808 --episodes 32
```

The first v4 pilot completed 200,704 additional steps. Full-task success remained 0/20; mean impact speed was 7.03 m/s, tilt 3.61 degrees and offset 9.69 m. The drift objective has not yet produced reliable full-task landing. Raw rewards across v3/v4 are not comparable. Exact continuation of a variant requires the same `--config` file. The main `config.yaml` remains unchanged so existing baseline replays keep their identity. See `docs/MODEL-ITERATION-2026-10-19.md`.

Its continuation completed another 802,816 steps, reaching 4,754,624 total lineage steps and curriculum 0.45. Matched stage probes gave 32/32, 24/32, 9/32 and 0/32 at difficulties 0.20/0.40/0.60/1.00. The final checkpoint regressed on the 20 full-task seeds: 0/20, 8.48 m/s mean speed. The earlier 4,351,808-step checkpoint had a better measured full-task objective and was retained for the next experiment.

`config/training-v5.yaml` keeps v4 physics, observations and reward but mixes 20% full-height starts into training-only resets. Easier-stage outcomes alone drive stage advancement. Noise and timeout stay tied to each episode's reset difficulty. The initial transferred actor matched all 20 parent outcome/reward rows; `data/model-mixture-transfer-validation.json` records the check. Evaluation never enables the mixture. This pilot is an experiment, not a reliability claim.

The v5 pilot completed 401,408 additional steps. Its best full-task speed was 5.74 m/s, still 0/20 successes; easier-stage performance declined. The bounded-mean v6 experiment also completed and did not improve overall full-task performance. A v7 exploration-only experiment retains the v5 deterministic actor and resets throttle sampling std to 0.15. Its first 200,000-step checkpoint recorded 1/20 full-task successes, but a separate 32-seed sample remained 0/32. This is early, unstable progress, not a solved RL controller. Exact results and limitations are in the model iteration report.

The longer-horizon v9 pilot completed 6,305,328 total lineage steps. On the same 256 full-difficulty development seeds, it improved to 23/256 successes (8.98%; Wilson 95% interval 6.06-13.12%), compared with v7's 5/256. Mean speed fell from 3.31 to 1.96 m/s; mean pad offset remains 10.69 m. Larger samples and explicitly selected successful examples are visible in Training. A two-million-step continuation and a separate pad-accuracy reward experiment are being measured. The takeoff pilot completed 401,408 steps and still scored 0/20 full-task successes.

The completed v10 pad-accuracy pilot's retained 6,905,328-step checkpoint scored 45/256 on those development seeds (17.58%; Wilson interval 13.40-22.71%), with 2.66 m/s mean speed and 6.89 m mean offset. Impact speed remains too high. A separate terminal-cost experiment is being measured. Takeoff's v11 goal curriculum completed 503,808 steps: it scored 32/32 at the training-only 64.25 m goal, while the full 400 m mission remained 0/20. Its practice replays are explicitly labelled. A longer-horizon ascent continuation is being measured; combined RL is still unqualified.

The v12 terminal-cost experiment completed and scored 6/20 on the small checkpoint batch, but only 29/256 on the matched larger sample. V10 remains the stronger measured choice. The Training page shows these rates and Wilson intervals together; repeated model selection on development seeds is explicitly disclosed.
