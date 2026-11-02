# The Markov decision process

## What it does

The agent maps a physical observation to throttle and two gimbal commands; some checkpoints also command three RCS channels. An episode begins from a seeded distribution and ends in a specific mission outcome. The same underlying simulator is used by classical controllers. Observation noise and unobserved wind make the agent's actual information partially observable.

## Why this approach

Physical-state learning isolates control from vision. The 22-value observation contains position, velocity, quaternion, angular velocity, fuel fraction, clock, relative target, target ascent velocity, mass, throttle and hold-down state. Wind, gravity and gimbal state are not direct inputs. PPO/SAC training uses rewards rather than expert actions; BC checkpoints are trained from classical demonstrations and may use a classical terminal guard.

## Key formulas

```text
MDP = (S, A, P, r, gamma)
a in [-1,1]^3 or [-1,1]^6 with RCS
pi(a | observed_state, relative_goal)
```

## Five interview questions

1. **Is the observation strictly Markov?** Not entirely: wind, gimbal actuator state and sensor noise are not fully observed. The full simulator state is Markov; the policy sees a partial observation.

2. **Why normalize actions?** A symmetric [-1,1] Box supports common continuous-control policies. Physics maps throttle to [0,1] and enforces an engine-on floor.

3. **Why include the goal?** The same state can require different behavior for different targets. Relative position provides that task context.

4. **How is combined flight handled?** The environment checks the ascent target and initiates cutoff and separation; the model does not command staging. The phase manager then switches to descent while retaining pose, velocity, mass and simulation time.

5. **Does a physical-state policy understand the 3D view?** No. Browser rendering is a display of telemetry and is not part of the policy observation.

## Evidence and further reading

See [research sources](RESEARCH.md), the relevant implementation in `rocket_lab/`, and the validation history in [HISTORY.md](HISTORY.md).
