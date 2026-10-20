# Training operations and reproducibility

## What it does

PPO and SAC jobs save progress heartbeats, episode outcomes, development evaluations, TensorBoard events, model weights and VecNormalize statistics. A stop marker requests orderly termination and a final checkpoint. Completed models can generate real telemetry through the same simulator.

## Why this approach

The frontend starts at most one active API-managed job. CLI research jobs were separately supervised. BLAS thread pools are capped. Atomic replacement retries short Windows reader locks, and stale heartbeats are displayed instead of remaining green indefinitely. GPU capability was verified by a real matrix multiply, not just device enumeration.

## Key formulas and procedure

```text
throughput = environment_steps / elapsed_seconds
checkpoint = weights + normalization + config + measured development evaluation
qualification = distinct fixed seeds + outcome CSV + confidence interval
```

## Five interview questions

1. **Does a seed guarantee bitwise reproducibility?** No. Hardware, package versions, floating-point kernels and scheduling can differ. Record runtime and configuration, and compare within a stated environment.
2. **Why can a machine with free RAM fail allocations?** Windows commit headroom includes private committed virtual memory and pagefile capacity. Several Torch processes can exhaust commit before physical RAM is full.
3. **What survives closing the browser?** Backend subprocess training continues. Closing the page does not request a stop; operating-system reboot and job-container termination are separate lifecycle events and are not qualified.
4. **Can a checkpoint resume exactly?** PPO continuation restores network and optimizer state, normalization, step count and curriculum difficulty under a matching configuration. Environment/RNG trajectories restart. SAC resume is explicitly rejected because the replay buffer is not preserved. Neither path claims bit-for-bit continuation.
5. **What did the scratch lesson prove?** REINFORCE learned CartPole from sampled rewards and exceeded a random baseline on 20 fixed evaluation episodes. It illustrates policy gradients; it does not validate rocket control.

## Limits

Historical exploratory jobs lack complete immutable source snapshots. New v4 jobs copy the simulation/training source files into the job directory and record a SHA256 source hash in checkpoint metadata. This improves provenance but is not a complete dependency lock or bitwise reproduction guarantee. Older checkpoints are replayed using their training observation scale, but exact historical source/RNG reproduction is not certified. Full every-checkpoint qualification and robustness sweeps remain explicit compute jobs, never inferred from pilot curves.

## Explicit variants and transfer

`--config config/training-v4.yaml` selects the complete experimental snapshot without changing the baseline config. Its hash is saved with every job, checkpoint, result and explicit telemetry export. `--resume` requires the exact recorded configuration. `--warm-start` instead copies only a compatible PPO actor and records parent lineage while leaving the critic, optimizer and reward statistics fresh. It rejects changed vehicle/world/mission settings and observation scales. The initial transferred v4 actor matched all 20 parent physical evaluation rows before training.

```powershell
python scripts/training_worker.py landing-ppo-lateral-v4-continued --steps 800000 --resume landing-ppo-lateral-v4-pilot__step-003951808 --config config/training-v4.yaml
python -m rocket_lab.probe landing-ppo-lateral-v4-pilot__step-003951808 --episodes 32
```

Development checkpoint evaluation uses seeds 20000 onward at full difficulty. Separate stage probes use seeds 21000 onward at difficulties 0.20, 0.40, 0.60 and 1.00; their summary is published to the Training page. Neither sample is a 10,000-seed qualification. Quartile checkpoints are measured relative to the additional step budget when continuing.

The latest CLI continuation runs in a foreground command session under workspace permissions. It must not be described as surviving a closed task, reboot or Windows job termination. The earlier backend/production-preview services were started separately before automatic approval review became unavailable. Current API imports were not restarted for the experimental profile; explicit checkpoint replay is available, while default selection still follows the baseline hash.

## Mixed starts

The v5 experimental snapshot keeps the v4 reward and physics but sets `full_start_probability: 0.2`. Only `training=True` environments enable it. The remaining resets use the current curriculum stage; full-start outcomes are logged with their actual difficulty and excluded from easier-stage advancement. Noise and timeout are tied to the reset's difficulty for the whole episode. Disabled mixing consumes no additional random draw. Full-task evaluation and stage probes never enable mixing. This is an empirical training distribution change; its effects must be measured independently.

Fixed-seed stage replays are exported to `frontend/public/model-replays/` and the current production build. Each uses the first probe seed, with the recorded outcome compared against the probe row before publication. The Training page opens them directly and labels development difficulty. `scripts/validate_model_artifacts.py` checks file-level integration; it is not a browser test.

## Output architecture

`config/training-v6.yaml` enables `BoundedMeanPolicy`: tanh on the diagonal-Gaussian mean, without changing PPO's sample likelihood or adding control logic. Gaussian tail actions are still clipped by SB3. This is an architectural experiment, distinct from SAC's fully squashed Gaussian. When the parent uses a linear mean, actor weights transfer but its function changes; the job's lineage records this. Compare the initial transformed policy separately from subsequent learning. Policy code is included in new source snapshots, and serialization is exercised by a real save/load test.

The v7 snapshot instead retains the linear actor and resets throttle exploration std to 0.15 on warm start, leaving gimbal std unchanged. `warm_start_action_std` accepts a positive finite value or null per action; null preserves the inherited std. This changes the sampled distribution while keeping deterministic mean actions unchanged, verified on 20 full-task rows. Exact-config continuation restores the saved distribution and does not apply the reset again.

## Full-task credit and pad accuracy

The v8 snapshot sets training difficulty to 1.0, and `warm_start_difficulty` explicitly selects that initial stage for actor transfer. Goals and reset difficulty remain fixed during each episode. The v9 snapshot changes PPO gamma/lambda to 0.999/0.995 with the same physical task and v4 reward. Its continuation uses the exact variant hash and restores optimizer/reward statistics. The v10 sibling separately increases lateral potential and terminal-offset costs; reward values must not be compared with v9. Initial physical rows are matched before updates, with reward intentionally excluded for v10.

`scripts/evaluate_model.py` publishes a named larger development sample with a retained seed journal, CSV, confidence interval and summary. Optional successful examples select the first successful seed and disclose that outcome selection. These are distinct from first-seed stage replays and from the 10,000-episode qualification pool.

## Ascent-goal curriculum

The v11 takeoff snapshot enables shorter goals only in training. At difficulty zero, the goal is 5 m altitude / 3 m/s ascent; it interpolates to the complete 400 m / 25 m/s task at difficulty one. The physical vehicle/world and full mission thresholds remain unchanged. The actual goal is included in observations and reward; it changes on reset, never mid-flight. Evaluation disables this training-only curriculum. The Training page displays the current stage goal beside the separate full-task requirement. Tests verify goal observations, stage changes and full evaluation targets.

`python -m rocket_lab.practice CHECKPOINT --episodes 32` measures the checkpoint's recorded short ascent goal on seeds 23000 onward, exports its first-seed replay and publishes a training-only label. It does not replace full-task evaluation. Telemetry carries explicit training mode and target altitude/velocity. The v13 sibling keeps this curriculum and uses a longer GAE horizon; initial transfer behavior and full mission checks remain separate.

## Conservative adaptation and frozen qualification

`--adapt-optimizer-from CHECKPOINT` preserves actor, critic, optimizer moments and normalization while allowing only learning rate, PPO target KL and the training-profile label to change. It rejects changed physics/reward/observation/credit settings. This is distinct from actor-only warm start, which intentionally creates a fresh critic, optimizer and reward statistics. The post-update final snapshot is always saved; a `-final` suffix preserves an earlier callback snapshot at the same step.

`python scripts/qualify_model.py --mission takeoff --checkpoint CHECKPOINT --id UNIQUE-ID` freezes candidate file hashes and source copies before a journalled nominal batch on seeds 10000–19999. Omitting the checkpoint evaluates classical L4 on the same task. Results use unique filenames, preserving small development samples. This qualifies the exact nominal candidate/configuration only. `scripts/stress_models.py` separately runs four matched 32-seed stress pilots; their effective config hash records each disturbance change.

The production Training page reads static qualification summaries and current-batch progress, alongside API training jobs and explicit replay files. The progress publisher is bounded to the current local batches and exits when both result files exist; it is not a durable service or a scheduled automation. Current foreground jobs must finish before closing their command sessions. New backend checkpoint selection uses compatible physical settings, the largest nominal sample and its Wilson lower bound; the running older API needs a restart before using that source change.


The running API was updated on 20 October and the live default selector/telemetry attribution checked through the production proxy. `training_worker.py --eval-episodes 256` gives longer landing continuations a larger fixed checkpoint pool. The `landing-ppo-pad-v10-long` job is launched independently of the interactive terminal through the existing Windows process mechanism; inspect its actual heartbeat/PID/log before assuming it is active. It still requires the PC to stay on and is not configured to start before login or after reboot.


After the D: exhaustion incident, the current five-million-step job is `landing-ppo-pad-v10-long-recovered`, starting from the intact 8,908,272-step checkpoint. The interrupted predecessor is retained as failed. A low-space stop below 64 MiB requests a final checkpoint; below 32 MiB no new checkpoint is attempted. Free adequate disk space before resuming a stopped worker. Failed partial qualification journals remain immutable evidence; restarted `-r2` batches use new source identities and manifests.
