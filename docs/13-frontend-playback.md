# Browser rendering and playback

## What it does

React renders the dashboard, React Three Fiber renders the procedural world, Zustand shares the playback clock, and Recharts plots actual telemetry. Rendering never advances backend physics. The replay starts from a recorded state and interpolates between adjacent frames.

## Why this approach

Separating rendering from training permits a headless Windows/Linux worker and a Mac browser. The rocket, pad, coastline, structures, grid fins, legs and exhaust are procedural geometry. The sky/HDR, terrain PBR maps and scanned coastal rocks are locally bundled CC0 Poly Haven assets; attribution is in `frontend/public/assets/ATTRIBUTION.md`. Curved grass blades use actual geometry. A visual ship option shares the static pad physics.

High is the default, with a 2 m near grid and 4 m coastal grid. Ultra uses 1 m / 2 m and 4K uses 0.5 m / 1 m. Resolution collars contain both boundary vertex sets, avoiding cracks between fine and distant grids. Matching world-space UVs and height-derived normals avoid texture and lighting seams. Roads and foundations stay level, while unpaved areas have fine relief. Terrain remains visual and does not replace the simulator's contact plane.

All camera presets permit live rotation, zoom and pan. Rotate/Pan chooses the left-drag operation; Follow is a separate toggle. Following translates the camera and orbit target by the same displacement, preserving user gestures. Screen-space pan and cursor zoom remain active after zooming, and resize preserves the user's framing. The camera stays above the terrain. Flown trail reveals only the recorded history; the default is Off. Sound is synthesized from recorded throttle and wind using Web Audio, enabled by an explicit speaker click, and muted/paused with playback and page visibility.

The canvas renders on demand. Playback requests frames at the chosen 30/60/120/144 Hz limit, with a 60 Hz default; pausing stops the playback scheduler. Camera gestures can still request frames. The clock uses elapsed time rather than assuming the monitor's refresh rate. Rocks use instanced distance LODs, grass has bounded detail and no shadow pass, grid-fin bars share merged geometry, and water uses environment/normal-map reflection without a second scene render.

## Key formulas

```text
alpha = (playback_time - t0)/(t1-t0)
position = p0 + alpha*(p1-p0)
quaternion = slerp(q0,q1,alpha)
R_three = C * R_physics * inverse(C), C = rotation_x(-pi/2)
follow_camera_next = follow_camera + (rocket_next - rocket_previous)
follow_target_next = follow_target + (rocket_next - rocket_previous)
4K still = 3840 x 2160 pixels, cloned camera aspect = 16/9
```

## Five interview questions

1. **Why slerp orientation?** Linear quaternion interpolation can distort angular motion and must handle sign equivalence. Three.js slerp follows the short rotation and preserves normalization.
2. **Does the display determine the physics?** No. All telemetry is produced by MuJoCo. Playback speed changes the viewing clock only.
3. **How does offline mode work?** Bundled JSON contains real exported classical landing episodes, with their actual failures. Training and other missions require the backend.
4. **Is the exhaust physical?** Flame and smoke are visual cues scaled by recorded throttle; they are not fluid simulation or additional forces.
5. **Is 60 fps guaranteed?** No. Recording view removes dashboard chrome; actual browser/GPU refresh performance has not been qualified. Browser observation was policy-blocked in this session.

The graphics menu offers Balanced, High, Ultra and 4K. High uses a 1.25 DPR cap, 2048 shadow maps and actual 4096×4096 ground textures. 4K fits a supersampled live buffer toward UHD bounds; CSS aspect ratio, viewport size and a DPR cap determine the exact live pixel count. Measured buffer dimensions and rolling active FPS are displayed; the paused label is IDLE. The separate 4K download temporarily renders an exact 3840×2160 scene-only PNG; HTML HUD panels are excluded. Smaller monitors can export this image but cannot physically display every pixel at once. Still capture is not MP4 export, and pixel count alone is not photorealism.

## Validation

The 30 frontend unit tests, TypeScript, lint and production build passed. They cover camera composition/following, actual OrbitControls on an isolated event surface, audio control behavior, terrain winding/common edges, physical coordinate conversion, frame scheduling and telemetry. High terrain has 282,712 triangles and about 9.8 MB of geometry buffers, compared with the superseded default's 2,943,464 triangles and 100.6 MB. These are source/CPU budgets, not browser GPU timings.

Local 4K assets have verified 4096×4096 dimensions and earlier production HTTP 200 responses. The user manually confirmed live rotation before the latest changes. A startup error now exposes its actual message and a retry button; browser host callbacks use explicit wrappers. Recovery after this fix, latest ground appearance, sound quality, captured PNG appearance and sustained FPS need browser review. Supplied Playwright tests remain unexecuted after the tool security block. Browser hardware-acceleration settings were not changed or verified.
