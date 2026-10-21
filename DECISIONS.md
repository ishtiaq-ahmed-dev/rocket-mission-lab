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
| Stitched multiresolution terrain with High default | Uniformly tiny triangles across the full 18 km world | High uses 2 m / 4 m near/coastal grids; 4K offers 0.5 m / 1 m on demand. Coarser distant land bounds memory/draw cost while matching shared edges |
| Road/pad depth separation and polygon offset | Increase every mesh's triangle count | Coplanar depth fighting is a depth-buffer problem; more subdivisions alone do not solve it |
| Correct PBR color spaces and anisotropic filtering | Only increase texture dimensions | Color maps use sRGB, data maps remain linear; sampling at shallow ground angles needs anisotropy, bounded by GPU capability |
| Separate UHD PNG capture from live quality | Permanently render oversized buffers or claim video export | Exact 3840×2160 scene image on demand; restore size before DPR to avoid a transient oversized allocation |
| Gesture-preserving follow camera | Overwrite camera position every frame | Translate camera and target together; cinematic orbit yields to user input and Reset restores the preset |
| Recorded trajectory hidden by default | Present the full line as intended landing guidance | Failed RL paths remain actual failed trajectories; Flown reveals only past telemetry |
| Telemetry-driven local audio | Remote sound recordings | Browser click enables synthesized engine/wind; no third-party runtime asset or autoplay assumption |
| PPO checkpoint continuation | Restart every run or imply exact recovery | Restore network/optimizer, normalization, steps and difficulty under an exact config match; fresh environment/RNG state is documented |
| Demand rendering and bounded playback rate | Unconditional display-refresh rendering | Default 60 Hz playback; idle requests no playback frames. Actual browser frame time still needs measurement |
| Instanced rock LODs and environment water reflection | Detailed rocks at every distance and a second scene reflection pass | Retains close detail while bounding geometry and pass count; latest visual quality remains unverified |
| Separate reward/config experiment with actor-only transfer | Mutate global config or reuse an obsolete critic silently | Preserve baseline identity and learned actor behavior; fresh critic, optimizer and reward statistics have explicit lineage |
| Stage probes beside full-task results | Present curriculum successes as mission qualification | Fixed matched seeds reveal partial competence and regressions without concealing full-task failures |
| Training-only full-start mixture experiment | Wait for easier-stage mastery before ever seeing full-height starts | Tests whether 20% full-height exposure improves burn timing; evaluation distribution and success thresholds stay fixed |
| First-seed stage replays | Select a successful flight for every stage | Match replay outcomes to saved probe rows and expose failures with visible difficulty/seed labels |
| Bounded Gaussian mean experiment | Leave the mean outside actuator bounds with tiny exploration | Tanh centers exploration inside bounds; initial transferred behavior changes and stochastic tails still clip. Results must be measured separately |
| Explicit throttle exploration reset experiment | Change deterministic control behavior to force an earlier burn | Reset sampled throttle std only, preserving deterministic actions and gimbal exploration; record lineage and verify matched initial outcomes |
| Full-difficulty training and longer GAE horizon | Continue easier stages indefinitely | Expose the real reset distribution and strengthen temporal credit; fixed-seed evaluation remains separate |
| Separate pad-accuracy objective | Treat reduced impact speed as complete mission competence | Test stronger physical offset costs alongside an unchanged continuation; retain speed/tilt regressions |
| Training-only ascent-goal curriculum | Require the full 400 m climb at every training stage | Start at 5 m / 3 m/s and widen only after successes; evaluation still uses 400 m / 25 m/s |
| Physical-config-aware frontend selection | Serve the old baseline by default or compare raw rewards across variants | Pass explicit compatible checkpoint IDs, use the largest sample and Wilson lower bound, then landing physical errors; retain clear unqualified labels |
| Larger development samples before retaining a new variant | Treat 6/20 as necessarily better than 5/20 | V12's small-sample apparent improvement reversed at 256 seeds; keep the reversal visible and disclose selection effects |

## Implementation findings

- Analytic tests detected pose reset during `mj_setConst`; the fix preserves pose, velocity and time.
- Cascaded lateral/attitude feedback can oscillate because a gimballed engine initially accelerates opposite the eventual correction. LQR models this four-state chain.
- The landing reference must retain a nonzero touchdown velocity; a square-root profile that approaches zero at zero altitude can hover indefinitely.
- A Windows file reader briefly locked a progress JSON file and stopped a training run. Bounded replacement retry and stale-heartbeat reporting were added.
- A SAC evaluation load allocated its original training replay buffer unnecessarily. Replay inference now overrides it to one transition.
- Physical RAM and Windows virtual-commit headroom are distinct. Launching several Torch jobs caused allocation failures even with physical RAM free. Resource failures are retained and reported.
- FastAPI TestClient stalls in the restricted Windows sandbox's socketpair initialization. The same full backend suite was run outside the sandbox and passed.
- Browser observation was blocked by browser security policy. No visual screenshot or Playwright pass is claimed from that attempt.


## 20 October model and numerical validation decisions

- Retain the intermediate 2,761,136-step ascent policy over the regressed 3,014,656-step final snapshot. The former scored 254/256 in development and 9,836/10,000 in its frozen nominal qualification; the latter scored 207/256 in development.
- Run matched current-source classical and PPO takeoff qualification on the same 10,000 nominal seeds. Keep per-seed journals, immutable candidate hashes and source copies; report stress pilots separately.
- Preserve actor, critic, optimizer moments and normalization when explicitly adapting only learning rate/target KL. A reward change still requires a separate actor-only transfer and a fresh critic/optimizer/reward transform.
- Always save a final snapshot after PPO updates. Retain an earlier same-step callback snapshot under a distinct identifier.
- Use the largest compatible nominal sample and Wilson lower bound for both backend and frontend selection, excluding cross-profile raw reward. The running API still requires its pending restart to import source changes.
- Use native MuJoCo quaternion math and an exact engine-lever expansion only after measured throughput and closed-loop numerical regression checks. The dynamics microbenchmark does not measure renderer GPU usage or end-to-end training speed.
- Test a separate v16 near-ground speed debit after the landing continuations plateaued. Preserve physics, observations and success thresholds; the reward supplies physical penalties, without an expert action or reference trajectory. Initial 20 physical rows match its parent exactly; learning improvement must be measured.


## 21 October 2026 — mission controls and white-plane renderer

- Remove scenery from the active renderer to focus the graphics budget on the rocket. Keep old research assets available; new default graphics quality is Balanced.
- Use charcoal/amber/olive dashboard surfaces, separate draft mission fields from the applied telemetry plan, and keep Run accessible while the setup panel scrolls.
- Use distinct launch and landing phase targets, launch-relative observations, bounded LQR transfer references, a simple sensor estimate, and a gentler terminal descent. Preserve failure outcomes instead of snapping the rocket onto its destination.
- Model generic attached upper-stage mass removal in combined flight and explicitly label the released-stage drawing as an ideal unpowered ballistic preview.
- Bind new run IDs and current result views to source/configuration identity, retaining earlier measurements as historical records.
- Treat 100 million steps as a shared upper budget for measured three-mission training. Keep pure learned policies separate from classical control and require a separate nominal qualification gate.
- A Start-Process worker disappeared during validation. Recover durable checkpoints, account for consumed/lost rollout steps, and use an independent hidden WMI worker on Windows. Real API dispatch and survival across web-server restart were observed; reboot and long unattended qualification remain open.
