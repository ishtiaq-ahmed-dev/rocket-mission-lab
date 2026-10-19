# The Markov decision process

## What it does

The agent maps a physical observation to throttle and two gimbal commands. An episode begins from a seeded distribution and ends in a specific mission outcome. The same underlying simulator is used by classical controllers. Observation noise and unobserved wind make the agent's actual information partially observable.

## Why this approach

Physical-state learning isolates control from vision. The observation contains position, velocity, quaternion, angular velocity, fuel fraction, clock, relative target, target ascent velocity, mass and previous throttle. There are no controller actions or expert demonstrations.

## Key formulas

```text
MDP = (S, A, P, r, gamma)
a in [-1,1]^3
pi(a | observed_state, relative_goal)
```

## Five interview questions

1. **Is the observation strictly Markov?** Not entirely: wind, gimbal actuator state and sensor noise are not fully observed. The full simulator state is Markov; the policy sees a partial observation.

2. **Why normalize actions?** A symmetric [-1,1] Box supports common continuous-control policies. Physics maps throttle to [0,1] and enforces an engine-on floor.

3. **Why include the goal?** The same state can require different behavior for different targets. Relative position provides that task context.

4. **How is combined flight handled?** A phase manager switches from ascent to descent at separation while retaining pose, velocity, mass and simulation time.

5. **Does a physical-state policy understand the 3D view?** No. Browser rendering is a display of telemetry and is not part of the policy observation.

## Evidence and further reading

See [research sources](RESEARCH.md), the relevant implementation in `rocket_lab/`, and the actual validation record in [VALIDATION.md](VALIDATION.md).
