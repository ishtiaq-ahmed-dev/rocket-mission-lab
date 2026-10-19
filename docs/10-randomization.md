# Domain randomization and robustness

## What it does

Seeded resets vary vehicle mass and thrust scale. Wind follows a mean-reverting gust process, air density decays exponentially with altitude, and the observation has configurable sensor noise. Curriculum scales disturbances during training; full evaluations use the complete distribution.

## Why this approach

Randomization reduces dependence on one ideal model. It does not prove transfer to reality. Robustness scenarios separately increase gusts and noise, reduce thrust, and widen initial conditions. Failure counts are reported per scenario rather than blended into a single flattering number.

## Key formulas

```text
d wind = k*(mean-wind)*dt + sigma*sqrt(dt)*normal(0,1)
rho(h) = rho0*exp(-h/H)
F_drag = -0.5*rho*Cd*A*||v-wind||*(v-wind)
```

## Five interview questions

1. **Why seed the gust process?** Matching seeds and action histories produces reproducible disturbances and directly comparable experiments.

2. **Are wind histories exactly identical across controllers?** The same random process is used on a common fixed integration clock, but different episode durations and control histories can change the observed prefix/termination.

3. **Does randomization guarantee sim-to-real transfer?** No. Unmodeled effects and incorrect parameter ranges can still dominate.

4. **What information advantage does classical control have?** Its modeled drag feedforward uses idealized wind information, while RL observes physical kinematics rather than explicit wind. Same physics does not mean identical estimator information.

5. **Why test thrust loss separately?** A controller can handle nominal randomization yet fail under a systematic engine degradation outside the training range.

## Evidence and further reading

See [research sources](RESEARCH.md), the relevant implementation in `rocket_lab/`, and the actual validation record in [VALIDATION.md](VALIDATION.md).
