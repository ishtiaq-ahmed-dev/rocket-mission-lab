# Validation record

Local work on 19 October 2026, Windows, RTX 5070 Ti. Results below are from executed commands and actual simulation records.

| Gate | Evidence | Status |
| --- | --- | --- |
| CUDA compatibility | PyTorch `sm_120` architecture, actual CUDA matrix multiply, exact runtime in `data/runtime.json` | PASS |
| Python suite | Current complete suite: 53 passed, including all API transport/dispatch tests, native math, rewards, selection and actual checkpoint attribution; same Gymnasium/pynvml warnings | PASS for stated scopes |
| Physics | Analytic free fall, vacuum energy/horizontal momentum, propellant flow, thrust floor, exhaustion, fixed-seed repeatability | PASS |
| Environment | Landing/Takeoff `check_env`, all seven outcomes and finite reward | PASS |
| Classical improvement | L4 beats L1 on matching landing seeds; separate pilots below | PASS on stated sample |
| API | Current read endpoints, simulated telemetry, request bounds, shared schema and bounded training dispatch pass in the 53-test full suite | PASS |
| Frontend TypeScript | `npm run typecheck` | PASS |
| Frontend lint | `npm run lint` | PASS |
| Frontend unit tests | 30 tests: checkpoint selection, telemetry, coordinates, real OrbitControls pan after zoom, ground safety, audio, terrain seams and playback scheduling | PASS |
| Production bundle | `npm run build`, warning about large Three.js/chart chunks | PASS with size warning |
| Dependency audit | Patched Vitest; install audit reports zero vulnerabilities | PASS at install time |
| REINFORCE lesson | CartPole, 400 episodes, 20 fixed evaluation seeds: random mean 18.85, initial 9.45, trained 500 | PASS on simple task |
| Live HTTP/proxy | `data/live-validation.json` records service and telemetry response checks | See current artifact |
| Browser visuals/interaction | User confirmed rotation earlier and later reported a startup fallback. Host-call binding/fallback corrected; latest 3D recovery is unverified. Browser automation remains policy-blocked | PARTIAL, manual confirmation only |
| Playwright | Test source supplied; browser execution not performed after policy block | NOT RUN |
| Mac M1 | Browser-only architecture and CPU setup supplied; no Apple hardware test | UNVERIFIED |
| Full RL rocket competence | Early real policies have zero held-out successes | NOT ACHIEVED |
| Classical L4 nominal landing batch | 10,000/10,000 observed successes, seeds 10000–19999, config `15b9d2a4ad7e8f68`; 95% Wilson lower bound 99.9616% | PASS on recorded batch |
| Every-controller/checkpoint 10,000-seed qualification | Only the classical L4 nominal landing batch is complete | INCOMPLETE |
| Sustained FPS / recorded video | Recording layout supplied; no measured 60 fps or video encoder result | UNVERIFIED |
| PPO continuation | Disposable 512+512-step test restored step count and normalization; real continuation loaded the 1,001,472-step checkpoint | PASS for continuation; exact RNG/environment resume and reboot soak UNVERIFIED |
| Ground/4K asset delivery | Three local JPEG maps checked at 4096×4096 and served HTTP 200; telemetry proxy checks passed | PASS for assets/HTTP; GPU output UNVERIFIED |
| Model evidence and replays | Saved summaries, first-seed outcomes, checkpoint lineage, telemetry schema and public/build file links checked by `scripts/validate_model_artifacts.py`; exact count in `data/model-artifact-validation.json` | PASS for artifact checks; browser/HTTP interaction UNVERIFIED |
| Training-only start mixture | Disabled mixing preserves seeded observations; evaluation ignores mixing; full starts retain their own noise/timeout difficulty and do not advance the practice stage | PASS in isolated tests |
| Automatic frontend checkpoint slots | Six tests reject incompatible physics/pending evaluations, exclude reward comparisons across profiles, use largest samples/Wilson bounds, retain best before later regression and handle ascent speed separately | PASS in isolated tests; browser interaction UNVERIFIED |
| Current outcome/schema contracts | Nine selected outcome/schema/Wilson tests passed without HTTP transport; 13 endpoint/dispatch tests deselected | PASS for selected checks; current API transport pending |

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

## Earlier dense-terrain iteration (superseded for performance)

The terrain now uses stitched 0.5 m / 1 m / 12 m / 120 m resolution regions in Ultra/4K. Shared edges have matching heights, UVs and normals; flat engineered roads and foundations are tested. The coastline remains continuous through the ocean surface; wet color transitions are gradual. Camera height is clamped above the same surface. Road and pad use physical separation plus polygon offset to reduce depth fighting. These code-level checks do not prove the user's visual issue is fully resolved.

Actual CPU mesh assembly produced 513,752 triangles in Balanced, 1,000,520 in High and 2,943,464 in Ultra/4K. Ultra uses 100,636,268 bytes of geometry buffers and assembled in about 942 ms in the local Node check. `data/terrain-mesh-validation.json` records these measurements. These timings are CPU geometry construction, not browser render timings. The dashboard updates at 10 Hz during playback while the 3D scene reads the full precision clock; paused/scrubbed/terminal values remain exact.

Ultra/4K load actual 4096×4096 color, OpenGL normal and roughness maps. The 4K still path temporarily renders a 3840×2160 canvas with a cloned camera, then restores the original size before supersampling. This avoids an accidental 4K-times-DPR allocation. Exported image dimensions, image appearance and audible sound remain browser-side acceptance gates. The displayed FPS is a rolling local observation, not a certified performance claim.

PPO `landing-ppo-state-potential-v3` completed 1,001,472 steps, reaching difficulty 0.20. Its last full-distribution pilot was 0/20 with crash-speed failures, mean speed 17.41 m/s and mean tilt 11.86 degrees. Its continuation completed 5,003,264 total steps, reaching difficulty 0.45, still with 0/20 full-task successes. Curriculum success must not be described as full-task success.

## Performance and model correction

The earlier Ultra default caused excessive rendering work. The new High default uses 282,712 terrain triangles instead of 2,943,464 (90.4% fewer), about 9.8 MB of geometry buffers instead of 100.6 MB, and a 1.25 DPR instead of 2.5 (75% fewer pixels for the same CSS size). High retains the 4K maps. Planar scene reflection was removed, shadows use 2048 maps, rocks use compacted distance LODs, and grass does not cast shadows. Grid-fin geometry now requires four draws instead of 64. See `data/render-budget-validation.json` and `data/rock-lod-validation.json`. These are measured source/CPU budgets, not measured browser GPU/FPS improvements.

An isolated frame-clock test requested no playback frames while idle and about 60 frames over a simulated second on a 144 Hz clock. Browser host callbacks use explicit wrappers. Real OrbitControls, exercised on an isolated event surface without a browser, passed zoom-then-pan tests. A coordinate test verifies the booster up/thrust axis under arbitrary attitude. Three Newton-Euler tests verify tilted thrust acceleration and engine-lever angular acceleration against MuJoCo.

The 200,704-step lateral-v4 pilot is real and completed. Before its first update, all 20 physical outcome rows matched the parent exactly; reward differs intentionally. It still had 0/20 full-task successes at the end, with 7.03 m/s mean impact speed, 3.61 degree tilt and 9.69 m offset. Training-source snapshots and a fresh-critic/optimizer transfer record are retained. Further training and qualification remain necessary.

The v4 continuation completed 4,754,624 total lineage steps. Its matched difficulty probes yielded 32/32 at 0.20, 24/32 at 0.40, 9/32 at 0.60 and 0/32 at 1.00. On the distinct 20 full-task seeds it remained 0/20 with 8.48 m/s mean impact speed, regressing relative to its earlier best objective. The next mixed-start pilot inherits the 4,351,808-step actor; all 20 initial physical/reward rows exactly matched that parent. Do not describe either continuation as full-task competence.

V7 exploration reset, v8 full-task training and v9 longer-horizon pilots all completed, with retained failures and transfer checks. V9's 6,305,328-step checkpoint had 3/20 and 3/32 successes in the two small full-task samples. On 256 fixed development seeds 22000-22255, v9 scored 23/256, compared with v7's 5/256 on the same seeds. V9 means were 1.96 m/s speed, 3.91 degree tilt and 10.69 m pad offset. This shows partial improvement, not robust RL competence. The takeoff 401,408-step pilot scored 0/20 at all checkpoints and 0/32 in each final stage probe.

Selected successful development replays are explicitly labelled with complete sample counts. The replay generator chooses the first successful seed in the stated CSV, compares terminal physical values, and publishes both source/build assets. The artifact validator verifies selection disclosure and raw CSV counts/means/Wilson intervals. See `data/model-artifact-validation.json` for the latest counts; no browser/HTTP check is implied by it.

The completed v10 pilot's retained 6,905,328-step checkpoint scored 45/256 on the same full-task development seeds, with 2.66 m/s mean speed, 4.33 degree tilt and 6.89 m offset. V11 takeoff completed 503,808 steps and reached a 64.25 m practice goal. It scored 32/32 in that training-only goal probe, still 0/20 at full 400 m. The practice replay's schema, target, outcome and public/build links are checked independently of browser rendering.

V12 completed 7,306,736 lineage steps. Although its 6/20 small checkpoint count exceeded v10's 5/20, its larger sample was 29/256 versus v10's 45/256. Its full-difficulty stage probe was 0/32. The selector now uses the largest available sample per checkpoint and its Wilson lower bound, retaining clear development-only limitations.

Earlier automatic approval review was unavailable because of an account usage limit, so elevated work was deferred at that time. On 20 October review became available: the complete backend suite and current localhost HTTP verification ran successfully. Workspace-local temporary directories remain in use. The verified inactive services were relaunched with the current code, followed by a scoped API restart for the checkpoint-attribution fix.


## Frozen takeoff qualification — 20 October

The v13 PPO candidate `takeoff-ppo-full-v13-refinement__step-002761136` was fixed before evaluating nominal seeds 10000–19999 under baseline configuration `4f2cb7c24e9839d5`. It completed 9,836 successes in 10,000 episodes (98.36%; 95% Wilson interval 98.0919–98.5910%). Failures were 89 pad misses, 65 excessive-tilt events and 10 separation-speed errors. The source snapshots and immutable candidate hashes are recorded under `data/qualifications/`; the per-seed journal and evaluation identity are retained under `data/evaluations/`. Its separate development sample had 254/256 successes. These numbers apply to this exact nominal candidate, not every RL checkpoint or combined flight.

Matched 32-seed takeoff stress pilots were: gusts classical 32/32 and PPO 32/32; fourfold sensor noise classical 2/32 and PPO 16/32; 20% thrust loss classical 32/32 and PPO 0/32; extreme starts classical 32/32 and PPO 7/32. These pilot results expose robustness limits and do not establish stress qualification. Effective stress configuration hashes are saved beside the base hash.

The numerical simulator optimization measured 2.04 times in the headless dynamics microbenchmark, with 32 open-loop trajectories and 64 closed-loop classical/PPO episodes preserving outcomes and termination steps. This is not GPU/FPS evidence. All 30 current non-API Python tests passed, including native rotation normalization, evidence-based checkpoint selection and the separate near-ground physical speed reward. The later complete 53-test suite passed with all API HTTP/dispatch tests included. Frontend type checking, lint, 30 unit tests and production build passed after the label refinements.


The matched current-source classical L4 takeoff batch completed with 10,000/10,000 observed successes, a Wilson 95% lower bound of 99.9616%, mean separation speed 24.9607 m/s, tilt 0.6652 degrees and offset 0.5685 m. This is a scoped nominal sample; it is not certainty or stress acceptance. The old landing classical 10,000 batch remains separate under its original configuration/source.

Thrust-loss pilots above reduce the configured maximum thrust. The classical controller receives that changed model parameter; the learned policy has no explicit thrust-availability feature. They are configured-parameter tests, not an unannounced mid-flight fault experiment. Real sensor contracts, hidden actuator estimation and blind failure recovery remain separate work.


## Current source/runtime handoff

The full current backend suite passed 53 tests in 16.45 seconds. Live production HTTP verification confirms all nine API routes through the Vite proxy, schema 1.1, default learned-policy checkpoint attribution, published model evidence, a linked selected-success recording and all three 4096-square terrain textures. The default landing seed 42 still fails at 3.05 m/s; the takeoff seed 42 succeeds. A functioning endpoint and correct replay identity do not imply successful landing. These exact live values are saved in `data/live-validation.json` with verification time and source hash.

The long v10 continuation runs in its own hidden Windows process, with status/PID/log/checkpoints under its job folder. It uses 256 fixed development episodes per checkpoint and preserves the previous best model. It is a bounded local training worker, not a boot service or a guarantee of survival after reboot. The separate landing nominal qualification batches are frozen before their own 10,000 seeds; read their completed result files for final counts.


## Disk exhaustion and recovery

D: reached zero free bytes during Git's automatic background repack and concurrent runtime writes. Commit `c56265c` completed, but the maintenance repack and the new landing workers failed. Completed checkpoints and takeoff qualification remain intact. The interrupted v10 continuation had no later saved checkpoint beyond its initial 8,908,272 actor; unsaved updates were lost and are not counted as retained training progress. Partial evaluation journals are preserved and marked failed, with restarted `-r2` batches under new source identities. They are not reported as completed qualification.

Cleanup removed only disposable workspace test directories (73.37 MiB) and moved the failed Git temporary pack (43.375 MiB) to this task's authorized C: recovery folder with a matching SHA256. About 120 MiB became available. No model checkpoint, completed result or unrelated file was deleted. Further commits disable automatic maintenance for the command to avoid another repack. Tests now use C: task temporary directories.

Atomic JSON writes clean up their own failed temporary files and preserve the previous record. The training callback requests a graceful stop below 64 MiB free and refuses a new checkpoint below 32 MiB. Two executed fault tests cover partial write preservation and low-space stopping. The recovered long job starts from the last intact actor; reboot survival and unlimited storage are not promised. D: still needs additional free capacity for extended work.


After low-space recovery and the Results batch-isolation change, the complete suite passed 55 backend tests (including API transport and storage fault drills), plus 32 frontend tests, TypeScript, lint and production build. The Results page now selects one failure sample and one configuration explicitly, and uses the largest nominal classical sample per level. It no longer sums overlapping seed pools or displays duplicate same-configuration controller bars. The API publishes its current configuration hash for this filter. Browser visual inspection remains unavailable under the existing policy.

A later capacity check found about 4.85 GiB available on D:. No additional unrelated files were removed by this task; the cause of that capacity change was not investigated. The low-space protections remain active.


## Completed current-source landing nominal batches

The frozen v10 8,908,272 checkpoint completed 1,781/10,000 nominal successes (17.81%; Wilson interval 17.0725–18.5722%). There were 7,453 speed failures, 516 tilt failures and 250 pad misses. Mean terminal speed was 3.0368 m/s, tilt 3.8274 degrees and pad offset 4.6284 m. This is weaker than its 65/256 selected development sample, reinforcing the documented selection/seed uncertainty. The completed `-r2` journal is the authoritative batch; the original disk-interrupted journal remains failed and was not combined with it.

Matched current-source classical L4 landing completed with 10,000/10,000 observed successes (Wilson lower bound 99.9616%), mean speed 0.7274 m/s, tilt 0.7047 degrees and offset 1.0624 m. Both batches use baseline configuration `4f2cb7c24e9839d5` and seeds 10000–19999. They retain the disclosed differences in state features, known wind/model information, and no real-vehicle qualification is implied.

The recovered v10 continuation's 10,158,272 checkpoint scored 71/256 on the 20000 checkpoint pool and 72/256 on the separate 22000 development pool (28.13%; interval 22.97–33.92%). The latter mean speed was 2.6658 m/s, tilt 3.4307 degrees and offset 3.7870 m. Its stage probes were 0/32, 7/32, 10/32 and 10/32, showing easier-start forgetting. It has not received a full nominal batch; it must not inherit the older checkpoint's qualification.


The single-weight v17 landing trial finished with 22/256 full-task development successes, 2.6358 m/s mean speed, 5.1805 degree tilt and 5.7198 m offset. Its stage probes were 0/32, 0/32, 4/32 and 3/32. This failed trial is preserved and does not replace the stronger development candidate. Its first 20 initial physical outcomes matched the retained parent within 1e-8; reward intentionally changed.
