# Flight fidelity revision — 21 October 2026

The requested outcome is a polished, evidence-backed mission laboratory with physically consistent launch, staging, descent, touchdown and movable targets. Existing uncommitted work belongs to the preceding agent and is preserved.

## Ordered implementation and acceptance

1. Align nozzle, flame and smoke with the integrated thrust axis. Remove renderer lag and wall-clock actuator smoothing. Test arbitrary attitudes and both gimbal axes, including paused playback and scrubbing.
2. Give launch and landing sites correct markings. Keep pad geometry fixed in world space, remove overlapping coplanar markings and fix target history during retarget playback.
3. Record hold-down release and require engine shutdown before staging. Animate clamps and service arms from recorded events; launch upright from the support structure.
4. Detect first tilted landing-foot contact and preserve the measured impact state. Tighten landing accuracy separately from concrete-pad size. Improve guidance rather than moving a vehicle after touchdown.
5. Preserve flight history across repeated mid-air target commands. Re-observe the new target before learned-policy inference. Show current error and actual terminal tolerance.
6. Build and visually verify the light, rounded dashboard inspired by the supplied reference. Retain charts, mission controls, playback, audio, training and failure evidence. Check narrow and wide screens.
7. Run analytical physics regressions, mission/retarget seed pilots, frontend checks and live API checks. Record source/config identities and counts.
8. Start a new, bounded training study only after the physics/controller corrections pass. Archive the failed v18 campaign; never resume its optimizer against changed dynamics or call a development sample qualified.

## Research and model boundaries

NASA's [rocket control explanation](https://www1.grc.nasa.gov/beginners-guide-to-aeronautics/rocket-control/) describes thrust-vector control and torque around the center of gravity. Its [flight sequence](https://www.nasa.gov/wp-content/uploads/2020/08/falcon9_launch_and_landing.pdf) distinguishes ascent, cutoff, separation, recovery and landing burns. The [PACE staging account](https://science.nasa.gov/blogs/pace/2024/02/08/coming-up-falcon-9-max-q-main-engine-cutoff-and-stage-separation/) confirms cutoff precedes separation.

The current vehicle is a generic single-engine, low-altitude research booster with approximate parameters. A 400 m demonstration cannot establish a hundreds-of-kilometers launch. Extending to that regime requires a separately identified vehicle/mission, altitude-dependent gravity and atmosphere, high-speed aerodynamics/heating, propellant/engine modes, coast attitude control, independently integrated stages and new qualification. Photorealistic rendering and a larger training budget cannot supply those missing models. These remain explicit research gates until implemented and measured.

No universal claim of perfect landing, arbitrary divert reachability, real-vehicle validity or international certification follows from local tests. Failed commands and flights must remain visible.


## Implemented revision

The implementation packages and automated checks were completed in this run; see [executed evidence and remaining qualification boundaries](24-flight-fidelity-validation.md). The final visual portion of package 6 remains unverified because browser control was disabled in Work settings. A separate 100 km suborbital study now includes inverse-square gravity, layered atmosphere, a spherical rendering horizon and independent unpowered-stage integration. It does not supply the remaining thermal, structural, orbital, RCS or compliant-contact models. Long RL training remains an experiment until its own held-out gates pass.
