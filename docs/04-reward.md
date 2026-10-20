# Reward shaping

## What it does

The baseline `state-potential-v3` profile uses the change in a physical-state potential: remaining height/distance, total speed, tilt, angular rate and lateral error. The experimental `state-potential-v4` variant adds an explicit horizontal-speed term and stronger pad-offset weights. Running costs discourage elapsed time, tilt, rotation, gimbal effort and fuel burn. Terminal rewards distinguish success from failure; capped speed/offset penalties make near misses informative. Historical profiles used distance progress with separate near-ground speed costs.

## Why this approach

Baseline shaping weights are in config.yaml; the full v4 snapshot is config/training-v4.yaml. Initial pilots learned faster failure without mission success, prompting reduced progress weight, stronger terminal speed costs and then state-potential shaping. These are empirical design changes, not evidence of convergence. Reward versions must be recorded when comparing curves.

## Key formulas

```text
Phi(s) = -w_height*remaining_height - w_speed*speed
         -w_tilt*(1-cos(tilt)) - w_rate*norm(angular_rate) - w_lateral*offset
r_v3 = Phi(s_next)-Phi(s) - dt*running_cost - w_fuel*fuel_burn
Phi_v4(s) = Phi_v3(s) - w_horizontal_speed*norm(velocity_xy)
r_terminal += success_bonus or failure_penalty - terminal_error_cost
```

The implementation reads `time_cost` with a 0.3 per-second fallback, preserving old v3 behavior. The v4 snapshot explicitly records 0.3. Its horizontal-speed weight is 12, lateral-position weight is 4 (v3: 2), and terminal-position weight is 2 (v3: 1). Physics, mission thresholds and physical observation scales are unchanged. Training snapshots identify the reward profile; compare actual speed/tilt/offset and success counts across profiles, not raw reward. The first v4 pilot improved easier-stage samples while full-task success remained zero. See [the measured model iteration](MODEL-ITERATION-2026-10-19.md).

The separate v16 experiment adds a dense landing-only physical speed cost below 50 m:

```text
r_ground = -dt * 2 * max(0, 1-max(0, altitude)/50)^2 * norm(velocity)^2
```

It gives near-surface high-speed states a continuous debit before the terminal event. It supplies no desired speed curve, burn time, controller action or expert data. It is an empirical reward change, not a guarantee of faster learning or a formally invariant transform. Missing/zero `ground_speed_cost` preserves prior rewards exactly. Tests verify the calculated debit, unchanged physical observations/outcomes, zero effect above the configured height and no takeoff effect. Invalid weights/heights are rejected. Baseline configuration and success criteria remain unchanged.

## Five interview questions

1. **Can shaping change the optimum?** Yes. Our difference-of-potential term omits the gamma factor used in the formal policy-invariant shaping result, and other costs intentionally change preferences.

2. **How can reward be exploited?** Large progress reward may favor fast ground impact; weak time cost may favor hovering. Inspect actual termination reasons and trajectories.

3. **Why smooth terminal costs?** They give near misses different feedback instead of treating every failure identically.

4. **Why multiply running costs by dt?** It reduces dependence on control frequency, although discretization and termination effects still matter.

5. **Does higher reward mean success?** No. Success is computed from explicit mission thresholds, independently of reward magnitude.

## Evidence and further reading

See [research sources](RESEARCH.md), the relevant implementation in `rocket_lab/`, and the actual validation record in [VALIDATION.md](VALIDATION.md).


The v17 sibling isolates one terminal-cost change: speed coefficient 8 instead of 2, with terminal-position coefficient still 12. V12 had changed both coefficients, so its results did not isolate the speed term. V17 keeps the same success thresholds and state observations, and uses a separately recorded fresh critic after actor transfer. Its reward magnitude is not comparable to v10; compare physical outcomes instead.
