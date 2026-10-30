# Rocket Mission Lab

A local rocket flight simulator and reinforcement-learning workbench. The browser interface is a single [Falcon 9 RTLS mission replay](frontend/index.html): one page that computes the whole flight in JavaScript and renders it with Three.js. The Python engine, training jobs and API remain available for simulation work.

Vehicle parameters are generic approximations of a Falcon 9 Block 5 class vehicle. Nothing here is a validated real-world flight model.

## Flight deck

The page integrates inertial point-mass dynamics on a spherical, rotating Earth with a 1976-standard-atmosphere density table, wind, Mach-dependent drag and an angle-of-attack normal force. It runs the ascent, MECO, stage separation, second-stage orbit insertion, fairing and payload deploy, then the booster's flip, boostback, entry burn, aerodynamic steering and powered landing on LZ-1. Integration is 0.02 s; tracks are sampled at 25 Hz.

The trajectory is computed once at load, so playback speed and frame rate never change the flight. Three.js is bundled locally; the replay does not require a CDN connection.

**Limits:** the model is approximate. Engine, mass and aerodynamic values are generic, guidance is a simplified predictor-corrector, and the second stage uses a tuned pitch schedule. A successful replay does not establish landing reliability. Fins, legs, plume and exhaust lighting are illustrative, not a combustion or structural model. The page states this in a **MODEL NOTES** panel (button at top left, or `M`/`?`), which lists the assumptions, what is not modelled, and the achieved default-run figures.

The default run reaches main engine cutoff at 70.6 km and 1.82 km/s, a booster apogee of 138 km, and a 274 × 326 km insertion at 39.9°. It touches down at 1.82 m/s vertical, 0.04 m/s horizontal and 0.2° tilt, 9.8 m from the pad centre on an 86 m pad.

### Cameras and playback

- `1` Orbit, `2` Chase, `3` Launch Tower, `4` Booster Top Cam, `5` Landing Pad, `6` Overview, `7` Orbital View.
- `F` cycle focus between the stack and the booster, `Space` play/pause, `←`/`→` seek, `H` hide the HUD.
- Drag to orbit, wheel to zoom. Speed presets run from 0.25× to 30×, and the timeline marks liftoff, max-Q, MECO, boostback, entry burn, landing burn, touchdown, SECO and payload deploy.

## Run locally

```powershell
cd frontend
npm ci
npm run dev
```

Open <http://127.0.0.1:5180/>. For a production build run `npm run build` (output in `frontend/dist`) and serve it with `.venv\Scripts\python.exe scripts/serve.py`, which also mounts the API at `/api`. Node is only needed for building or development.

To work on the Python engine:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Python engine and training

`rocket_lab` integrates booster dynamics in MuJoCo and exposes missions through the FastAPI app in `rocket_lab/api.py` (`/simulate`, `/training`, `/campaigns`, `/checkpoints`, `/results`). Mission plans use local metres: X east, Y north, a flat surface at Z = 0, and pads more than 1,000 m apart. The engine's default plan lands at the origin with 400 m separation; a request without a `flight_plan` uses it.

Training supports individual PPO/SAC jobs and a three-mission campaign. Budgets are environment steps, not optimizer iterations. A campaign shares a total ceiling up to 100 million steps across alternating landing, takeoff and combined blocks, saves model/normalization snapshots, and uses a curriculum for altitude and target displacement. Landing and combined episodes also receive seeded mid-flight landing-target changes from `training.retarget_probability`. PPO keeps a stage-scaled action-std floor so a policy cannot collapse to a constant action, and uses discount 0.999 so a full-height descent stays inside the credit horizon. It stops on exhausted budget or a measured plateau.

```powershell
# Explicitly bounded local campaign; logs/status/checkpoints stay on this machine.
.venv\Scripts\python.exe -m rocket_lab.campaign --id my-flight-study --steps 100000000 --block-steps 250000 --plan data/campaign-plan-2026-10-21.json
# After a campaign has stopped, continue its optimizer/normalization snapshots:
.venv\Scripts\python.exe -m rocket_lab.campaign --id my-flight-study --steps 100000000 --block-steps 250000 --resume
```

Stop flags work at `data/campaigns/<id>/stop`; a running block saves at a callback. Status is in `/api/campaigns` and `/api/training`. Exact environment/RNG continuation across a restart is not promised. Model binaries live under ignored `data/checkpoints/`.

A candidate with at least 254/256 development successes receives a separate 10,000-seed nominal evaluation using a fresh seed range. The nominal gate requires a 95% Wilson lower bound of at least 99%. This does not establish stress robustness or real-world safety, and training never substitutes a classical controller for a learned policy.

## Validation

```powershell
.venv\Scripts\python.exe -m pytest tests -q
node scripts/check_flight.js
.venv\Scripts\python.exe scripts/validate_mission_plans.py --episodes 100
.venv\Scripts\python.exe scripts/validate_live.py
cd frontend
npm run build
```

`scripts/check_flight.js` extracts the flight model from the shipped `frontend/index.html` and asserts its invariants: chronological events, monotonic non-negative propellant, throttle bounds, vis-viva consistency at insertion, insertion elements, and touchdown speed, tilt and pad contact. `scripts/check.py` runs it together with the Python suite and the production build.

`make test` runs both steps. Continuous integration runs the same Python suite and production build on Windows (`.github/workflows/ci.yml`).

Existing 10,000-flight results belong to earlier source/configuration snapshots and are archived experiments; they do not qualify the current controller.

## Project layout

| Path | Contents |
| --- | --- |
| `frontend/` | The replay page (`index.html`), vendored Three.js and the ground textures |
| `rocket_lab/` | Physics, controllers, environments, training, FastAPI service |
| `scripts/` | Launchers, checks and validation entry points |
| `tests/` | Python test suite |
| `docs/` | Numbered design and validation records |
| `config.yaml` | Vehicle, mission and reward configuration |

## License

MIT — see [LICENSE](LICENSE). Bundled terrain textures are CC0; see [frontend/public/assets/ATTRIBUTION.md](frontend/public/assets/ATTRIBUTION.md).

[Mission/physics contracts](docs/21-mission-controls.md) · [Research](docs/RESEARCH.md) · [Pad labels, distance and timing](docs/31-pad-labels-distance-and-timing.md) · [Earlier implementation and experiment history](docs/archive/README-2026-10-20.md).
