# Browser rendering and playback

## What it does

React renders the dashboard, React Three Fiber renders the procedural world, Zustand shares the playback clock, and Recharts plots actual telemetry. Rendering never advances backend physics. The replay starts from a recorded state and interpolates between adjacent frames.

## Why this approach

Separating rendering from training permits a headless Windows/Linux worker and a Mac browser. The rocket, pad, coastline, structures, grid fins, legs and exhaust are procedural geometry. The sky/HDR, terrain PBR maps and scanned coastal rocks are locally bundled CC0 Poly Haven assets; attribution is in `frontend/public/assets/ATTRIBUTION.md`. Curved grass blades use actual geometry. A visual ship option shares the static pad physics.

Ultra/4K use a half-meter grid near the lander and a one-meter grid across the 960 m coastal range. Resolution collars contain both boundary vertex sets, avoiding cracks between fine and distant grids. Matching world-space UVs and height-derived normals avoid texture and lighting seams. Roads and foundations stay level, while unpaved areas have fine relief. Terrain remains visual and does not replace the simulator's contact plane.

All camera presets permit live rotation, zoom and pan. Following translates the camera and orbit target by the same displacement, preserving user gestures. The camera stays above the terrain. Flown trail reveals only the recorded history; the default is Off. Sound is synthesized from recorded throttle and wind using Web Audio, enabled by an explicit speaker click, and muted/paused with playback and page visibility.

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

The graphics menu offers Balanced, High, Ultra and 4K. Ultra is the default on this workstation. 4K fits a supersampled live buffer toward UHD bounds; CSS aspect ratio, viewport size and a DPR cap determine the exact live pixel count. Its measured dimensions and rolling FPS are displayed. The separate 4K download temporarily renders an exact 3840×2160 scene-only PNG; HTML HUD panels are excluded. Smaller monitors can export this image but cannot physically display every pixel at once. Still capture is not MP4 export, and pixel count alone is not photorealism.

## Validation

The 19 frontend unit tests, TypeScript, lint and production build passed. They cover camera composition/following, audio control behavior, terrain winding/common edges, quality scaling and telemetry. Local 4K assets have verified 4096×4096 dimensions and HTTP 200 responses. The user manually confirmed live rotation. Latest ground appearance, sound quality, captured PNG appearance and sustained FPS need browser review. Supplied Playwright tests remain unexecuted after the tool security block.
