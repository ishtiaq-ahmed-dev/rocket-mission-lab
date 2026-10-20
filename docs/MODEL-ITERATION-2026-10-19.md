# Measured model iteration: 19 October 2026

The revised PPO actor improved easier landing stages. It has not learned reliable full-difficulty landing. This report records physical outcomes and retains failed checkpoints.

## Diagnosis and changes

The original v3 continuation completed 5,003,264 steps with zero successes in its final 20-seed full-task development sample. Later training regressed, so the 3,751,104-step checkpoint was retained based on measured evaluation, rather than selecting the newest file. It had mean touchdown speed 6.97 m/s, tilt 3.80 degrees and pad offset 10.09 m on seeds 20000-20019.

The explicit `config/training-v4.yaml` snapshot keeps the vehicle, world, mission thresholds and physical observation scales unchanged. It adds a horizontal-speed potential, doubles the lateral-position and terminal-position weights, halves PPO's learning rate, and uses gamma 0.997 / GAE lambda 0.98 with a target-KL stop. These are empirical changes informed by [SB3's experiment guidance](https://stable-baselines3.readthedocs.io/en/master/guide/rl_tips.html) and [GAE](https://arxiv.org/abs/1506.02438).

Actor-only transfer copies this project's own learned policy layers and action distribution. The critic, optimizer and reward normalization are fresh. No classical-controller actions, demonstrations or trajectory reference are supplied. The initial transferred actor's 20 physical outcome rows exactly matched the parent before its first update; rewards differ because the objective changed. Evidence: `data/model-transfer-validation.json` and the job's `warm-start.json`.

The pilot completed 200,704 additional steps, reaching 3,951,808 total inherited-plus-new steps. Its final full-task sample remained 0/20, with mean speed 7.03 m/s, tilt 3.61 degrees and offset 9.69 m. Raw v3/v4 reward values are not comparable.

## Matched difficulty probes

Each row uses the same 32 development seeds, 21000-21031, deterministic policy actions and the same physical evaluation configuration. Difficulty changes the reset distribution, randomization and disturbances. Success still requires speed below 2 m/s, tilt below 5 degrees and pad offset within 5 m. These are development probes, not independent qualification.

| Difficulty | v3 successes | v4 pilot successes | v3 / v4 mean speed (m/s) | v3 / v4 mean tilt (degrees) | v3 / v4 mean offset (m) |
| --- | --- | --- | --- | --- | --- |
| 0.20 | 26/32 | 32/32 | 1.67 / 1.39 | 2.15 / 1.03 | 3.44 / 2.20 |
| 0.40 | 19/32 | 22/32 | 2.97 / 1.41 | 3.72 / 2.13 | 6.56 / 3.94 |
| 0.60 | 4/32 | 5/32 | 5.30 / 6.18 | 11.04 / 10.26 | 22.44 / 16.87 |
| 1.00 | 0/32 | 0/32 | 7.26 / 7.17 | 4.45 / 3.93 | 11.19 / 10.26 |

The improvement is clearest at 0.20 and 0.40. At 0.60 the speed metric regressed despite one more success and reduced mean offset. No full-task success was observed. Per-seed outcomes and failure classes are saved in `data/probes/`; summary rows are published in the Training page's Difficulty checks table.

## Continuation and provenance

The 800,000-additional-step continuation completed 802,816 actual steps, reaching 4,754,624 total lineage steps and difficulty 0.45. It restored optimizer, reward statistics, inherited steps and difficulty 0.40 at launch. Environment/RNG state restarts, so exact trajectory continuation is not claimed. Every full-task checkpoint sample remained 0/20. The final one had mean speed 8.48 m/s, tilt 3.30 degrees and offset 9.27 m, regressing on speed relative to the earlier best objective.

| V4 checkpoint steps | d=0.20 successes | d=0.40 successes | d=0.60 successes | d=1.00 successes |
| --- | --- | --- | --- | --- |
| 3,951,808 (pilot) | 32/32 | 22/32 | 5/32 | 0/32 |
| 4,151,808 | 32/32 | 22/32 | 6/32 | 0/32 |
| 4,351,808 | 32/32 | 23/32 | 6/32 | 0/32 |
| 4,754,624 | 32/32 | 24/32 | 9/32 | 0/32 |

The final d=0.60 sample had mean speed 2.15 m/s, tilt 3.75 degrees and offset 5.21 m. Easier-stage improvement coexists with worse full-height generalization. The first fixed-seed full-task pilot replay shows excessive coasting before the landing burn. These observations motivate changing training exposure rather than hiding failed replays.

Baseline config hash: `4f2cb7c24e9839d5`. V4 training hash: `2255ffc440dc1a47`. New jobs copy source files and record a SHA256 source hash with checkpoints. This is source provenance, not a full portable dependency lock.

```powershell
.\.venv\Scripts\python.exe scripts/training_worker.py landing-ppo-lateral-v4-continued --steps 800000 --resume landing-ppo-lateral-v4-pilot__step-003951808 --config config/training-v4.yaml
.\.venv\Scripts\python.exe -m rocket_lab.probe landing-ppo-lateral-v4-pilot__step-003951808 --episodes 32
```

## Verification and remaining gates

All 30 non-API Python tests passed with a unique temporary directory inside the workspace. They include physical rotated-thrust/torque checks, actor-transfer invariance and rejection guards, reward drift sensitivity, exact-config resume, source identity, replay difficulty and training-only mixture controls. All 30 frontend tests, type checking, lint and production build passed. The frontend table loads actual saved probe results. Replays always use the first development seed, including failures, with visible difficulty/seed/step labels. The artifact validator checks raw counts, means, checkpoint identity, recorded terminal outcomes, schema and public/build file links.

Full API tests need a separate rerun: sandbox socket initialization is restricted, and automatic approval review was unavailable due an account usage limit. No elevated command was executed after that failure. Browser observation was separately blocked by browser policy; no current screenshot, rendering recovery or GPU/FPS result is claimed.

Remaining work includes full-difficulty PPO competence, comparable SAC training, takeoff/combined RL, independent larger evaluation batches, stress testing, every-checkpoint qualification, and browser/Mac/performance acceptance. The completed classical nominal 10,000-episode batch does not qualify these RL models.

## Mixed-start experiment

`config/training-v5.yaml`, hash `62abdd5e196902e2`, keeps v4 physical settings, observations and reward. During training only, 20% of landing resets use full difficulty and 80% use the current practice stage. Only practice-stage outcomes count toward advancement. Noise and timeout remain fixed to the actual reset difficulty throughout an episode, even if the next curriculum stage changes. Evaluation ignores this mixture and keeps the exact requested difficulty. With mixing disabled, seeded observations remain unchanged.

The 400,000-step pilot warm-started only the actor from the 4,351,808-step checkpoint, which had the best measured full-task objective in the v4 continuation. A new critic, optimizer and reward statistics are explicit. Before updates, all 20 physical/reward rows matched its parent exactly (`data/model-mixture-transfer-validation.json`). It completed 401,408 actual additional steps, reaching 4,753,216 total lineage steps and difficulty 0.45.

Its best full-task checkpoint was 4,651,808: 0/20 successes, 5.74 m/s mean speed, 2.45 degree tilt and 10.39 m offset. The final checkpoint regressed to 6.07 m/s, 6.02 degree tilt and 14.33 m offset. On matched stage probes the best checkpoint scored 31/32, 18/32, 5/32 and 0/32; the final scored 31/32, 19/32, 5/32 and 0/32. Full-height speed improved relative to the v4 parent, while easier-stage competence declined. This is not a general improvement or convergence result.

## Action-distribution diagnosis and bounded-mean experiment

`scripts/diagnose_policy_actions.py` records the actor's actual Gaussian mean/std along one deterministic full-height flight. At seed 21000, the retained v4 policy started with throttle mean -1.2371 and standard deviation 0.0252. With engine-on cutoff -0.96, the Gaussian probability of an engine-on sample was about 2.31e-28. This is evidence of an exploration/clipping obstacle on that trajectory, not proof that it explains every failed seed. The full diagnostic is saved in `data/diagnostics/`.

[SB3 documents PPO's clipped Gaussian actions](https://stable-baselines3.readthedocs.io/en/master/guide/custom_policy.html) and [the limitations of clipping](https://stable-baselines3.readthedocs.io/en/master/guide/rl_tips.html). The v6 architecture places `tanh` on the Gaussian mean before sampling. It does not squash the sampled distribution: PPO's Gaussian likelihood remains valid, and SB3 still clips tail samples. It supplies no controller action, burn schedule or expert trajectory. Physics, v4 reward and v5 start mixture are unchanged.

The v6 snapshot hash is `c30ba642a907ae19`. Actor weights transfer from the best v5 checkpoint, but the output activation changes the actor function. Its `warm-start.json` explicitly records `actor_function_changed: true`; initial actions/outcomes are not claimed to match. It completed 401,408 additional steps, reaching 5,053,216 lineage steps, with no curriculum advancement. The untrained transformed actor had 0/20 successes and 11.09 m/s mean impact speed. The final had 0/20, 5.32 m/s mean speed, 6.15 degree tilt and 15.15 m offset. The full-difficulty 32-seed probe also failed all episodes, with 8.63 m/s mean speed and 14.93 degree tilt. Although speed recovered, this experiment did not beat the v5 parent's full-task objective. Unit tests verify bounded means, finite gradients, real parameter updates, and identical deterministic actions after save/load.

## Throttle exploration experiment

The v5 parent's initial full-height throttle mean was -1.2917 with std 0.0245 on seed 21000: engine-on sampling probability about 5.34e-42. The v7 snapshot (`b3a9ab3c011b2b2a`) resets only the throttle std to 0.15; gimbal std and the deterministic actor remain unchanged. The corresponding probability became about 1.35%. All 20 initial deterministic physical/reward rows exactly matched the parent. Evidence is in `data/diagnostics/` and `data/model-exploration-transfer-validation.json`. This changes training exploration, without adding a burn schedule or expert action.

At 200,000 additional steps, checkpoint 4,851,808 achieved 1/20 full-task development successes, with mean speed 2.65 m/s, tilt 5.03 degrees and offset 12.15 m. Its separate 32-seed full-difficulty probe scored 0/32, with mean speed 3.35 m/s. Easier probes scored 32/32 at 0.20, 18/32 at 0.40 and 1/32 at 0.60. Later 5,000,000 and 5,051,808 checkpoints again had 0/20. The pilot completed 802,816 additional steps, reaching 5,454,624 lineage steps; its final checkpoint scored 0/20 and 1/32 on the two small full-difficulty seed pools. The retained 4,851,808 checkpoint scored 5/256 on seeds 22000-22255 (1.95%; Wilson 95% interval 0.84-4.49%). Mean speed was 3.31 m/s, tilt 4.79 degrees and offset 12.26 m. This is early competence, not reliable generalization.

The v7 transfer explicitly records a changed distribution and an unchanged deterministic action function. The per-action std override is used on warm start only, not reapplied on exact-config resume. Unit tests verify identical deterministic actions, changed throttle std, preserved gimbal std and invalid-value rejection.

## Full-difficulty and longer-horizon training

The v8 snapshot (`f3625bf01a1fcfc6`) sets all training starts and disturbances to difficulty 1.0. It transfers the v7 actor without changing its deterministic actions; all 20 initial physical/reward rows matched exactly. Its 600,000-step pilot completed 602,112 actual additional steps, reaching 5,453,920 lineage steps. The 5,301,808 checkpoint scored 1/20 and 1/32 at full difficulty, with mean speed 2.38 m/s in the 32-seed probe; its final regressed to 0/20 and 0/32. Pad error remained around 11 m.

The v9 snapshot (`f10344bcd3bb0cd4`) keeps the physical task and v4 reward, and increases gamma to 0.999 / GAE lambda to 0.995. The heuristic credit horizon `1/(1-gamma*lambda)` rises from about 43 to about 167 control steps, which may help relate early lateral actions to a terminal pad miss. This is our hypothesis, not a proof of causality. [GAE](https://arxiv.org/abs/1506.02438) describes the underlying bias/variance tradeoff. [Gaudet et al.](https://arxiv.org/abs/1810.08719) also discuss credit assignment and scaling for a different six-DOF lander; this project does not reproduce their algorithm or results.

Its initial actor matched all 20 parent physical/reward rows exactly. The million-step pilot completed 1,003,520 additional steps, reaching 6,305,328 lineage steps. Checkpoint full-task successes rose from 1/20 to 3/20. The final 32-seed full-difficulty probe scored 3/32, with mean speed 2.17 m/s, tilt 4.23 degrees and offset 10.66 m.

| Policy | Full-task seeds 22000-22255 | Wilson 95% interval | Mean speed | Mean tilt | Mean pad offset |
| --- | --- | --- | --- | --- | --- |
| V7 at 4,851,808 steps | 5/256 (1.95%) | 0.84-4.49% | 3.31 m/s | 4.79 degrees | 12.26 m |
| V9 at 6,305,328 steps | 23/256 (8.98%) | 6.06-13.12% | 1.96 m/s | 3.91 degrees | 10.69 m |

The matched development sample shows improvement, while absolute success remains low. It is not an independent 10,000-seed qualification, and it comes from one training seed. The two-million-additional-step exact-config continuation completed 8,308,272 lineage steps. Its final larger development sample was 24/256 (9.38%; interval 6.38–13.57%), mean speed 2.14 m/s, tilt 4.21 degrees and offset 10.59 m. Its final stage probes were 0/32, 1/32, 4/32 and 1/32, showing forgetting of easier starts. This did not beat the v10 pad-accuracy branch on the larger sample. The v10 sibling (`364e1822c49464a7`) separately tests pad accuracy: lateral potential weight 12 instead of 4 and terminal-position weight 12 instead of 2, with unchanged physics and mission thresholds. Its initial physical rows match the v9 parent; rewards intentionally differ.

The Training page publishes larger sample counts and confidence intervals alongside all stage probes. Stage replays always use the first fixed seed. Separately, a button can show the first successful seed from a larger sample, explicitly labelled as selected by outcome and accompanied by the complete sample rate. For example, v7 seed 22011 landed at 1.98 m/s, 4.01 degree tilt and 0.69 m pad offset, as one of only 5 successes in 256 attempts. It is not presented as representative reliability.

## Takeoff pilot and selection

The takeoff v4 PPO pilot completed 401,408 steps from scratch. It reached no curriculum advancement and scored 0/20 at every full-task checkpoint. The final stage probes also scored 0/32 at all four difficulties. Reward improved, but the policy did not demonstrate controlled separation. Recorded terminal speed is the actual speed at termination and must not be confused with the target-speed error. Combined RL remains unqualified.

The frontend's automatic RL slots now compare only checkpoints with identical vehicle/world/mission settings. They use the largest full-task sample available for each checkpoint and rank its Wilson lower bound, sample size, observed rate, then physical speed/tilt/offset error for landing; raw reward across profiles is excluded. This is a conservative development-selection rule, not a post-selection reliability guarantee. Historical ascent results lack target vertical-speed error, so ascent ties use recency rather than treating low speed as a soft landing. Earlier slots come from the selected job before its best checkpoint. Six unit tests cover incompatible physics, incomplete evaluation, reward incompatibility, regressed later checkpoints, ascent-speed interpretation and larger-sample reversals. The running API's older default selector is unchanged; the frontend supplies the selected checkpoint ID explicitly. Direct API callers still need to choose an explicit variant checkpoint.

## Pad accuracy and ascent-goal experiments

The v10 pilot completed 802,816 additional steps, reaching 7,108,144 lineage steps. Its initial 20 physical rows exactly matched the v9 parent, with raw reward excluded because position costs changed. Checkpoint 6,905,328 scored 5/20 full-task successes, with mean speed 2.35 m/s, tilt 4.64 degrees and offset 5.84 m. The final checkpoint regressed to 4/20, so it is not selected merely for being newer. Final stage probes were 28/32, 20/32, 13/32 and 4/32 at difficulties 0.20/0.40/0.60/1.00.

On the same 256 full-difficulty development seeds, checkpoint 6,905,328 scored 45/256 (17.58%; Wilson 95% interval 13.40-22.71%). Mean speed was 2.66 m/s, tilt 4.33 degrees and offset 6.89 m. This improved success and offset relative to the v9 pilot but worsened mean speed. Repeated use of these seeds makes this a development comparison, not an independent post-selection confidence guarantee. The v12 sibling increases terminal-speed weight from 2 to 8 and sets terminal-position weight to 8. Initial physical rows match its v10 parent, while reward intentionally differs.

V12 completed 401,408 additional steps, reaching 7,306,736 lineage steps. Its final checkpoint scored 6/20, apparently better than v10's 5/20 on that small batch. The matched larger sample reversed the result: 29/256 (11.33%; Wilson interval 8.00-15.80%), with mean speed 2.29 m/s, tilt 4.78 degrees and pad offset 8.89 m. The final full-difficulty stage probe was 0/32. V10 is retained over v12 based on the larger sample. This reversal motivated using each checkpoint's largest sample and uncertainty in automatic selection.

V11 fixes a curriculum gap in the original takeoff pilot: it initially required the full 400 m climb even at difficulty zero. During v11 training only, altitude/velocity goals interpolate from 5 m / 3 m/s to 400 m / 25 m/s. Goal observations and reward use the actual reset goal; evaluation always retains the full task. The 500,000-step pilot completed 503,808 actual steps and reached difficulty 0.15, corresponding to 64.25 m / 6.30 m/s practice. It still scored 0/20 at every full-task checkpoint.

Matched deterministic practice probes scored 32/32 at the 125,000-step checkpoint's 44.50 m / 5.20 m/s goal and 32/32 at the final 64.25 m / 6.30 m/s goal. These are short-goal practice successes, not 400 m results. Each has a first-seed replay and visible training-only target labels. They use a separate seed pool, 23000-23031. The v13 takeoff sibling increases gamma/lambda to 0.999/0.995 and inherits the v11 actor; its million-additional-step pilot completed 1,507,328 lineage steps at difficulty 0.70. Full-task successes remained 0/20; the actual 281.5 m / 18.4 m/s practice goal scored 16/32. A continuation reached the full mission, as detailed below.

Current verification: 30 non-API Python tests passed, plus nine selected outcome/schema/Wilson tests from the API test module that do not use HTTP transport. The 13 HTTP/dispatch tests were deselected in that run; full current API transport remains pending. All 30 frontend tests, type checking, lint and production build passed. The source/build artifact validator checks practice labels/targets, larger sample CSVs and explicitly selected successful examples. The Training page charts actual rates on a 0-100% axis with Wilson intervals and retains exact counts in the adjacent table.


## Full ascent, conservative updates and CUDA comparison — 20 October

V13 takeoff continued to 2,011,136 lineage steps and full difficulty. It scored 16/20 on the checkpoint pool and 190/256 (74.22%; Wilson interval 68.53–79.19%) on the larger development pool. Mean terminal speed was 25.62 m/s against the 25 m/s ascent target, tilt 3.43 degrees and offset 2.82 m. This terminal speed is separation speed, not a landing impact.

A further million-step exact-config refinement completed 3,014,656 steps. Its intermediate 2,261,136 checkpoint scored 236/256 (92.19%; interval 88.24–94.89%), with speed 27.42 m/s, tilt 2.98 degrees and offset 2.04 m. The 2,761,136 checkpoint scored 254/256 (99.22%; interval 97.20–99.79%), with speed 25.74 m/s, tilt 2.36 degrees and offset 2.53 m. Both failures were pad misses. Its small checkpoint sample was 20/20, which is not a certainty claim. The final post-update checkpoint regressed to 15/20. Newer is therefore not automatically better.

The 2,761,136 candidate was frozen before a separate 10,000-seed nominal batch on seeds 10000–19999. A matched current-source classical L4 takeoff batch uses exactly those seeds and the same configuration. Candidate file hashes, configuration, source copies and evaluation journals are retained in `data/qualifications/` and `data/evaluations/`. The PPO batch completed 9,836/10,000 successes (98.36%; Wilson interval 98.0919–98.5910%). Failures were 89 pad misses, 65 excessive-tilt events and 10 separation-speed errors. The matched classical batch completed with 10,000/10,000 observed successes (Wilson lower bound 99.9616%), mean speed 24.9607 m/s, tilt 0.6652 degrees and offset 0.5685 m. They do not qualify every checkpoint, stress conditions or combined flight.

V14 is a fresh SAC comparison under the same full-difficulty landing physics, v10 reward and fixed observation scaling. Its 200,000-step pilot actually used CUDA and completed. All checkpoint full-task samples were 0/20; all four final stage probes were 0/32. The final full-difficulty probe had mean speed 156.97 m/s, tilt 84.06 degrees and offset 2,046.43 m. This short SAC budget is not comparable to the millions of inherited PPO updates and does not establish an algorithm-wide ranking. PPO remains the stronger measured candidate here.

V15 tests conservative optimization while preserving the v10 learned value function and optimizer moments: learning rate 0.00005 instead of 0.00015 and target KL 0.005 instead of 0.02. The explicit optimizer-adaptation path permits only these controls and the profile label to change; changed physics, reward, observations or credit settings are rejected. All 20 initial physical and raw reward rows match the parent exactly (`data/model-optimizer-transfer-validation.json`). Tests also verify preserved weights/optimizer state and actual updates after loading.

The v15 pilot added 401,408 steps. Its 7,305,328 pre-final snapshot scored 6/20 and 48/256 (18.75%; interval 14.44–23.98%). Mean speed was 2.59 m/s, tilt 4.02 degrees and offset 6.78 m. Compared with v10's 45/256, the three additional successes are uncertain; the intervals overlap. Its stage probes were 32/32, 21/32, 11/32 and 3/32. The final 7,306,736 snapshot had 4/20, so a trained final snapshot is saved and distinguished from the earlier rollout callback snapshot. Exact-config continuations of v10 and v15 are retained as separate jobs with added-step budgets.

Checkpoint callbacks can run before the PPO update that consumes their rollout. Training now always saves a post-update final snapshot after `learn`. If that step already has a callback snapshot, `-final` keeps both. The metadata states `snapshot_phase`; no earlier snapshot is overwritten.

## Numerical performance and telemetry provenance

Replacing SciPy quaternion conversion in each substep with normalized native MuJoCo math, plus the exact engine-lever cross-product expansion, measured a 2.04-times headless dynamics microbenchmark improvement (3,427 to 6,980 control steps/s). Parameters and integration are unchanged. Thirty-two open-loop trajectories and 64 feedback episodes using separate classical/PPO landing/takeoff actions matched outcomes and termination steps; largest position difference in feedback was about 3.45e-12 m. This does not measure browser GPU use, FPS or full training speed. Already-running workers retain their imported source; new workers snapshot the native implementation.

Saved replay producers now use telemetry 1.1 for checkpoint, episode difficulty, training-only mode and actual ascent-goal fields; archived 1.0 remains accepted. The running older API process still needs its separate restart to import changed source. The frontend build and static model replays can update without that restart.

The simulator remains approximate. In particular, absolute position and relative-goal observation features currently have independent noise in differently scaled feature units. They are not a physically specified coherent navigation sensor model. Both methods share rigid-body physics and mission thresholds, but the learned policy also receives these relative-goal features. Changing that observation contract would require an explicit version and new training; it has not been silently changed during these comparisons.


## Continuation and stress evidence

The v15 exact-config continuation added 1,003,520 actual steps, reaching 8,308,848 lineage steps. Its larger final sample was 47/256 (18.36%; interval 14.10–23.56%), compared with 48/256 for the retained 7,305,328 actor. Mean terminal speed worsened to 2.75 m/s while tilt improved to 3.06 degrees and pad offset to 5.76 m. Final stage probes were 32/32, 22/32, 13/32 and 5/32. These tradeoffs do not establish a general improvement. The continuation's initial saved actor was also checked on the same 256 seeds and exactly reproduced the parent's counts and physical means.

The matched takeoff stress pilots used the frozen v13 candidate and current classical L4 controller on 32 seeds each. Gusts scored 32/32 for both; fourfold sensor noise scored 2/32 classical and 16/32 PPO; 20% thrust loss scored 32/32 classical and 0/32 PPO; extreme starts scored 32/32 classical and 7/32 PPO. PPO thrust-loss failures were all separation-speed errors. These pilots qualify neither controller under those stress distributions; they expose the gap between nominal success and robustness.

The v16 landing profile adds a dense physical speed debit below 50 m, with coefficient 2 and quadratic proximity. The old reward profile's running cost omitted this near-ground speed term. Vehicle dynamics, observations and mission success thresholds are unchanged. It actor-warm-starts the v15 final policy, with fresh critic, optimizer and reward statistics; all 20 initial physical rows match exactly, while reward intentionally differs (`data/model-groundspeed-transfer-validation.json`). The million-additional-step pilot must be judged by measured full-task outcomes, not its changed reward magnitude.


The v10 exact-config continuation completed 8,908,272 lineage steps, adding 2,002,944 actual steps. Its 8,405,328 intermediate checkpoint scored 36/256, while the final improved to 65/256 (25.39%; Wilson interval 20.45–31.06%). Mean speed was 2.78 m/s, tilt 3.84 degrees and pad offset 4.37 m. The final first-seed stage probes scored 15/32, 13/32, 14/32 and 8/32. Better full-height pad accuracy came with forgetting of easier starts; this is still weak landing reliability. It replaces the earlier v15 48/256 actor under the largest-sample selection rule. A separate conservative optimizer refinement starts from this improved v10 final checkpoint, preserving its critic, optimizer moments and normalization under the unchanged reward.

Configured thrust-loss pilots give the classical controller the reduced maximum-thrust parameter. The policy has no explicit thrust-availability observation. These pilots are not proof of blind mid-flight failure recovery; that requires a distinct unannounced-fault experiment.


## Completed follow-up trials and live service update

The v15 refinement from the improved v10 actor completed 9,911,792 lineage steps. Larger matched development samples were 54/256 at 9,158,272, 58/256 at 9,408,272 and 48/256 at the final snapshot. The final mean speed was 2.46 m/s, tilt 5.07 degrees and pad offset 5.29 m. The final stage probes scored 2/32, 9/32, 13/32 and 4/32. Smaller optimizer updates did not beat the v10 parent's 65/256. Initial 20 physical/reward rows matched within 1e-8; tiny differences reflect the independently validated native-math implementation rather than changed control behavior.

V16 completed 9,312,368 lineage steps. Its larger sample scored 41/256 (16.02%; interval 12.03–21.01%), mean speed 3.13 m/s, tilt 3.14 degrees and offset 4.64 m. Stage probes scored 30/32, 15/32, 12/32 and 7/32. The near-ground penalty helped the easiest stage's speed but did not improve full-task reliability relative to v10. The failed trial remains published; it is not the default model.

A five-million-additional-step exact-config v10 continuation (`landing-ppo-pad-v10-long`) starts from 8,908,272 with 256 full-task checkpoint episodes on seeds 20000–20255. Its initial 56/256 is a different pool from the 65/256 development comparison on 22000–22255. A separate frozen v10 nominal 10,000-seed batch and matched current-source classical landing batch are being run on 10000–19999. Their frozen source and candidate manifests are separate from later live producer changes.

Elevated test execution became available on 20 October. The complete backend suite passed 52 tests, closing the previously restricted API transport/dispatch check for that source. The old services had exited; the verified inactive localhost ports were restarted under the existing hidden supervisor. Current production frontend/proxy/routes/textures passed real HTTP checks. Default RL checkpoint selection now considers compatible experiment variants, and a producer fix records the actual automatically selected checkpoint ID. Cross-mission IDs and one-checkpoint combined requests are rejected. Browser visual appearance, acceleration state, sound playback and FPS remain separate unverified gates.


## Joint failure diagnosis and isolated terminal-speed experiment

The v10 retained actor's 256 development landings met the speed threshold in 89 episodes, tilt in 200 and pad offset in 183. Only 65 met all three. Ninety-one failed speed alone, 39 speed plus offset, 18 speed plus tilt, and 19 all three. Nine failed tilt alone, ten tilt plus offset and five offset alone. These simultaneous criteria explain more than the priority-ordered failure label. `scripts/analyze_landing_failures.py` verifies every original success against the three physical thresholds and exports the measured scatter/count plot; it never changes recorded outcomes.

The v17 sibling changes only terminal-speed cost from 2 to 8 while preserving v10 lateral/terminal-position weights, full-height starts, observations and physical task. The earlier v12 trial also reduced the terminal-position weight, so its failure did not isolate speed cost. V17 actor-warm-starts the retained v10 checkpoint with a fresh critic/optimizer/reward transform, and runs 800,000 additional steps with 64 checkpoint episodes. It is a bounded empirical trial, not the default until measured results justify selection. The five-million-step exact v10 continuation remains a separate control.


## Frozen landing result

The unchanged v10 8,908,272 actor completed the restarted nominal batch on seeds 10000–19999 with 1,781/10,000 successes (17.81%; Wilson interval 17.0725–18.5722%). Failures were 7,453 speed events, 516 tilt events and 250 pad misses. Mean terminal speed was 3.0368 m/s, tilt 3.8274 degrees and offset 4.6284 m. This is materially below the previously selected 65/256 development sample; repeated model selection on that smaller pool can produce optimistic estimates. The failed disk-interrupted partial batch was not counted or combined with this completed batch.

The automatic development selector may prefer newer snapshots after larger evidence changes a candidate's lower bound. Its chosen model is therefore not necessarily the exact frozen candidate above. The qualification panel always names the precise checkpoint/configuration/seeds, while the development table and replay report their own provenance. New development selection is not a post-selection qualification guarantee.


The matched classical landing batch completed with 10,000/10,000 observed successes on the same current configuration and seeds, Wilson lower bound 99.9616%. Mean speed was 0.7274 m/s, tilt 0.7047 degrees and offset 1.0624 m. This remains a scoped nominal simulation comparison with disclosed information asymmetries.

The recovered long v10 job's 10,158,272 checkpoint reached 71/256 on its larger 20000–20255 callback pool and 72/256 (28.13%; interval 22.97–33.92%) on development seeds 22000–22255. Mean speed was 2.6658 m/s, tilt 3.4307 degrees and offset 3.7870 m. Its stage probes were 0/32, 7/32, 10/32 and 10/32; full-height improvement coexists with severe forgetting of the easy stage. Only the named older checkpoint has the frozen 10,000 result. The current selector may use this newer unqualified development candidate while explicitly preserving that distinction.


V17 completed 802,816 additional steps, reaching 9,711,088 lineage steps. The final checkpoint scored 8/64 on its callback pool and 22/256 (8.59%; interval 5.74–12.67%) on the matched development pool. Mean speed was 2.6358 m/s, tilt 5.1805 degrees and pad offset 5.7198 m. Stage probes were 0/32, 0/32, 4/32 and 3/32. Increasing the isolated terminal-speed coefficient did not improve reliability. The failed trial, source snapshot, initial physical-transfer comparison and first-seed failures remain retained; the default remains chosen by measured evidence.
