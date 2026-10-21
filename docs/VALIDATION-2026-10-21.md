# Mission Control validation — 21 October 2026

This record covers the white-plane renderer, camera/dashboard redesign, configurable mission geometry, stage event, revised classical descent, and supervised training workers. Earlier qualification batches remain historical evidence.

## Executed checks

| Check | Result | Scope |
| --- | --- | --- |
| Backend suite | 71 passed | Physics, environment, API, bounds, mission targets, separation continuity, exact replay attribution, training continuation, campaign dispatch, storage faults, worker diagnostics |
| Frontend units | 34 passed | Telemetry, engine-off/mass transition sampling, coordinates, camera framing/pan/follow, expanded zoom bound, playback scheduling, existing archive helpers |
| TypeScript/build/lint | Passed | Production build retains warnings about large Three.js/chart chunks |
| Local integration | Passed | Ten API/proxy endpoints, production frontend, configured combined flight, saved replay identity, offline replay schemas |
| Actual worker dispatch | Passed | API launched an independent Windows worker; a 4,096-step job completed and saved checkpoints |
| Worker restart survival | Observed | Independent campaign continued advancing with a fresh heartbeat across an API/preview restart; no reboot or overnight soak claim |
| Archived evidence integrity | Passed | 37 checkpoints, 157 replays, 5,376 development evaluation episodes and 40,000 historical qualification episodes; this validates saved artifacts, not current policy competence |

Gymnasium warns about unbounded observation-space limits. PyTorch reports the existing pynvml deprecation warning. Neither warning was hidden or treated as flight evidence.

## Fixed-seed classical pilots

Each cell is 100 independent simulations on seeds 50000–50099, using controller level 4. These are development pilots, including reused seeds during controller tuning. They are not held-out qualification and are not pooled into a universal reliability rate.

| Flight plan | Landing | Takeoff | Combined |
| --- | --- | --- | --- |
| Launch [0, 0], land [0, 0], separation 400 m | 100/100 | 100/100 | 99/100 |
| Launch [200, -100], land [240, -80], separation 300 m | 100/100 | 100/100 | 98/100 |
| Launch [0, 0], land [80, 40], separation 400 m | 100/100 | 100/100 | 98/100 |

The five combined-flight failures exceeded the 2 m/s touchdown speed threshold. Longer/harder transfers can exhaust the fuel reserve. Success is not forced when a requested target is unreachable. The source digest is `dcd106afbe6510059063b16bf90cd3aa95fe2e38ccca94c4247497884b43d1c6`; each row's exact configuration and Wilson interval are in [the machine-readable pilot record](evidence/2026-10-21/mission-plan-validation.json). Nine raw CSV files in that folder retain all 900 episode outcomes.

The local configured API flight on seed 42 launched at [200, -100], released its upper stage at 300 m, and landed near [240, -80]: 0.355 m/s final speed, 0.997 degrees tilt, and 1.097 m offset. This is one example, not a reliability claim.

## Browser observations

The actual browser displayed the white plane, rocket, colored exhaust during powered ascent, paused/no-flame coast, amber/charcoal dashboard, separately editable coordinates, fixed Run control, and recorded event links. Zoom-out reached 3.5 km, exceeding the old 2.2 km clamp. A combined flight accepted edited launch/landing/separation values, scrubbing paused playback, and its final event displayed a successful touchdown. Training and campaign progress were visible.

At the observed 451 x 698 render buffer, playback readouts included approximately 55–57 FPS and 54–60 draw calls depending on phase/view. These are short observations from one browser, not sustained FPS, GPU-memory measurements, or a hardware benchmark. Browser console inspection returned no errors/warnings at the checked point. The camera unit suite additionally exercises orbit/pan/follow behavior. Current mobile, 4K still export, screen-reader behavior, and long video output were not fully qualified.

## Training state and recovery

Campaign `mission-v18-20261021` alternates landing, takeoff, and combined PPO blocks under a **shared 100,000,000-step ceiling**. It was observed advancing past 2.7 million aggregate environment steps after the worker recovery and API restart. See [the timestamped training snapshot](evidence/2026-10-21/training-snapshot.json). None of these new learned policies has passed its full-task qualification gate.

An earlier Start-Process worker exited with a stale heartbeat. Recovery retained the durable checkpoint, recorded the lost in-flight steps, counted consumed steps against the budget, and switched dispatch to a hidden WMI worker with owned logs. The short dispatch test and campaign restart-survival observations are saved in this evidence folder. API training now uses the same independent host; errors are persisted instead of leaving a false running label. Reboot recovery and prolonged unattended operation remain unverified.

The campaign may stop before its budget if successes, physical errors, and curriculum difficulty cease improving. Candidates need a separate 10,000-seed nominal test before the nominal gate can pass. Even a passed nominal gate would not establish stress robustness or a real flight capability. The 100-million-step ceiling has not been claimed as completed training.

## Model limits

The booster is a generic, approximate rigid-body model. Separation drops attached mass without an ejection impulse or center-of-mass migration. The released stage is an unpowered ideal ballistic drawing; no upper-stage propulsion or orbit is integrated. Exhaust rendering is illustrative. See [mission contracts](21-mission-controls.md).
