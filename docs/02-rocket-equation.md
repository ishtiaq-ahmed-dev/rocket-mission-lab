# Fuel flow and the rocket equation

## What it does

Specific impulse converts propellant flow into thrust through an effective exhaust velocity. Each integration substep consumes only available propellant. The last substep caps delivered impulse so fuel cannot become negative. Mass and inertia are updated as fuel burns.

## Why this approach

The same effective exhaust velocity appears in the thrust law and Tsiolkovsky equation. We apply thrust/m acceleration and decrement mass; we do not add a second rocket-equation acceleration, which would double-count propulsion.

## Key formulas

```text
v_e = Isp * g0
mdot = -T / (Isp * g0)
delta_v_ideal = Isp * g0 * ln(m_initial / m_final)
```

## Five interview questions

1. **What does Isp measure?** Thrust divided by propellant weight flow; its units are seconds.

2. **Why does acceleration increase as fuel burns?** For the same thrust, T/m grows as mass falls.

3. **Why not directly add ideal delta-v each step?** Force integration already produces propulsion acceleration. Adding the ideal rocket equation separately double-counts it.

4. **Does this include gravity loss?** The dynamics integrate gravity and drag separately, so actual velocity gain differs from the ideal vacuum mass-ratio formula.

5. **What limits remain?** Constant Isp, simplified inertia scaling and unlimited restart commands omit pressure dependence, ignition delays and tank geometry.

## Evidence and further reading

See [research sources](RESEARCH.md), the relevant implementation in `rocket_lab/`, and the actual validation record in [VALIDATION.md](VALIDATION.md).
