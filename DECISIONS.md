# Engineering decisions

| Decision | Alternatives | Reason and tradeoff |
| --- | --- | --- |
| MuJoCo free-body dynamics | Genesis, custom NumPy integrator, MJX | Mature native CPU simulation and Gymnasium integration; GPU physics is not implemented |
| Browser-only R3F rendering | Native MuJoCo renderer | Windows training remains headless; Mac only needs a browser for telemetry playback |
| Generic single-engine 40 m vehicle | Official Falcon 9 model | Avoid unsupported specifications; every physical parameter is approximate and centralized |
| RK4 at 50 Hz, controller at 10 Hz | Faster coarse integration or 1 kHz physics | Manageable local training cost and accurate free-fall baseline; timestep convergence remains a further qualification task |
| Touchdown judged on pre-contact state at COM plane | Full compliant landing-leg collision | Preserves impact speed and explicit failure classification; tilted foot geometry and contact/landing stability are approximate |
| Rate-limited two-axis thrust vectoring | Artificial attitude thrusters | Torque follows the engine lever; no hidden stabilizing torque is given to RL |
| Engine-off command plus minimum on-throttle | Allow impossible continuously low thrust | Enforces actuator limits, but unlimited restart commands omit ignition limits/transients |
| L1 untuned feedback, L2 tuned feedback, L3 convex plan tracking, L4 LQR + descent feedforward | Claim monotonic improvement by naming | Versions are real; evaluation may show regressions and the UI displays them |
| Constant-mass SOCP approximation | Full nonlinear six-DOF successive convexification | Free solver and inspectable implementation; minimum thrust relaxation and attitude lag can cause failure |
| Vertical launch to separation | Orbital ascent or arbitrary downrange gravity turn | User scope excludes orbit. With a target directly above the pad, the gravity-aligned reference stays vertical; no realistic orbital gravity turn is claimed |
| PPO CPU, SAC automatic CUDA | Always use GPU | State MLP PPO is frequently simulation/CPU limited; record actual throughput |
| Four DummyVecEnv instances | SubprocVecEnv on Windows | Avoid costly spawned Torch runtimes on an already memory-constrained machine; vectorized does not mean parallel physics |
| State-only RL, no expert actions | Imitation, controller residuals | Preserves a pure RL comparison; convergence takes genuine training effort |
| Explicit physical reward with terminal-error shaping | Sparse binary success alone | Early pilot reward encouraged fast failures; smoother terminal speed/position penalties improve the learning signal. Old pilot data are retained as exploratory evidence |
| Rolling-success curriculum | Advance every fixed number of steps | Difficulty only rises after measured performance; reward improvement alone is insufficient |
| Fixed-seed evaluation with Wilson interval | Only show best replay | Uncertainty and failure modes remain visible. Development checkpoint evaluation is distinct from 10,000-seed qualification |
| Atomic JSON + Windows retry | SQLite database | Inspectable small local jobs and telemetry; transient reader locks require bounded retry |
| One API-launched training job at a time | Unbounded task launch | Avoid saturating virtual memory and GPU; command-line research runs were separately supervised |
| Procedural rocket plus locally bundled CC0 environment assets | Downloaded official vehicle or remote runtime asset loading | Generic educational vehicle; scanned rocks, PBR terrain and HDR sky improve environmental detail with recorded attribution |
| Ghost overlay comparison | Two separate WebGL canvases | Lower rendering cost, same start seed; clocks align by time, not normalized mission fraction |
| Recorded offline fallback | Invented successful mock flight | Offline playback uses actual exported classical MuJoCo runs |
| Record-friendly fullscreen view | Claim built-in video export | UI hides controls, browser renders at its actual refresh rate; no guaranteed 60 fps or MP4 encoder is implied |
| Stitched multiresolution terrain | Uniformly tiny triangles across the full 18 km world | 0.5 m near grid and 1 m coastal range in Ultra/4K; coarser distant land bounds memory/draw cost while matching shared edges |
| Road/pad depth separation and polygon offset | Increase every mesh's triangle count | Coplanar depth fighting is a depth-buffer problem; more subdivisions alone do not solve it |
| Correct PBR color spaces and anisotropic filtering | Only increase texture dimensions | Color maps use sRGB, data maps remain linear; sampling at shallow ground angles needs anisotropy, bounded by GPU capability |
| Separate UHD PNG capture from live quality | Permanently render oversized buffers or claim video export | Exact 3840×2160 scene image on demand; restore size before DPR to avoid a transient oversized allocation |
| Gesture-preserving follow camera | Overwrite camera position every frame | Translate camera and target together; cinematic orbit yields to user input and Reset restores the preset |
| Recorded trajectory hidden by default | Present the full line as intended landing guidance | Failed RL paths remain actual failed trajectories; Flown reveals only past telemetry |
| Telemetry-driven local audio | Remote sound recordings | Browser click enables synthesized engine/wind; no third-party runtime asset or autoplay assumption |
| PPO checkpoint continuation | Restart every run or imply exact recovery | Restore network/optimizer, normalization, steps and difficulty under an exact config match; fresh environment/RNG state is documented |

## Implementation findings

- Analytic tests detected pose reset during `mj_setConst`; the fix preserves pose, velocity and time.
- Cascaded lateral/attitude feedback can oscillate because a gimballed engine initially accelerates opposite the eventual correction. LQR models this four-state chain.
- The landing reference must retain a nonzero touchdown velocity; a square-root profile that approaches zero at zero altitude can hover indefinitely.
- A Windows file reader briefly locked a progress JSON file and stopped a training run. Bounded replacement retry and stale-heartbeat reporting were added.
- A SAC evaluation load allocated its original training replay buffer unnecessarily. Replay inference now overrides it to one transition.
- Physical RAM and Windows virtual-commit headroom are distinct. Launching several Torch jobs caused allocation failures even with physical RAM free. Resource failures are retained and reported.
- FastAPI TestClient stalls in the restricted Windows sandbox's socketpair initialization. The same full backend suite was run outside the sandbox and passed.
- Browser observation was blocked by browser security policy. No visual screenshot or Playwright pass is claimed from that attempt.
