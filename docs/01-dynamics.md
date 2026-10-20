# Six-degree-of-freedom dynamics

## What it does

MuJoCo advances one rigid body with a free joint. World z points up. Attitude is a unit quaternion in wxyz order. External force acts at the center of mass; a gimballed engine at the lower end creates torque through its physical lever. Four RK4 evaluations approximate continuous acceleration within each integration step.

## Why this approach

MuJoCo avoids maintaining a second hand-coded integrator for controllers versus RL. Fifty-hertz integration and ten-hertz control are explicit approximations. Changing mass requires mj_setConst, which resets qpos internally; live pose, velocity and time are restored afterward.

## Key formulas

```text
m v_dot = R(q) F_body + m g + F_drag
I omega_dot + omega cross (I omega) = tau
q_dot = 0.5 q multiply [0, omega]
```

## Five interview questions

1. **Why six degrees of freedom?** Three translations and three attitude coordinates determine spatial rigid-body motion; the quaternion stores attitude redundantly with a unit-length constraint.

2. **Why a quaternion?** It avoids Euler-angle singularities. MuJoCo uses wxyz, while Three.js uses xyzw; the renderer also changes from z-up to y-up.

3. **Where does torque come from?** From r cross F at the engine lever. No artificial attitude torque is added for the RL policy.

4. **How was the integrator checked?** Free fall is compared with h=h0+v0*t-0.5*g*t^2; vacuum energy and horizontal momentum are checked numerically.

5. **What is missing?** Flexible-body motion, detailed aerodynamics, contact stability, slosh and center-of-mass migration. The touchdown plane is a simplified COM-height test.

## Evidence and further reading

The native MuJoCo quaternion conversion normalizes a copy of the live wxyz quaternion, then calls `mju_quat2Mat`. The engine torque uses the exact expansion of `[0, 0, -length/2] cross F`. Neither change alters a physical parameter or the integrator. A concurrent-training microbenchmark measured 3,427 versus 6,980 control steps/s (2.04 times); this is headless dynamics only, not browser FPS or full training throughput. Saved pre-change and live dynamics matched outcomes and termination steps in 64 closed-loop classical/PPO landing/takeoff episodes. State errors were below 1e-5, with largest position error about 3.45e-12 m. See `data/physics-performance-validation.json` and `data/physics-closed-loop-validation.json`.

See [research sources](RESEARCH.md), the relevant implementation in `rocket_lab/`, and the actual validation record in [VALIDATION.md](VALIDATION.md).
