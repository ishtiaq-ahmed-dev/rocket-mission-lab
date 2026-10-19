# Why RL and classical control differ

## What it does

Classical guidance encodes physical structure and can work before collecting training episodes. RL optimizes a parameterized policy through sampled rewards and can learn behaviors absent from a hand-designed law. Both remain limited by their model, observation and actuator assumptions.

## Why this approach

The project preserves failed runs and real learning curves. A reward increase without success is learning progress only in the reward objective. Four named replay slots are a storytelling interface, not automatic evidence of four maturity stages. Algorithm choice should be based on held-out success and robustness at an explicit compute budget.

## Key formulas

```text
classical: state -> explicit guidance law -> actuator command
RL: state -> learned neural policy -> actuator command
comparison: same dynamics, start seeds, outcome thresholds and scenario
```

## Five interview questions

1. **Why can classical win with little data?** It exploits known mechanics and design insight; its engineering effort is not counted as training samples.

2. **Why might RL eventually improve?** It may optimize nonlinear or coupled strategies across many samples, provided the observation/reward and coverage support them.

3. **Is this a perfectly fair information comparison?** Physics and seeds match, but classical modeled wind feedforward is an information advantage. Report it rather than obscuring it.

4. **What qualifies a Final level?** A label alone does not. Held-out success, uncertainty, robustness and independent qualification are needed.

5. **Would you fly this controller on hardware?** No. This educational simulator omits many flight-critical effects and has no certification, hardware-in-loop or safety case.

## Evidence and further reading

See [research sources](RESEARCH.md), the relevant implementation in `rocket_lab/`, and the actual validation record in [VALIDATION.md](VALIDATION.md).
