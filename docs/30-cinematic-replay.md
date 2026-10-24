# Cinematic Replay Pipeline & Visual Upgrade

**Date:** 24 October 2026
**Scope:** Isaac Sim visual mode — offline film renderer, live viewport smoothness, terrain/atmosphere upgrade

---

## 1. Problem

The previous recording path had three verified defects:

1. **Broken output.** The native video encoder wrote a 0-byte MP4 on the full
   flight (`data/isaac/flight-report-flight.mp4`) and the surviving smoke-test
   MP4 (`data/isaac/record-smoke-flight.mp4`) had damaged container timing.
2. **Unusable real-time factor while recording.** The same smoke test ran at
   RTF 0.136 (7× slower than real time) because every frame was rendered
   twice (viewport + record product) and encoded on the CPU inside the
   physics loop.
3. **Prototype look.** 1280×720@30, 1.1 Mbps starved bitrate, flat ground
   cylinder, cone "hills", soap-bubble steam, no ocean/horizon, lollipop
   trees. The dashboard mission video was 1080p25 at 1.1 Mbps.

## 2. Architecture: two-pass cinematic replay

Pass 1 and pass 2 are decoupled, so neither compromises the other:

- **Pass 1 — live flight.** Physics runs at full real-time speed with zero
  recording overhead. A `FlightTrack` (`rocket_lab/isaac/cinematic.py`)
  hook, called from `IsaacRocketPhysics.step` every physical substep
  (120 Hz), samples booster pose/quaternion/velocity/omega, throttle,
  gimbal, wind and the upper-stage pose. Capture cost is negligible; the
  live RTF returned to ~1.0 (previously 0.136 while recording).

- **Pass 2 — offline film.** After touchdown the track is replayed
  frame-exactly at the output frame rate. `PlaybackPhysics` feeds the same
  `NativeVisuals.update` used live (plume, steam, legs, grid fins, lights
  all animate identically), a `CameraDirector` executes a nine-shot
  launch-coverage plan (establishing wide → ignition close-up with tilt-up →
  tower rise → 170 mm ascent telephoto → separation → descent chase → 85 mm
  landing approach → touchdown → beauty orbit) with event timings mined from
  the track itself (ignition, separation, landing burn, touchdown), and an
  `OfflineRenderer` renders every frame once through a dedicated
  `/World/CinematicCamera` render product into an **ffmpeg NVENC pipe**
  (H.264, CQ 19, `+faststart`). No wall clock is involved: frame pacing,
  motion smoothness and bitrate are exactly what the GPU affords per frame.

Key implementation facts, each verified by a probe in this session:

| Fact | Value | Probe |
| --- | --- | --- |
| 1080p render + RGB readback | ~160 ms/frame | `scripts/probe_cinematic_pipeline.py` |
| 2160p render + RGB readback | ~470 ms/frame | same |
| NVENC H.264 round-trip | exit 0, frames written = frames in container, duration exact | `scripts/probe_camera_control.py` |
| Viewport camera prim is unusable for offline render | `/OmniverseKit_Persp` transform is overwritten by the viewport each frame | same |
| Dedicated camera prim works | content variance + parallax across focal lengths | same |
| RTX height fog (`/rtx/fog/*`) fogs the sky dome | washes the HDRI to flat gray — left OFF | `data/probes/aa`, smoke renders |
| scipy `Rotation.slerp` unavailable in Isaac's build | 120 Hz keyframes → normalized linear interpolation is visually identical | smoke run |

## 3. Visual upgrades (`rocket_lab/isaac/visuals.py`)

- **Terrain**: three displaced annulus meshes (inner grass 60–2400 m, midland
  2400–6200 m, dry outland 6200–10500 m) with dead-flat blending around the
  pads and low-frequency noise relief; two noise-profiled ridge lines past
  the plain (near green-gray, far blue-shifted for aerial perspective); an
  ocean disc to the world edge beyond the ridges.
- **Vegetation**: layered three-tier fir prototype, proportioned broadleaf,
  ground scrub instancer (2 600 instances), corridor-dense tree scattering
  (1 500 instances) — all single-draw `PointInstancer`s.
- **Deluge steam**: fourteen strongly flattened ground-hugging ellipsoids
  (never overhead spheres, which read as soap bubbles), opacity 0.10,
  visible only under 12 m AGL during a burn.
- **Lighting discipline**: plume light 26 000 units at radius 3.5 (the
  previous 52 000 blew out nearby steam and the skirt), ground blast glow
  thrust-squared and limited to the last 6 m AGL, plume emission unchanged.
- **Animation timing**: all eased quantities (landing legs, grid fins,
  camera blends) are now exponential in *real seconds* measured between
  visuals updates, so 60 Hz live view and offline replay animate identically.
- **Live viewport**: render gate raised 30 → 60 Hz (`physics.py`).

## 4. Runner interface

```
scripts/run_isaac.ps1 [--cinematic] [--cine-fps 60] [--cine-preset balanced|cinematic|pathtraced]
                      [--cine-size 720|1080] [--cine-output videos/...] [--track-out data/...npz]
```

`--cinematic` records the pose track during the flight, then renders the
film offline. `--track-out` persists the 120 Hz track for re-renders without
re-flying (`FlightTrack.load`). The dashboard API now reports the real video
duration instead of a hardcoded 57.6 s.

## 5. Camera authoring findings (probes in `scripts/probe_*.py`)

The offline camera went through three verified stages:

1. Authored `xformOp:translate` + `xformOp:rotateXYZ` on a dedicated
   `/World/CinematicCamera`: positions applied exactly, but scipy's
   lowercase `'xyz'` euler convention is EXTRINSIC while USD `rotateXYZ`
   is INTRINSIC X→Y→Z — every shot silently aimed wrong (verified by
   instrumented pos_err=0.000 m / view_err up to 177° logs).
2. `xformOp:orient` quaternion (unambiguous encoding): stopped propagating
   to the render product after the first aim in full-scene sessions.
3. **Viewport-driven `/OmniverseKit_Persp` via `set_camera_view`** — the
   same proven path the live follow camera uses — with per-shot
   `focalLength` on the prim. This is the shipped path; a striped-board
   probe (`scripts/probe_quat_render.py`) proves face-on framing.

## 6. Verification (measured)

- Headless physics diagnostic (`data/isaac/diagnostic-regression.json`):
  **passed** — analytic free fall, hold-down release, separation pusher
  momentum conservation, RCS impulse, telemetry socket, dashboard bridge.
- Python suites: 89 tests + 10 Isaac contract tests pass.
- Full mission (240 s budget, 1080p60, cinematic preset): the classical
  guidance landed 0.0547 m from pad center at 0.0066 m/s, 0.0° tilt; live
  real-time factor 1.0 with the adaptive render gate (was 0.59 at a fixed
  60 Hz gate and 0.136 with the old inline recorder).
- Film: 5 605 frames, 1920×1080@60, 93.42 s, frame-exact container,
  ~258 ms/frame offline, 24 min wall render. Served by the dashboard at
  `/api/native/video`; the API now reports the real duration.
- Frames: `docs/evidence/2026-10-24/isaac-cine-*.png`; summary:
  `docs/evidence/2026-10-24/isaac-cinematic.json`.

Known cosmetic follow-ups: the landing-pad sign reads mirrored from some
beauty-orbit azimuths, and the demo mission carries 24 t propellant
(documented above) because the stock load runs dry ~2 m above the pad on
the classical descent.
