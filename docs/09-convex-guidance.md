# Convex powered-descent approximation

## What it does

A finite-horizon trajectory uses position, velocity and acceleration variables. Linear discrete dynamics, an upper thrust norm bound and an approximate pointing cone form a second-order cone problem. CLARABEL solves it; an attitude controller tracks the resulting reference.

## Why this approach

Constant mass keeps the problem convex and inspectable. A positive lower thrust norm is nonconvex and is relaxed in planning; physics still enforces it. Reference tracking has real attitude lag. Solver status is recorded, and a documented feedback fallback handles infeasibility.

## Key formulas

```text
p_(k+1) = p_k + v_k*dt + 0.5*a_k*dt^2
v_(k+1) = v_k + a_k*dt
||a_k - g|| <= T_max / m_assumed
minimize sum ||a_k||^2 + small_weight*sum ||v_k||^2
```

## Five interview questions

1. **Is this lossless convexification?** No. It is a simplified constant-mass convex approximation, without a proof that a relaxation recovers the original optimum.

2. **Why is minimum thrust hard?** The set outside a norm ball is nonconvex, while an upper norm bound defines a convex set.

3. **Does a feasible plan guarantee successful flight?** No. Mass changes, gimbal rate limits, attitude tracking, disturbances and approximation error can invalidate it.

4. **Is the objective fuel optimal?** It minimizes squared acceleration plus a velocity term. It is not an exact propellant-minimization formulation.

5. **What happens if the solver fails?** The run retains a solver-status label and uses the feedback controller. Results must not call that flight an optimal-solver success.

## Evidence and further reading

See [research sources](RESEARCH.md), the relevant implementation in `rocket_lab/`, and the actual validation record in [VALIDATION.md](VALIDATION.md).
