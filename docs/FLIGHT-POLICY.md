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
   without rocking from one side to the other, as a Falcon 9 does. The lean fades
   out over the last 50 m above 150 m, and below 150 m the booster comes down
   nearly vertical, nulling the last sideways drift. Typical leans are 3-10°,
   never more than 20°.
   *Faults.* If the engine goes out during the burn, the booster glides on its
   grid fins and relights at the ignition point. If the burn overshoots and the
   booster stops above the pad, it shuts the engine down (one Merlin at minimum
   throttle still lifts a nearly empty booster, so it cannot hover), falls, and
   relights once it is falling fast enough for a gentle stop.
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
  recover, and some training flights carry an engine fault in the landing burn
  (a cutoff of 0.5-1.5 s at 1-3.5 km, or three engines instead of one for
  0.5-1 s at 100-300 m) so the data shows the glide, hop and relight that follow.
- `train.py` — behaviour cloning, exported as base64 float32 weights. The
  training set is held on the GPU when it fits (with room left for other work),
  so minibatches are drawn there instead of from files on disk.
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

### Teacher fixes

Two errors in the teacher's look-ahead were found and fixed while redesigning the
landing: the predicted touchdown point was compared with the pad's position at
the end of the integration step instead of at the touchdown moment (the pad moves
about 400 m/s with the Earth's rotation, which put an east-west error of up to
~100 m into every boostback, glide and landing prediction), and the boostback was
cut off from a plan up to 0.5 s old (at about 7 km of landing error per second
of boostback). The boostback planner also returns the best plan it actually
predicted: near cutoff the heading has almost no lever, the Newton solve can run
out of iterations, and it used to return its last, untested step, which on one
dispersed flight meant four more seconds of burn 50° off course and a 12 km miss.

**Landing-burn labels.** The previous network's rare crashes (about 1 in 1,000
flights, at 160-250 m/s) were not late ignitions. Its engine history showed
that the teacher's labels had taught them:

- When the engine was off during the landing burn, the landing law said "stay
  off". Whenever the network cut its engine early, the data told it to keep
  falling: 147,014 such labels were in the training set, 14,440 of them from the
  network's own crashes on fresh seeds.
- When the booster was rising above the pad, the law kept thrusting upward
  (98,072 labels). After a brief, wrong three-engine command about 140 m up, the
  network stopped, climbed back to about 4 km, ran out of propellant and fell.
- The lean switched from the two-lean law to the hold law with a step of 2-4° at
  150 m. The network had to learn a sharp edge there, and its engine-count output
  jumped at the same height: that is where the wrong three-engine commands came
  from.

The teacher now relights after a cutoff, cuts and falls instead of climbing, and
fades the lean; the mislabelled rows (278,423 in all) were removed and the
training flights carry engine faults. With these fixes the teacher completes
2,000 / 2,000 selection flights (previously 1,999), with a worst pad offset of
3.5 m (previously 32 m).

## Results

**Teacher.** 2,300 / 2,300 stress flights (seeds 500000-500299 and
700000-701999), 2,000 / 2,000 selection, 500 / 500 validation, 300 / 300 held-out
and 1,000 / 1,000 new held-out flights; median pad offset 0.4 m, worst
touchdown 1.57 m/s.

**Shipped policy: `v6r4`.** Same networks as before (booster 4 × 384 with the
two predictive inputs: the vacuum impact point, the cue for boostback cutoff,
and the undiverted touchdown point, the cue for the divert; upper stage 3 × 128),
retrained from `v5mineA` on the fixed teacher. Four DAgger rounds: in each, the
network flew 400 flights with a forced engine fault and 400 normal flights, the
teacher labelled the states it reached, and a fine-tune followed (rounds 3 and 4
on the booster network only). Every round was scored on the 2,000-flight
selection set and on two fault-recovery tests. Round 4 completed all 2,000
selection flights; it was then checked on validation, development and 6,000
fresh seeds, and the held-out seeds were run once. Evidence:
`data/flight-policy-validation.json` (`node scripts/flight_policy/evaluate.js`).

| Dispersed flights | Neural policy | Classical teacher |
| --- | --- | --- |
| **Held-out, seeds 900000-900299** | **300 / 300** | 300 / 300 |
| **New held-out, seeds 910000-910999** | **1,000 / 1,000** | 1,000 / 1,000 |
| Validation, seeds 600000-600499 | 500 / 500 | 500 / 500 |
| Development gate, seeds 800000-800255 | 256 / 256 | |
| Selection, seeds 300000-301999 | 2,000 / 2,000 | 2,000 / 2,000 |
| Fresh, seeds 472000-477999 | 6,000 / 6,000 | |
| Held-out median pad offset | 0.6 m | 0.4 m |

A full mission means orbit (perigee above 150 km, eccentricity below 0.05),
fairing released, payload deployed, and a touchdown on deployed legs slower than
3 m/s vertically and 1.5 m/s sideways, tilted under 5° and inside the 43 m pad
radius. Across all 10,056 dispersed evaluation flights the network completed
every mission; its worst touchdown was 2.0 m/s and its worst pad offset 35 m.
On the same 6,000 fresh seeds the previous network (`v5mineA`) completed 5,987:
four crashes at 190-250 m/s, one boostback 12.7 km off, eight soft landings off
the pad.

**Engine faults.** 100 dispersed flights per fault (seeds 620000-620099), the
fault forced during the landing burn:

| Fault | `v6r4` | `v5mineA` | Teacher |
| --- | --- | --- | --- |
| Engine out for 1 s at 2,500 m | 100 | 0 | 100 |
| Engine out for 1 s at 1,500 m | 99 | 0 | 100 |
| Three engines for 0.8 s at 250 m | 100 | 25 | 100 |
| Three engines for 0.8 s at 120 m | 100 | 0 | 100 |

**Landing smoothness.** Over the nominal flight and 39 dispersed ones, the
booster's lean during the landing burn travels 47° in total on average (previous
network 46°, teacher 27°; the network before that, trained on the old
zero-effort-miss teacher, 119° on eight flights) and never exceeds 19°.

**Nominal replay compared with Falcon 9 RTLS** (Ax-4, 25 June 2025, and Dragon
cargo webcast timelines; booster apogee from CRS-10 webcast reconstructions):

| Event | This replay | Falcon 9 RTLS |
| --- | --- | --- |
| Max-Q | T+1:11, 25.5 kPa | T+1:12 |
| MECO | T+2:15, 58.8 km, 1.81 km/s | T+2:17-2:33, ~60-65 km, ~1.7 km/s |
| Boostback | T+2:36-3:30 | T+2:42-3:28 |
| Booster apogee | 127 km | ~130 km |
| Entry burn | T+6:10-6:21 (66 → 56 km) | T+6:18-6:30 |
| Landing burn | T+7:28 from 3.6 km | T+7:22-7:33 |
| Touchdown | T+7:53 | T+7:39 |
| SECO | T+8:23 | T+8:48 |

Touchdown at 1.44 m/s vertical, 0.06 m/s horizontal, 0.20° tilt, 1.4 m from
the pad centre; insertion 269 × 342 km at 41.8°; payload deploy T+9:23.

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
network retrained on it (`v5mineA`, 298/300 held-out). Its rare crashes were
then traced to the teacher's landing-burn labels and boostback planner (Teacher
fixes, above); four DAgger rounds with engine faults in the training flights
produced `v6r4` (selection 1,994 → 1,995 → 1,999 → 2,000; the early rounds
briefly learned new mistakes, such as cutting the engine mid-burn, which the
next round's labels removed).

## Limits

- The network imitates a classical teacher; it is not optimised beyond it, and
  its reliability is a measured rate on simulated dispersions, not a guarantee.
- Point-mass translational dynamics with first-order attitude response; no
  rigid-body rotation, slosh, structural or thermal loads.
- The dispersion set is a simulation study, not a range-safety analysis.
