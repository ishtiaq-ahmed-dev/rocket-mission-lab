# Curriculum learning

## What it does

Training starts with a narrow position, velocity and tilt distribution and reduced disturbances. A rolling window tracks actual episode success. After the threshold is passed, difficulty widens until the full distribution is reached. Development evaluation always uses the full distribution.

## Why this approach

This keeps advancement tied to measured competence. Four vectorized environments collect experience; DummyVecEnv steps them sequentially in one process. An agent that never succeeds stays at its current curriculum stage, even if reward improves.

## Key formulas

```text
advance if successes_in_window / window_size >= 0.75
window_size = 40
difficulty_next = min(1, difficulty + 0.025)
```

## Five interview questions

1. **Why not start with the hardest distribution?** Sparse success and unstable attitude may prevent useful early learning.

2. **What triggers advancement?** At least 30 actual successes in the latest 40 training episodes, using the configured threshold.

3. **Can curriculum performance be reported as full-task reliability?** No. The full start distribution, noise and wind must be evaluated separately.

4. **What if the agent forgets earlier stages?** The current implementation widens a nested distribution; retention still needs evaluation. It does not guarantee immunity to forgetting.

5. **Is vectorization parallel simulation?** Not here. Four DummyVecEnv instances batch policy calls but step physics sequentially, avoiding Windows spawn memory overhead.

## Evidence and further reading

See [research sources](RESEARCH.md), the relevant implementation in `rocket_lab/`, and the actual validation record in [VALIDATION.md](VALIDATION.md).
