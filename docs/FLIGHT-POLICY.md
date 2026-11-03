# Neural flight policy and mission profile

The replay in `frontend/index.html` is flown end to end by a trained neural
network. Every command that changes the flight comes from it: engine ignition
and cutoff, engine count, throttle, attitude, stage separation, second-stage
ignition and cutoff, fairing jettison and payload deploy. The page contains the
physics and the network; there is no scripted guidance in it, and no fallback
controller. If the weights fail to load the page stops with an error instead of
flying something else.

## What the page runs

| Part | Where | Role |
| --- | --- | --- |
| Physics | `frontend/index.html` (simulator block) | WGS-84 gravity and rotation, ISO 2533 / US 1976 atmosphere, Mach-dependent drag and normal force, Merlin/MVac thrust with nozzle back-pressure, propellant flow, staging masses |
| Actuators | same block | engine spool-up and tail-off, minimum throttle 40 % (Merlin) / 39 % (MVac), no relight until a shutdown completes, gimbal / cold-gas / grid-fin slew limits, hold-down release, pneumatic stage separation that conserves momentum |
| Policy | `frontend/public/flight-policy.js` | two MLPs evaluated at 10 Hz on the vehicle's own state |

**Booster network** (stack during ascent, then the returning first stage):
48 inputs, 3 × 256 SiLU hidden layers, outputs thrust/attitude direction in the
local East-North-Up frame, throttle, engine count (0, 1, 3 or 9) and a staging
command. **Upper-stage network:** 26 inputs, 3 × 128, outputs attitude, throttle,
engine on/off, fairing jettison and payload deploy.

Inputs are things the vehicle can sense about itself: position and velocity
relative to LZ-1 at several scales, direction of motion, attitude, propellant,
engine state, dynamic pressure, Mach, and its own event clocks (time since MECO,
separation, last ignition, last cutoff). Phase labels on the HUD are *read out*
of that state (staged? which burn? engines on?); they never select behaviour.

## Mission profile and why each step is physical

Anchored to Falcon 9 return-to-launch-site practice (SpaceX user's guide, NASA
launch-and-landing sequence, public webcast telemetry):

1. **Ascent.** Hold-down until thrust exceeds weight at T-0, pitch kick, gravity
   turn, max-Q throttle bucket, 3.65 g acceleration limit.
2. **MECO and separation.** All nine engines cut, the engines finish their
   tail-off, then pneumatic pushers separate the stages with an equal and
   opposite impulse (1.8 m/s relative; the lighter booster recoils more). The
   upper stage lights its MVac about five seconds later, clear of the booster.
3. **Flip and boostback.** Cold-gas thrusters turn the booster; three engines
   burn with **horizontal thrust** toward the landing zone. The burn reverses
   the downrange velocity. It never points the thrust toward the ground: after
   separation the booster is still climbing, and gravity alone bends that
   climb into a fall.
4. **Ballistic coast.** Engines off, nose kept above the horizon with the
   engines leading, so the booster is already in its entry attitude.
5. **Entry burn.** Three engines at about 62 km, against the airflow, until the
   speed is below 400 m/s with only the landing budget left. Spare propellant is
   spent here rather than at the bottom, where one engine cannot throttle low
   enough to hover.
6. **Aerodynamic glide.** Engines off; grid fins trim the descent. The steering
   is chosen so the predicted touchdown lands on the pad.
7. **Landing burn.** One engine, lit at the last moment a burn at 85 % throttle
   can still stop at the pad (drag and mass loss included: with drag
   proportional to v², the constant-thrust stopping distance has a closed form).
   Side steering accounts for the aerodynamic normal force of an engine-first
   body, which at high dynamic pressure is larger than the engine's own side
   force and reverses the steering sense.
8. **Orbit insertion.** Closed-loop MVac guidance raises the stage to about
   270 km with zero climb rate and cuts off when the orbit's semi-major axis
   reaches 300 km; the payload deploys 60 s after SECO.

## How it was trained

`scripts/flight_policy/` (Node + PyTorch, not shipped):

- `teacher.js` — a classical teacher whose every command is a function of the
  present state, so it can label any state the network reaches. It predicts the
  rest of the return (burns, glide, landing burn) to touchdown and solves for
  the boostback heading/duration and the entry/glide steering that zero the
  predicted miss.
- `rollout.js`, `parallel.js` — episode runner over seeded dispersions (wind
  0-100 % in any direction, Merlin and MVac thrust ±1 %, drag ±5 %, booster dry
  mass ±300 kg, payload ±1,000 kg). Demonstrations add small pointing/throttle
  errors and randomly delayed discrete commands so the teacher also shows how to
  recover.
- `train.py` — behaviour cloning, exported as base64 float32 weights.
- `dagger.js` — DAgger: the network flies, the teacher labels the states it
  actually reaches, data is aggregated and the network retrained. Training uses
  file-backed minibatches and resumes the actual incumbent export rather than
  an unrelated local checkpoint. A separate candidate must pass a matched
  nominal + 256-seed development comparison before replacing the shipped file.
  The gate rejects worse speed/offset envelopes even when the success count rises.

```powershell
node scripts/flight_policy/dagger.js --fresh --demos 240 --iters 10 --per-iter 200
node scripts/flight_policy/parallel.js policy 900000 200   # evaluate on unseen seeds
node scripts/flight_policy/parallel.js teacher 900000 200  # same seeds, teacher
```

## Results

Shipped policy: `dagger8` (behaviour cloning on 240 dispersed and 40 nominal noisy
teacher demonstrations, then eight DAgger rounds of 200 policy-flown dispersed
flights). Candidates from later rounds were compared on the same held-out seeds
and the best one ships. Evidence: `data/flight-policy-validation.json`
(`node scripts/flight_policy/evaluate.js`).

**Held-out dispersed flights** (seeds 900000-900299, never used in training):

| | Full missions | Reached orbit | Worst touchdown | Worst pad offset |
| --- | --- | --- | --- | --- |
| Neural policy | **298 / 300** | 300 / 300 | 2.17 m/s | 49.8 m |
| Classical teacher | 295 / 300 | 300 / 300 | 2.06 m/s | 53.6 m |

A full mission means orbit (perigee above 150 km, eccentricity below 0.05),
fairing released, payload deployed, and a touchdown on deployed legs slower than 3 m/s vertically and 1.5 m/s
sideways, tilted under 5° and inside the 43 m pad radius. The policy's two
misses were soft touchdowns just outside the pad radius.

**Nominal replay** (what the page shows): liftoff T+0, MECO T+139 s at 71.9 km
and 1.78 km/s, separation T+142.5, MVac ignition T+147.6, boostback T+159-196,
booster apogee 184 km at T+294, entry burn T+457-483 (60.6 → 34.7 km),
landing burn T+550 from 2.1 km, touchdown T+568 at 1.82 m/s vertical,
0.03 m/s horizontal, 0.11° tilt, 0.2 m from the pad centre; SECO T+509 into a
270 × 341 km orbit at 39.5°, payload deploy T+569.

Training history (200 dispersed flights per round): round 1 0/200 (the cloned
policy flew every phase but crashed), round 6 165/200 after adding fine height
and sink-rate inputs for the last metres, rounds 8-13 between 188 and 197/200.

## Limits

- The network imitates a classical teacher; it is not optimised beyond it, and
  its reliability is a measured rate on simulated dispersions, not a guarantee.
- Point-mass translational dynamics with first-order attitude response; no
  rigid-body rotation, slosh, structural or thermal loads.
- The dispersion set is a simulation study, not a range-safety analysis.
