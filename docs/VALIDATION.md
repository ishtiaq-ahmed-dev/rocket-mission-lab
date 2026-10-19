# Validation record

Local work on 19 October 2026, Windows, RTX 5070 Ti. Results below are from executed commands and actual simulation records.

| Gate | Evidence | Status |
| --- | --- | --- |
| CUDA compatibility | PyTorch `sm_120` architecture, actual CUDA matrix multiply, exact runtime in `data/runtime.json` | PASS |
| Python suite | `python -m pytest -q`: 33 passed, four unbounded-observation Gymnasium warnings and one third-party pynvml deprecation warning | PASS |
| Physics | Analytic free fall, vacuum energy/horizontal momentum, propellant flow, thrust floor, exhaustion, fixed-seed repeatability | PASS |
| Environment | Landing/Takeoff `check_env`, all seven outcomes and finite reward | PASS |
| Classical improvement | L4 beats L1 on matching landing seeds; separate pilots below | PASS on stated sample |
| API | Read endpoints, simulated telemetry, request bounds, schema and training dispatch tests | PASS |
| Frontend TypeScript | `npm run typecheck` | PASS |
| Frontend lint | `npm run lint` | PASS |
| Frontend unit tests | 19 tests: parser/interpolation, quaternion, camera follow/framing, audio lifecycle, terrain continuity/winding/seams, quality scaling | PASS |
| Production bundle | `npm run build`, warning about large Three.js/chart chunks | PASS with size warning |
| Dependency audit | Patched Vitest; install audit reports zero vulnerabilities | PASS at install time |
| REINFORCE lesson | CartPole, 400 episodes, 20 fixed evaluation seeds: random mean 18.85, initial 9.45, trained 500 | PASS on simple task |
| Live HTTP/proxy | `data/live-validation.json` records service and telemetry response checks | See current artifact |
| Browser visuals/interaction | User confirmed live camera rotation. Browser tool policy blocked automation; latest terrain/sound/4K capture need user review | PARTIAL, manual confirmation only |
| Playwright | Test source supplied; browser execution not performed after policy block | NOT RUN |
| Mac M1 | Browser-only architecture and CPU setup supplied; no Apple hardware test | UNVERIFIED |
| Full RL rocket competence | Early real policies have zero held-out successes | NOT ACHIEVED |
| Classical L4 nominal landing batch | 10,000/10,000 observed successes, seeds 10000–19999, config `15b9d2a4ad7e8f68`; 95% Wilson lower bound 99.9616% | PASS on recorded batch |
| Every-controller/checkpoint 10,000-seed qualification | Only the classical L4 nominal landing batch is complete | INCOMPLETE |
| Sustained FPS / recorded video | Recording layout supplied; no measured 60 fps or video encoder result | UNVERIFIED |
| PPO continuation | Disposable 512+512-step test restored step count and normalization; real continuation loaded the 1,001,472-step checkpoint | PASS for continuation; exact RNG/environment resume and reboot soak UNVERIFIED |
| Ground/4K asset delivery | Three local JPEG maps checked at 4096×4096 and served HTTP 200; telemetry proxy checks passed | PASS for assets/HTTP; GPU output UNVERIFIED |

## Classical pilots

32 fixed seeds beginning at 20000; all with nominal noise/wind unless scenario named. Fractions are observations, not guaranteed rates. Exact confidence intervals and per-seed data are in `data/results/`.

| Mission | L1 | L2 | L3 | L4 |
| --- | --- | --- | --- | --- |
| Landing | 0/32 | 0/32 | 19/32 | 32/32 |
| Takeoff | 0/32 | 32/32 | 32/32 | 32/32 |
| Combined | 0/32 | 0/32 | 17/32 | 32/32 |

Landing L4 stress pilots: gusts 32/32, thrust loss 32/32, fourfold noise 0/32, extreme starts 17/32. The noise failures were 31 crash_speed and 1 crash_tilt. Extreme starts produced 11 crash_speed and 4 missed_pad. These weaknesses are retained and are not hidden by the nominal result.

## Operational failures and fixes

- MuJoCo mass constant recalculation reset the live pose; preserving it fixed analytic tests.
- Cascaded lateral/attitude feedback produced touchdown drift. LQR with the adverse initial translation term improved the measured controller.
- An asymptotically zero descent reference caused a combined-flight hover. A finite touchdown-speed reference fixed the recorded seed-42 flight.
- SAC inference initially allocated its training replay buffer. Loading a one-transition placeholder fixed unnecessary allocation.
- A Windows reader lock interrupted progress persistence. Bounded retry was implemented and tested with simulated transient lock failures.
- Multiple Torch processes approached Windows commit limits; physical free RAM alone was misleading. Research jobs are supervised and the UI permits one API job at a time.
- Sandbox API tests stalled in asyncio's local socketpair initialization. The suite passed outside that sandbox.

## Pending evidence

Complete the independent seed batches and robustness checks for every candidate checkpoint before assigning reliable RL maturity. Visual browser checks, accessibility interaction, mobile overflow, Apple hardware, measured rendering performance and recovery/soak must remain separate gates.

## Latest visual and RL iteration

The terrain now uses stitched 0.5 m / 1 m / 12 m / 120 m resolution regions in Ultra/4K. Shared edges have matching heights, UVs and normals; flat engineered roads and foundations are tested. The coastline remains continuous through the ocean surface; wet color transitions are gradual. Camera height is clamped above the same surface. Road and pad use physical separation plus polygon offset to reduce depth fighting. These code-level checks do not prove the user's visual issue is fully resolved.

Actual CPU mesh assembly produced 513,752 triangles in Balanced, 1,000,520 in High and 2,943,464 in Ultra/4K. Ultra uses 100,636,268 bytes of geometry buffers and assembled in about 942 ms in the local Node check. `data/terrain-mesh-validation.json` records these measurements. These timings are CPU geometry construction, not browser render timings. The dashboard updates at 10 Hz during playback while the 3D scene reads the full precision clock; paused/scrubbed/terminal values remain exact.

Ultra/4K load actual 4096×4096 color, OpenGL normal and roughness maps. The 4K still path temporarily renders a 3840×2160 canvas with a cloned camera, then restores the original size before supersampling. This avoids an accidental 4K-times-DPR allocation. Exported image dimensions, image appearance and audible sound remain browser-side acceptance gates. The displayed FPS is a rolling local observation, not a certified performance claim.

PPO `landing-ppo-state-potential-v3` completed 1,001,472 steps, reaching difficulty 0.20. Its last full-distribution pilot was 0/20 with crash-speed failures, mean speed 17.41 m/s and mean tilt 11.86 degrees. The four-million-additional-step continuation is `landing-ppo-state-potential-v3-continued`; its current heartbeat and evaluation curve are in the Training tab. Curriculum success must not be described as full-task success.
