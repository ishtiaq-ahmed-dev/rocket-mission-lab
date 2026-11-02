# Rocket Mission Lab

A Falcon 9-class return-to-launch-site mission — launch, staging, orbit insertion and booster landing — **flown end to end by a trained neural network** and rendered in the browser with Three.js ([`frontend/index.html`](frontend/index.html)).

Every command in the flight comes from the network: engine ignition, cutoff and engine count, throttle, attitude, stage separation, second-stage burn, fairing jettison and payload deploy. The page contains the physics and the network weights ([`frontend/public/flight-policy.js`](frontend/public/flight-policy.js)); it contains no scripted guidance and no fallback controller. If the weights cannot be loaded, the page stops with an error instead of flying something else.

## The flight

| Phase | What happens (after Falcon 9 RTLS practice) |
| --- | --- |
| Ascent | Hold-down until thrust exceeds weight at T-0, pitch kick, gravity turn, max-Q throttle bucket |
| MECO and separation | Nine engines cut and finish their tail-off; pneumatic pushers separate the stages with equal and opposite impulse; the upper stage lights about five seconds later |
| Flip and boostback | Cold-gas flip, then three engines with **horizontal** thrust toward the landing zone. Thrust never points toward the ground; the booster keeps climbing on its own momentum while gravity slows it |
| Ballistic coast | Engines off, nose up, engines leading |
| Entry burn | Three engines near 60 km, against the airflow |
| Aerodynamic glide | Engines off, grid fins steer toward the pad |
| Landing burn | One engine, lit at the last feasible moment; touchdown on LZ-1 |
| Orbit | Closed-loop insertion to about 270 × 340 km at 39.5°, payload deploy 60 s after SECO |

Default flight, as flown by the shipped policy: MECO at 71.9 km and 1.78 km/s, booster apogee 184 km, insertion 270 × 341 km at 39.5°, touchdown at 1.76 m/s vertical and 0.03 m/s horizontal, 0.10° tilt, 0.2 m from the pad centre.

**Reliability.** On 300 dispersed flights the network never saw — wind 0–100 % in any direction, engine thrust ±1 %, drag ±5 %, booster dry mass ±300 kg, payload ±1,000 kg — it completed **298** full missions (orbit, deploy and a landing within 3 m/s, 1.5 m/s sideways, 5° and the 43 m pad radius). The classical teacher it learned from completed 295 of the same flights. All 300 reached orbit; the worst touchdown was 2.1 m/s. This is a simulated study, not a flight-certification claim. Details: [docs/FLIGHT-POLICY.md](docs/FLIGHT-POLICY.md).

**Model limits:** point-mass dynamics with a rate-limited first-order attitude response; public Falcon 9 figures anchor the vehicle, but dry masses and aerodynamic coefficients are modelled. Plume, smoke, legs and fins are illustrative. The **MODEL NOTES** panel (top left, or `M`) lists the assumptions and this run's figures.

### Cameras and playback

- `1` Orbit, `2` Chase, `3` Launch Tower, `4` Booster Top Cam, `5` Landing Pad, `6` Overview, `7` Orbital View.
- `F` cycle focus between the stack and the booster, `Space` play/pause, `←`/`→` seek, `H` hide the HUD.
- Speed presets 0.1× to 30×; the timeline marks liftoff, max-Q, MECO, separation, boostback, entry burn, landing burn, touchdown, SECO and payload deploy.

## Run locally

```powershell
cd frontend
npm ci
npm run dev
```

Open <http://127.0.0.1:5180/>. `npm run build` writes a production bundle to `frontend/dist`; `.venv\Scripts\python.exe scripts/serve.py` serves it together with the Python API at `/api`.

## Train the flight policy

The classical teacher, data generation and training live in [`scripts/flight_policy/`](scripts/flight_policy/) and are never shipped to the page. Node runs the flights in parallel; PyTorch trains the network.

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
node scripts/flight_policy/dagger.js --fresh --demos 240 --iters 10 --per-iter 200   # demonstrations, behaviour cloning, DAgger
node scripts/flight_policy/parallel.js policy 900000 300                             # evaluate the shipped policy on unseen seeds
node scripts/flight_policy/parallel.js teacher 900000 300                            # the teacher on the same seeds
```

Training writes `frontend/public/flight-policy.js`. Datasets and checkpoints stay under ignored `data/flight-policy/`.

## Validation

```powershell
node scripts/check_flight.js
node scripts/check_standards.js
.venv\Scripts\python.exe -m pytest tests -q
cd frontend; npm run build
```

`check_flight.js` flies the shipped page with the shipped weights and checks every frame and the 60 Hz interpolation: event order, propellant, throttle and engine bounds, phase consistency, vis-viva at insertion, touchdown limits, that the booster's thrust never points toward the ground after separation, that the return burns run boostback → entry → landing, and that the page contains no scripted guidance. `check_standards.js` checks the WGS-84, ISO 2533 / US 1976, Merlin/MVac and mass-closure anchors and the default-flight regression ([docs/STANDARDS.md](docs/STANDARDS.md)). `make test` and CI (`.github/workflows/ci.yml`) run these together.

## Python laboratory

`rocket_lab/` is a separate 400 m subscale workbench: MuJoCo free-body dynamics, Gymnasium environments, PPO/SAC training, campaigns, classical controllers and a FastAPI service (`/simulate`, `/training`, `/campaigns`, `/checkpoints`, `/results`). Its vehicle is not the Falcon 9 replay. See [docs/README.md](docs/README.md) for its notes; earlier experiment history is in [docs/HISTORY.md](docs/HISTORY.md).

## Project layout

| Path | Contents |
| --- | --- |
| `frontend/` | The replay page, the policy weights (`public/flight-policy.js`), vendored Three.js and textures |
| `scripts/flight_policy/` | Teacher, rollouts, DAgger loop and trainer for the flight policy |
| `scripts/` | Checks, launchers and validation entry points |
| `rocket_lab/` | Python laboratory: physics, environments, training, API |
| `tests/` | Python test suite |
| `data/reference/` | Public standards, vehicle and mission reference |
| `docs/` | Flight policy, standards, research, history and the Python lab notes |

## License

MIT — see [LICENSE](LICENSE). Bundled terrain textures are CC0; see [frontend/public/assets/ATTRIBUTION.md](frontend/public/assets/ATTRIBUTION.md).
