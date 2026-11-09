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
| Actuators | same block | engine spool-up and tail-off, minimum throttle 40 % (Merlin) / 39 % (MVac), no relight until a shutdown completes, gimbal / cold-gas / grid-fin slew limits, hold-down release, pneumatic stage separation that conserves momentum, a 4 s post-separation safety inhibit during which booster thrusters and engines cannot fire |
| Policy | `frontend/public/flight-policy.js` | two MLPs evaluated at 10 Hz on the vehicle's own state |

**Booster network** (stack during ascent, then the returning first stage):
52 inputs, 4 × 384 SiLU hidden layers, outputs thrust/attitude direction in the
local East-North-Up frame, throttle, engine count (0, 1, 3 or 9) and a staging
command. **Upper-stage network:** 26 inputs, 3 × 128, outputs attitude, throttle,
engine on/off, fairing jettison and payload deploy.

Inputs are things the vehicle can sense or compute about itself: position and
velocity relative to LZ-1 at several scales, direction of motion, attitude,
propellant, engine state, dynamic pressure, Mach, its own event clocks (time
since MECO, separation, last ignition, last cutoff), and two kinematic
predictions from its own state: the vacuum impact point and the touchdown point
of a landing burn with no sideways correction. Phase labels on the HUD are *read out*
of that state (staged? which burn? engines on?); they never select behaviour.

## Mission profile and why each step is physical

Anchored to Falcon 9 return-to-launch-site practice (SpaceX user's guide, NASA
launch-and-landing sequence, public webcast telemetry):

1. **Ascent.** Hold-down until thrust exceeds weight at T-0, a 2.2° pitch kick,
   gravity turn, a throttle bucket centred on T+48 s that caps dynamic pressure
   (max-Q falls at T+1:11, as on Falcon 9), 3.65 g acceleration limit. MECO comes
   with about 60 t of propellant left for the return, at about 60 km and
   1.8 km/s, so the booster coasts to about 126 km, as on RTLS flights.
2. **MECO and separation.** All nine engines cut, the engines finish their
   tail-off, then pneumatic pushers separate the stages with an equal and
   opposite impulse (1.8 m/s relative; the lighter booster recoils more). The
   upper stage lights its MVac about five seconds later, clear of the booster.
3. **Flip and boostback.** Cold-gas thrusters turn the booster; three engines
   burn toward the landing zone and reverse the downrange velocity. The thrust
   is horizontal on a normal flight; when dispersions leave the booster on a low
   arc (little time aloft), it is pitched up to 25° to loft the return instead
   of building a very fast, propellant-hungry return. It never points toward
   the ground: after separation the booster is still climbing, and gravity
   alone bends that climb into a fall.
4. **Ballistic coast.** Engines off, nose kept above the horizon with the
   engines leading, so the booster is already in its entry attitude.
5. **Entry burn.** Three engines at about 66 km, against the airflow, for about
   ten seconds: it sheds roughly 600 m/s and stops once only the landing budget
   (13 t) is left, as on Falcon 9 where the entry burn lasts 10-20 s. The booster
   then falls fast through the glide instead of drifting down slowly.
6. **Aerodynamic glide.** Engines off; grid fins trim the descent. The steering
   is chosen so that a landing burn with **no sideways correction** would
   touch down on the pad, as Falcon 9's grid fins line the booster up; the
   landing burn then only trims what is left.
7. **Landing burn.** One engine, lit at the last moment a burn at 85 % throttle
   can still reach the terminal gate (the ignition test integrates the stopping
   distance with drag rising as the air thickens). Vertically it is a hoverslam
   to 20 m above the pad, then a gentle deceleration just above what minimum
   throttle forces, to 1.4 m/s at touchdown. Sideways, above 150 m a
   zero-effort-miss law (with the aerodynamic side force of the near-vertical
   body in its prediction, and a braking cap against a runaway approach) zeroes
   position and velocity; below 150 m the booster comes down nearly vertical,
   nulling sideways speed first. Near the crossover where thrust side force and
   aerodynamic normal force cancel, the commanded tilt fades to zero instead of
   flipping sides.
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
node scripts/flight_policy/mine.js hardD 430000 6000 --fails-only   # hard-example mining
.venv/Scripts/python scripts/flight_policy/train.py --init-policy frontend/public/flight-policy.js --epochs 20 --lr 1e-4 --output candidate.js
```

## Results

**Teacher.** Stress-tested on 2,300 dispersed flights (seeds 500000-500299 and
700000-701999): 2,300 / 2,300 full missions, worst touchdown 1.57 m/s, worst
sideways speed 0.85 m/s, worst tilt 3.4°, median pad offset 2.2 m.

**Shipped policy: `v4mineC`.** The booster network was enlarged to 4 × 384 and
given two predictive inputs that the teacher's hardest decisions depend on: the
vacuum impact point (where the booster would come down if its engines stopped
now, the cue for boostback cutoff) and the undiverted touchdown point (where a
landing burn with no sideways correction would land, the cue for the divert).
Trained from scratch: behaviour cloning on 300 noisy teacher demonstrations,
14 DAgger rounds of 250 policy-flown dispersed flights, then *hard-example
mining* (`scripts/flight_policy/mine.js`): the network flies thousands of fresh
seeds, the teacher labels the states the network reached on every seed where it
failed (and flies the seed itself), the labels are oversampled 3-5x, and a
low-learning-rate fine-tune follows; four mining loops were run and each
candidate scored on a separate 2,000-flight selection set. Candidates are also
compared with the incumbent on 256 development seeds (no more catastrophic
outcomes, a crash above 5 m/s or a landing beyond 250 m, than the incumbent;
then more full missions); the held-out seeds were run once, for the shipped
network. Evidence: `data/flight-policy-validation.json`
(`node scripts/flight_policy/evaluate.js`).

| Dispersed flights | Neural policy | Classical teacher |
| --- | --- | --- |
| **Held-out, seeds 900000-900299** | **299 / 300** | 299 / 300 |
| Validation, seeds 600000-600499 | 499 / 500 | |
| Development gate, seeds 800000-800255 | 256 / 256 | |
| Selection, seeds 300000-301999 | 1,998 / 2,000 | 1,999 / 2,000 |
| Fresh, seeds 422000-427999 (before mining them) | 5,982 / 6,000 | |
| Held-out reached orbit | 300 / 300 | 300 / 300 |
| Held-out worst touchdown | 1.73 m/s | 1.56 m/s |

A full mission means orbit (perigee above 150 km, eccentricity below 0.05),
fairing released, payload deployed, and a touchdown on deployed legs slower than
3 m/s vertically and 1.5 m/s sideways, tilted under 5° and inside the 43 m pad
radius. On the held-out seeds the network and the teacher each miss one
mission, and neither crashes: the network's miss is a soft landing 234 m from
the pad, the teacher's 43.7 m (just past the radius). Across all evaluation
sets the network completes 99.7-99.9 % of dispersed missions; the predictive
inputs removed most of the boostback-cutoff errors that used to leave the
booster 100+ km away, which now remain only as rare (about 1 in 3,000) outliers.

**Nominal replay compared with Falcon 9 RTLS** (Ax-4, 25 June 2025, and Dragon
cargo webcast timelines; booster apogee from CRS-10 webcast reconstructions):

| Event | This replay | Falcon 9 RTLS |
| --- | --- | --- |
| Max-Q | T+1:11, 25.5 kPa | T+1:12 |
| MECO | T+2:15, 58.7 km, 1.81 km/s | T+2:17-2:33, ~60-65 km, ~1.7 km/s |
| Boostback | T+2:35-3:29 | T+2:42-3:28 |
| Booster apogee | 127 km | ~130 km |
| Entry burn | T+6:10-6:21 (66 → 56 km) | T+6:18-6:30 |
| Landing burn | T+7:27 from 3.9 km | T+7:22-7:33 |
| Touchdown | T+7:53 | T+7:39 |
| SECO | T+8:23 | T+8:48 |

Touchdown at 1.43 m/s vertical, 0.05 m/s horizontal, 0.16° tilt, 2.8 m from
the pad centre; insertion 269 × 336 km at 42.1°; payload deploy T+9:23.

Training history: a from-scratch run on the first RTLS-timeline teacher reached
297/300 held-out; a warm-started retrain after the max-Q throttle bucket reached
297/300 against the teacher's 298/300, with the misses traced to the teacher's
terminal landing control. That control was redesigned (terminal gate, braking-
limited zero-effort-miss divert, crossover fade, lofted boostback on low arcs),
taking the teacher from 299/300 to 2,300/2,300, and the network was retrained
on it: DAgger round 1 flew 3/300, round 4 283/300, round 10 257/257 on the
development gate; hard-example mining then took it to 299/300 held-out. Its
remaining misses were rare large diverts and boostback cutoffs held a few
seconds too long; the booster network was then enlarged and given the two
predictive inputs, retrained from scratch, and mined four times (selection
1,992 → 1,992 → 1,998 → 1,984; the best ships).

## Limits

- The network imitates a classical teacher; it is not optimised beyond it, and
  its reliability is a measured rate on simulated dispersions, not a guarantee.
- Point-mass translational dynamics with first-order attitude response; no
  rigid-body rotation, slosh, structural or thermal loads.
- The dispersion set is a simulation study, not a range-safety analysis.
