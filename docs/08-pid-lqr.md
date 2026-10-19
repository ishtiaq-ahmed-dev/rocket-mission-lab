# Feedback control and LQR

## What it does

The untuned baseline uses weak altitude and attitude feedback. Tuned feedback tracks an altitude-dependent descent-speed reference. Engine gimbal couples lateral translation and attitude, and its initial lateral force can oppose the eventual desired correction. The final version models this chain with an LQR regulator.

## Why this approach

These controllers use a PD subset of the general PID family; no integral term is claimed. The LQR state is lateral position, velocity, body-axis tilt and tilt rate. Vertical feedforward differentiates the descent speed reference, reducing touchdown lag. Saturation and gimbal rate limits remain in physics.

## Key formulas

```text
PID: u = Kp*e + Ki*integral(e dt) + Kd*e_dot
LQR: minimize integral(x^T Q x + u^T R u) dt
A^T P + P A - P B R^-1 B^T P + Q = 0
u = -R^-1 B^T P x
```

## Five interview questions

1. **Is the implemented baseline a full PID?** It is PID-style cascaded feedback with proportional and derivative terms, no integral accumulator. The documentation states that explicitly.

2. **Why can cascaded loops oscillate?** Attitude lag and adverse initial gimbal translation add phase delay to lateral feedback.

3. **What does LQR optimize?** A quadratic state-and-input cost for a local linear model, not global fuel optimality for the nonlinear mission.

4. **Why use feedforward?** Tracking a changing velocity reference requires its expected acceleration as well as feedback on velocity error.

5. **What happens under actuator saturation?** The LQR assumptions no longer hold exactly. The physical simulator clips gimbal/thrust and evaluation exposes resulting failures.

## Evidence and further reading

See [research sources](RESEARCH.md), the relevant implementation in `rocket_lab/`, and the actual validation record in [VALIDATION.md](VALIDATION.md).
