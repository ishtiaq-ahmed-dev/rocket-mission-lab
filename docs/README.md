# Documentation

## Falcon 9 RTLS replay (browser)

- [Neural flight policy and mission profile](FLIGHT-POLICY.md): what flies the rocket, why each phase is physical, how the network was trained and how it performs.
- [International-standard reference profile](STANDARDS.md): WGS-84, ISO 2533 / US 1976, public Falcon 9 anchors and the default-flight regression.
- [Research sources](RESEARCH.md)
- [Project history](HISTORY.md): earlier revisions, merged from the dated notes.

## Python laboratory (`rocket_lab/`, 400 m subscale vehicle)

- [Six-degree-of-freedom dynamics](01-dynamics.md)
- [Fuel flow and the rocket equation](02-rocket-equation.md)
- [The Markov decision process](03-mdp.md)
- [Reward shaping](04-reward.md)
- [Curriculum learning](05-curriculum.md)
- [Proximal policy optimization](06-ppo.md)
- [Soft actor-critic](07-sac.md)
- [Feedback control and LQR](08-pid-lqr.md)
- [Convex powered-descent approximation](09-convex-guidance.md)
- [Domain randomization and robustness](10-randomization.md)
- [Evaluation statistics](11-statistics.md)
- [Why RL and classical control differ](12-comparison.md)
- [API and telemetry](14-api-telemetry.md)
- [Training operations](15-training-operations.md)

Raw measurement files referenced by older notes remain under [evidence/](evidence/).
