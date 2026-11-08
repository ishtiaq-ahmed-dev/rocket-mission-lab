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

1. **Ascent.** Hold-down until thrust exceeds weight at T-0, a 2.6° pitch kick,
   gravity turn, max-Q throttle bucket, 3.65 g acceleration limit. MECO comes
   with about 60 t of propellant left for the return, at about 60 km and
   1.8 km/s, so the booster coasts to about 126 km, as on RTLS flights.
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
5. **Entry burn.** Three engines at about 66 km, against the airflow, for about
   ten seconds: it sheds roughly 600 m/s and stops once only the landing budget
   (13 t) is left, as on Falcon 9 where the entry burn lasts 10-20 s. The booster
   then falls fast through the glide instead of drifting down slowly.
6. **Aerodynamic glide.** Engines off; grid fins trim the descent. The steering
   is chosen so the predicted touchdown lands on the pad.
7. **Landing burn.** One engine, lit at the last moment a burn at 85 % throttle
   can still stop at the pad. The ignition test integrates the stopping
   distance with drag rising as the air thickens on the way down; the burn
   itself holds the constant thrust that ends the descent at touchdown speed.
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

Shipped policy: `dagger8` of the real-timeline training run. The teacher was
retuned to the Falcon 9 RTLS timeline (flatter ascent, MECO with the return
propellant kept, short entry burn, drag-aware landing-burn ignition, smooth
terminal insertion guidance) and the network trained from scratch: behaviour
cloning on teacher demonstrations, then DAgger rounds of 200-300 policy-flown
dispersed flights. Each candidate is compared with the incumbent on the same 256
development seeds before it ships; while no network can yet fly the nominal
mission, the gate ships whichever is further along (missions, then orbits, then
pad offset). Evidence: `data/flight-policy-validation.json`
(`node scripts/flight_policy/evaluate.js`).

**Held-out dispersed flights** (seeds 900000-900299, never used in training):

| | Full missions | Reached orbit | Worst touchdown | Worst pad offset |
| --- | --- | --- | --- | --- |
| Neural policy | **297 / 300** | 300 / 300 | 6.24 m/s | 94 km |
| Classical teacher | 300 / 300 | 300 / 300 | 2.05 m/s | 27.3 m |

A full mission means orbit (perigee above 150 km, eccentricity below 0.05),
fairing released, payload deployed, and a touchdown on deployed legs slower than
3 m/s vertically and 1.5 m/s sideways, tilted under 5° and inside the 43 m pad
radius. The network's misses: two touchdowns on the pad that were too hard
(3.7 and 6.2 m/s), one 44 m out, and one low-thrust, strong-wind flight whose
boostback fell short (94 km). Later candidates traded these for more misses
elsewhere and were rejected by the gate.

**Nominal replay compared with Falcon 9 RTLS** (Ax-4, 25 June 2025, public
webcast timeline; booster apogee from CRS-10 webcast reconstructions):

| Event | This replay | Falcon 9 RTLS |
| --- | --- | --- |
| MECO | T+2:16, 60.6 km, 1.80 km/s | T+2:17-2:33, ~60-65 km, ~1.7 km/s |
| Boostback | T+2:36-3:31 | T+2:42-3:28 |
| Booster apogee | 128 km at T+4:16 | ~130 km |
| Entry burn | T+6:10-6:20 (66 → 57 km) | T+6:18-6:30 |
| Landing burn | T+7:24 from 4.2 km | T+7:22 |
| Touchdown | T+7:49 | T+7:39 |
| SECO | T+8:24 | T+8:48 |

Touchdown at 1.95 m/s vertical, 0.02 m/s horizontal, 0.12° tilt, 1.4 m from
the pad centre; insertion 269 × 334 km at 42.9°; payload deploy T+9:24.

Training history: from scratch, round 1 flew 0/200 and reached no orbits;
round 5 found that the teacher's terminal insertion steering whipped the pitch
to its limit in the last seconds (time-to-go collapsing to zero), which the
network could not imitate, so upper-stage labels were regenerated with a
time-to-go floor; round 7 flew 86/200 and round 8 195/200; later rounds flew 197/200 to 300/300
with the round-8 network, and no later candidate beat it on the gate.

## Limits

- The network imitates a classical teacher; it is not optimised beyond it, and
  its reliability is a measured rate on simulated dispersions, not a guarantee.
- Point-mass translational dynamics with first-order attitude response; no
  rigid-body rotation, slosh, structural or thermal loads.
- The dispersion set is a simulation study, not a range-safety analysis.
- Max-Q comes at T+55 s, earlier than the T+1:10 typical of Falcon 9
  webcasts: with the lighter default payload the stack accelerates faster off
  the pad. Moving the throttle bucket earlier collapses the gravity turn in
  this point-mass model, so the bucket stays where it is.
