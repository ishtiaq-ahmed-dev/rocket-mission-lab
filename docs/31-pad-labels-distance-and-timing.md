# Pad labels, separation and physical timing

28 October 2026. This revision preserves the newer flight deck and fixes inconsistencies across its rendered pads, public mission requests and native guidance.

## Sites and markings

The default browser flight deck paints `TAKEOFF` on the launch circle and `LANDING` on the recovery circle. The lettering is a texture fixed to each site's geometry, with separate materials; camera or rocket motion does not rotate or resize it. The React scene retains the corresponding takeoff/landing stencils. Native USD pads now also have painted surface lettering alongside their existing rim signs.

The nominal sites are [0, 0] and [1200, 400] in local meters, a surface distance of 1,264.911 m. Default separation altitude is 600 m. Public simulation, explicit training/campaign plans and native-start requests reject distances **less than or equal to 1,000 m**. Scheduled simulation retargets and connected native retarget commands apply the same rule. Native telemetry includes the launch coordinates; the radar uses the applied coordinates rather than a hard-coded [1050, 250] target. Its site frame stays fixed as the rocket moves.

Short-distance archived runs and direct internal physics tests remain readable and executable. This is compatibility with historical research evidence, not permission for a new short-range operational request. Coordinate validity and pad spacing do not guarantee that a target is physically reachable.

## Physical time and event labels

At the default 1× setting, playback advances with elapsed monotonic browser time, independently of the rendering rate. Pausing freezes the recorded clock. Hiding the flight-deck tab pauses playback; returning does not skip the hidden interval. Starting a new deck flight restores 1×. Optional accelerated/slow playback remains explicitly selectable; the React transport badge now shows the selected rate or `PAUSED` instead of always claiming 1:1.

The phase timeline uses recorded hold-down release, zero-throttle cutoff, payload separation, relight and physical ground contact. It no longer adds 0.6 s to separation or identifies initial launch-pad contact as touchdown. The duration panel distinguishes ascent from release to separation, recovery from separation to contact, and total recorded duration. Recovery includes coast, lateral transfer and powered descent. Scrubbing to the end selects the actual final frame even when contact time falls between slider increments.

Visual native sessions are paced at their configured time scale; headless runs integrate as fast as the computer allows. Fixed physical timesteps and recorded simulation seconds remain unchanged by that pacing. Hardware load can reduce native real-time performance; a faster headless computation does not shorten the physical mission.

These timings describe the generic model. They are not measured launch-vehicle schedules, orbital flight qualification or certification.

## Native landing fixes

The previous native 1.265 km flight exhausted its fuel after overshooting. Its 45 m/s cruise demand was inconsistent with the native acceleration governor. Native guidance now requests a 25 m/s cruise, a 1 m/s² braking profile and a bounded 400 m transfer shelf. Vehicle thrust and fuel capacity were not increased.

A second problem used the launch stand's 3 m height as the remote landing height. Native descent now references body height at ground-level foot contact, while ascent keeps its separate stand reference. The policy goal uses that same landing contact height. No vehicle pose is snapped or teleported to satisfy the target.

## Evidence and limits

Reports are in [the 28 October evidence directory](evidence/2026-10-28/). Failed exploratory flights are retained alongside successful reruns. Native reports record source manifests and whether files changed during execution.

- The first native long-range run and the cruise-only fix exhausted their fuel; their reports are preserved with `before-guidance` and `before-height-fix` suffixes.
- After both fixes, four deterministic native regression episodes passed, including two target changes. First-contact position error was at most 0.327 m; the four-second settling checks passed with the engine off. This small fixed-configuration regression is not a randomized reliability study.
- The nominal native mission took 122.208 s including four seconds of settling; retargeted episodes took 139.717 s. The MuJoCo combined demonstration took 105.485 s, with 32.740 s ascent and 72.285 s recovery. Different engines/models/controllers are reported separately.
- The browser clock advanced 18.480 physical seconds over 18.4735 measured wall seconds at 1× (the displayed clock is rounded to 0.01 s). Screenshots show both distinct labels and the final `BOOSTER TOUCHDOWN` event.
- The native diagnostic passed gravity, engine, hold-down, separation, RCS impulse and live telemetry checks. The HTTP control test passed pause, resume, manual control, retarget, stop and exactly 0.1 s single-step. No CUDA/memory error appeared in these run logs.
- The complete suite passed 112 Python tests and 49 frontend tests; frontend lint and the production build passed. Native ground lettering was authored in USD; the browser circle lettering was visually reviewed. Headless diagnostics do not qualify native photorealism.

The 1,500 m MuJoCo exploratory plan also exhausted fuel with this generic reserve. The 600 m nominal demonstration was selected from executed cases; other heights and seeds can still fail. There is no automatic promise of success for arbitrary coordinates or more training steps.
