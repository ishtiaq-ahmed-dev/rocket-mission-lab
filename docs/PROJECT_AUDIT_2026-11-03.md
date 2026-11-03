# Project audit — 3 November 2026

Scope: browser mission physics, neural policy runtime and evaluation, replay
visuals/controls, Python environments/training/API, build and GitHub delivery.
The browser Falcon 9 study and the Python subscale RL lab remain distinct.

## Plan and acceptance

1. Establish the baseline: Python suite, shipped-flight invariants, standards,
   production build, and browser inspection.
2. Repair demonstrated numerical, model-contract, rendering and input failures;
   add regressions that exercise the failure rather than duplicate the code.
3. Re-evaluate the shipped policy on dispersed missions after physics changes.
   Preserve measured failures and model limits; never substitute a successful
   trajectory or silently replace a failed policy.
4. Verify desktop/mobile layout, camera framing, seeking, keyboard/modal input,
   playback timing, API and training compatibility, and production assets.
5. Record commands/results and remaining research limits, review the final diff,
   commit the project changes and push to the existing GitHub remote.

## Baseline

- `node scripts/check_flight.js`: passed 16,751 frames and interpolation.
- `node scripts/check_standards.js`: passed 57 anchors.
- `npm run build` in `frontend`: passed.
- Initial Python suite: 130 passed and one MuJoCo allocation failure; the
  failing case passed in isolation. The restricted Windows sandbox stalls
  networking, so complete suites run outside that sandbox.
- Browser: reproduced a cropped launch stack, overlapping event labels, and
  low-contrast text over the bright sky/ground. Source review also found a
  clamped playback clock, modal/keyboard conflicts and missing narrow layouts.
- Physics review: separation advances the new upper stage twice in its birth
  interval; fairing bodies have the same timing error; contact reports retain
  the end-of-step rather than the contact-time velocity.

## Repairs

- Physics: new upper stages, fairings and payloads are recorded at release
  time and integrated once per interval; fairing mass closes to the parent
  mass and its separation recoil conserves momentum. Fuel exhaustion caps
  the final interval's impulse. Contact-time velocity, attitude and fuel are
  retained; a successful landing requires deployed legs. Failed impacts do
  not level the booster into a successful-looking landing.
- Visuals and input: full-stack camera framing, contrast behind HUD labels,
  narrow-screen/short-screen layout, collision-aware timeline labels,
  keyboard-accessible event buttons and time slider, modal focus and playback
  restoration, pointer cancellation and wall-time playback through slow frames.
- Neural/runtime: reject invalid network dimensions, normalization, activation
  and nonfinite weights before flight. Validate evaluation arguments and worker
  results, handle worker errors, and bound default worker concurrency.
- Training: map dataset files and load only shuffled minibatches, validate
  labels, normalize in bounded chunks, export atomically, resume the actual
  incumbent weights, and compare candidates before promotion. The gate uses
  nominal + 256 development seeds and rejects worse speed/offset envelopes.
  Candidates and checkpoints remain local until accepted.
- Python RL: reject all nonfinite actions before clipping or changing RCS;
  preserve pre-contact foot speed in both terminal reward and reported metrics.
  MuJoCo's free-body arena is explicitly 256 KiB rather than the inferred
  13 MiB per environment; measured arena use has ample headroom. See the
  [MuJoCo memory parameter](https://mujoco.readthedocs.io/en/stable/XMLreference.html#size-memory).
- Native controls: share the pressure/Isp engine model with guidance, scale
  both pressure-model thrust anchors during engine identification, reapply
  gravity after reset, permit light-booster terminal cutoff, clear stale
  pulse-off decisions during continuous burns, use a gentler descent and
  bounded roll damping, use exact feedback for perfect-sensor runs while
  retaining navigation filtering for noisy sensors, and avoid wasting fuel on
  high-altitude emergency retarget holds. Default integration is 240 Hz after a 120/240 Hz comparison
  exposed excessive roll growth at the lower rate. Lower explicitly selected
  rates remain experimental and are not covered by the default-flight pass.
- Native validation: configurable API endpoint/output directory, real vacuum
  conditions in momentum tests (Mach-dependent drag was still active before),
  and roll/fuel/contact-speed telemetry in flight traces.

## Verification

- Nominal browser mission: 16,751 recorded frames plus 60 Hz interpolation;
  57 standards anchors; production build and eleven Node regression tests pass.
- `python scripts/check.py`: **169 Python tests**, 57 standards anchors, flight
  invariants and interpolation, **11 Node regressions**, and the production
  build pass together. `scripts/bootstrap.py` also regenerates all twelve
  reference runs; level-4 landing, takeoff and combined missions succeed.
- Native default 240 Hz matrix: **4/4** complete missions (seeds 42–45,
  alternating nominal and mid-flight retargeted), all stable after four seconds
  of settling with the engine off. Contact speed is 1.0035 m/s nominal and
  0.5912 m/s retargeted; first-contact pad errors are 0.8008 m and 0.7030 m.
  The matched-source final record is
  [native-four-flight-regression.json](evidence/2026-11-03/native-four-flight-regression.json).
  Earlier failed attempts are retained as negative evidence; they are not the
  final implementation's qualification record.
- Final CUDA/PhysX diagnostic: passed at 240 Hz, including free fall, pusher
  linear/angular momentum, hold-down release, RCS impulse/gas and API telemetry.
  [Diagnostic](evidence/2026-11-03/native-diagnostic.json).
- Live HTTP controls: pause freezes the clock; single-step advances exactly
  0.1 physical seconds; manual, guidance, retarget, resume, pause and stop all
  acknowledged by the real native process.
  [Command test](evidence/2026-11-03/isaac-control-test.json).
- Current-source policy/teacher comparison: **298/300** and **295/300** full
  missions; all 300 in both sets reach orbit, release fairings and deploy.
  The incumbent's two failures remain soft landings outside the 43 m pad.
  Source and model hashes are in `data/flight-policy-validation.json`.
- A six-epoch booster-only candidate trained on 8,656,483 existing rows
  completed **299/300**, but its worst miss grew to 149.3 m and impact speed
  to 3.08 m/s. It was **not promoted**. Its old 64-seed count-only development
  comparison and the rejection rationale are retained in
  [policy-comparison.json](evidence/2026-11-03/policy-comparison.json).
- Browser inspection at 1280×720 and 390×844 verified launch framing, readable
  labels, responsive controls and seeking; the checked page logged no browser
  warnings/errors. A later production-tab pass was blocked by automatic approval
  review because its review service reported a usage limit. No browser workaround
  or claim of a completed final visual pass is made.
- `npm audit --json`: zero known advisories. The local Python environment
  inherits system packages; `pip check` reports unrelated global-package
  conflicts, which this project does not change.
- The final browser/model hashes and every source file in the native regression
  manifest were compared with the working tree and match. Compact results:
  [validation-summary.json](evidence/2026-11-03/validation-summary.json).
- The first GitHub run exposed deprecated action runtime warnings. The workflow
  now uses the official supported releases:
  [checkout v7.0.1](https://github.com/actions/checkout/releases/tag/v7.0.1),
  [setup-node v7.1.0](https://github.com/actions/setup-node/releases/tag/v7.1.0)
  and [setup-python v7.1.0](https://github.com/actions/setup-python/releases/tag/v7.1.0).

## Limits

This is a bounded engineering audit, not proof that every possible defect is
absent. The browser remains a point-mass/first-order-attitude simulation and
the Python and native subscale vehicles remain separate experiments. Archived
RL checkpoints do not become qualified on changed dynamics. The two dispersed
policy pad misses and lower-rate native integration limitations remain visible.
No real-vehicle, arbitrary-weather, arbitrary-retarget or model-reliability
certification is claimed.
