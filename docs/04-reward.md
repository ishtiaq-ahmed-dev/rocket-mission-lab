# Reward shaping

## What it does

The current `state-potential-v3` profile uses the change in a physical-state potential: remaining height/distance, total speed, tilt, angular rate and lateral error. Running costs discourage elapsed time, tilt, rotation, gimbal effort and fuel burn. Terminal rewards distinguish success from failure; capped speed/offset penalties make near misses informative. Historical profiles used distance progress with separate near-ground speed costs.

## Why this approach

Named shaping weights are in config.yaml, with the time-cost exception described below. Initial pilots learned faster failure without mission success, prompting reduced progress weight, stronger terminal speed costs and then state-potential shaping. These are empirical design changes, not evidence of convergence. Reward versions must be recorded when comparing curves.

## Key formulas

```text
Phi(s) = -w_height*remaining_height - w_speed*speed
         -w_tilt*(1-cos(tilt)) - w_rate*norm(angular_rate) - w_lateral*offset
r_v3 = Phi(s_next)-Phi(s) - dt*running_cost - w_fuel*fuel_burn
r_terminal += success_bonus or failure_penalty - terminal_error_cost
```

The current implementation retains a 0.3 per-second time cost in the v3 code path. This constant is an outstanding configuration-centralization limitation; the other named v3 potential/action/fuel/terminal weights are in `config.yaml`. Training snapshots identify the reward profile, and raw reward across profiles should not be ranked as comparable evidence.

## Five interview questions

1. **Can shaping change the optimum?** Yes. Our difference-of-potential term omits the gamma factor used in the formal policy-invariant shaping result, and other costs intentionally change preferences.

2. **How can reward be exploited?** Large progress reward may favor fast ground impact; weak time cost may favor hovering. Inspect actual termination reasons and trajectories.

3. **Why smooth terminal costs?** They give near misses different feedback instead of treating every failure identically.

4. **Why multiply running costs by dt?** It reduces dependence on control frequency, although discretization and termination effects still matter.

5. **Does higher reward mean success?** No. Success is computed from explicit mission thresholds, independently of reward magnitude.

## Evidence and further reading

See [research sources](RESEARCH.md), the relevant implementation in `rocket_lab/`, and the actual validation record in [VALIDATION.md](VALIDATION.md).
