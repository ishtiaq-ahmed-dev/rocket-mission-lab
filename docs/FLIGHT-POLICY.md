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
3. **Flip and boostback.** About six seconds after separation, once the second
   stage has lit its engine and is clear, nitrogen cold-gas thrusters on the
   interstage turn the booster around at up to 12°/s; three engines
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
   throttle forces, to 1.4 m/s at touchdown. Sideways, above 150 m the booster
   holds two leans, each constant in the pad's frame (upper and lower half of
   the burn), solved with the full flight model so that it reaches 150 m over the
   pad with no sideways speed. While the air dominates, a lean makes body lift
   that carries the booster toward the pad; once the engine dominates, the same
   lean puts thrust into braking, so the booster accelerates and then brakes
   without rocking from one side to the other, as a Falcon 9 does. Below 150 m it
   comes down nearly vertical, nulling the last sideways drift. Typical leans are
   3-10°, never more than 20°.
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

### Prediction fixes

Two errors in the teacher's look-ahead were found and fixed while redesigning the
landing: the predicted touchdown point was compared with the pad's position at
the end of the integration step instead of at the touchdown moment (the pad moves
about 400 m/s with the Earth's rotation, which put an east-west error of up to
~100 m into every boostback, glide and landing prediction), and the boostback was
cut off from a plan up to 0.5 s old (at about 7 km of landing error per second
of boostback). With both fixed, the teacher lands within 1.4 m of the pad centre
on 300 of 300 dispersed flights and 2,298 of 2,300 in a stress test.

## Results

**Teacher.** 2,298 / 2,300 stress flights (seeds 500000-500299 and
700000-701999; the two misses touched down gently 15 and 26 m from the centre
but moving sideways too fast),
1,999 / 2,000 selection, 500 / 500 validation and 300 / 300 held-out flights;
median pad offset 0.4 m, worst touchdown 1.57 m/s.

**Shipped policy: `v5mineA`.** Same networks as before (booster 4 × 384 with
the two predictive inputs: the vacuum impact point, the cue for boostback
cutoff, and the undiverted touchdown point, the cue for the divert; upper stage
3 × 128), retrained on the redesigned landing teacher. Warm-started from the
previous weights, then 12 DAgger rounds of 250 policy-flown dispersed flights
(from round 5 at a lower learning rate); each round's candidate is compared
with the incumbent on 256 development seeds (no more catastrophic outcomes, a
crash above 5 m/s or a landing beyond 250 m; then more full missions; then a
smaller mean pad offset). The best round was then refined by *hard-example
mining* (`scripts/flight_policy/mine.js`): the network flies 6,000 fresh seeds,
the teacher labels the states the network reached on every seed where it failed
(and flies the seed itself), the labels are oversampled 5x, and a
low-learning-rate fine-tune follows. Candidates are scored on a separate
2,000-flight selection set and rejected if they land hard (above 5 m/s) more
often than the incumbent; a second mining loop scored 1,980 with nine hard
landings and was discarded. The held-out seeds were run once, for the shipped
network. Evidence: `data/flight-policy-validation.json`
(`node scripts/flight_policy/evaluate.js`).

| Dispersed flights | Neural policy | Classical teacher |
| --- | --- | --- |
| **Held-out, seeds 900000-900299** | **298 / 300** | 300 / 300 |
| Validation, seeds 600000-600499 | 497 / 500 | 500 / 500 |
| Development gate, seeds 800000-800255 | 256 / 256 | |
| Selection, seeds 300000-301999 | 1,997 / 2,000 | 1,999 / 2,000 |
| Fresh, seeds 466000-471999 | 5,976 / 6,000 | |
| Held-out reached orbit | 300 / 300 | 300 / 300 |
| Held-out median pad offset | 0.8 m | 0.4 m |

A full mission means orbit (perigee above 150 km, eccentricity below 0.05),
fairing released, payload deployed, and a touchdown on deployed legs slower than
3 m/s vertically and 1.5 m/s sideways, tilted under 5° and inside the 43 m pad
radius. Of the network's two held-out misses, one is a soft landing 60 m from
the pad; the other lit its landing burn too late and struck at 163 m/s. Late
landing-burn ignition is the network's one remaining catastrophic mode: it did
not occur on the 2,000 selection flights but did once in 300 held-out flights,
and one validation flight ended 6.6 km away after a misjudged boostback cutoff.
Across all evaluation sets the network completes 99.4-100 % of dispersed
missions (8,726 of 8,756 outside the held-out seeds).

**Landing smoothness.** The redesigned teacher holds two steady leans instead
of steering back and forth, and the network follows it. Over the nominal flight
and seven dispersed ones, the booster's lean during the landing burn travels
49° in total on average (teacher 23°; the previous network, trained on the old
zero-effort-miss teacher, 119°) and never exceeds 20° (previously 33°).

**Nominal replay compared with Falcon 9 RTLS** (Ax-4, 25 June 2025, and Dragon
cargo webcast timelines; booster apogee from CRS-10 webcast reconstructions):

| Event | This replay | Falcon 9 RTLS |
| --- | --- | --- |
| Max-Q | T+1:11, 25.7 kPa | T+1:12 |
| MECO | T+2:15, 58.4 km, 1.81 km/s | T+2:17-2:33, ~60-65 km, ~1.7 km/s |
| Boostback | T+2:36-3:30 | T+2:42-3:28 |
| Booster apogee | 125 km | ~130 km |
| Entry burn | T+6:06-6:17 (66 → 57 km) | T+6:18-6:30 |
| Landing burn | T+7:23 from 3.8 km | T+7:22-7:33 |
| Touchdown | T+7:48 | T+7:39 |
| SECO | T+8:23 | T+8:48 |

Touchdown at 1.31 m/s vertical, 0.06 m/s horizontal, 0.16° tilt, 1.2 m from
the pad centre; insertion 269 × 339 km at 42.2°; payload deploy T+9:23.

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
1,992 → 1,992 → 1,998 → 1,984). That network (`v4mineC`, 299/300 held-out)
inherited the old teacher's landing, whose zero-effort-miss divert swung the
booster's lean back and forth in the last kilometres. The landing was then
redesigned around two constant leans solved by prediction (above), the flip
moved to six seconds after separation, two prediction errors were fixed, and the
network retrained on it (`v5mineA`).

## Limits

- The network imitates a classical teacher; it is not optimised beyond it, and
  its reliability is a measured rate on simulated dispersions, not a guarantee.
- Point-mass translational dynamics with first-order attitude response; no
  rigid-body rotation, slosh, structural or thermal loads.
- The dispersion set is a simulation study, not a range-safety analysis.
