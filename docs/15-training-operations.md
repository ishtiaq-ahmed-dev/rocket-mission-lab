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

Historical exploratory jobs lack complete immutable source snapshots. Older checkpoints are replayed using their training observation scale, but exact historical source/RNG reproduction is not certified. Full every-checkpoint qualification and robustness sweeps remain explicit compute jobs, never inferred from pilot curves.
