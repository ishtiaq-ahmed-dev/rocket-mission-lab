# Research and source trail

Researched 19 October 2026. Primary documentation and research papers informed the implementation. No flight certification or official vehicle parameters are implied.

| Source | Applied decision | Important limit |
| --- | --- | --- |
| [MuJoCo simulation programming](https://mujoco.readthedocs.io/en/stable/programming/simulation.html) | One free joint for full rigid-body translation and attitude; external Cartesian force and torque; headless `mj_step` | Mass/inertia edits require recalculating constants; `mj_setConst` overwrites the pose, so live state is preserved |
| [MuJoCo Python bindings](https://mujoco.readthedocs.io/en/stable/python.html) | Native Python wheel, no OpenGL rendering in training | MuJoCo is CPU physics here; GPU policy optimization does not make simulation GPU accelerated |
| [NASA specific impulse](https://www1.grc.nasa.gov/beginners-guide-to-aeronautics/specific-impulse/) | Propellant flow `T/(Isp*g0)` and finite-fuel thrust cap | Constant effective Isp; no chamber or nozzle transient model |
| [NASA ideal rocket equation](https://www1.grc.nasa.gov/beginners-guide-to-aeronautics/ideal-rocket-equation/) | Consistent effective exhaust velocity and mass ratio explanation | Real flight also loses velocity to gravity and drag |
| [Gymnasium custom environments](https://gymnasium.farama.org/tutorials/gymnasium_basics/environment_creation/) | Seeded resets, continuous spaces, distinct terminated/truncated states, environment checker | Observation bounds use infinities for unbounded physical velocities; checker warnings are documented |
| [Stable-Baselines3 PPO](https://stable-baselines3.readthedocs.io/en/master/modules/ppo.html) | Clipped PPO, small MLP, vectorized environments, CPU default | Small state networks can be slower on GPU; verify throughput instead of equating GPU use with speed |
| [Stable-Baselines3 SAC](https://stable-baselines3.readthedocs.io/en/master/modules/sac.html) | Entropy-regularized off-policy candidate, CUDA when available | Evaluation loads a minimal replay buffer; optimizer checkpoints do not imply the replay buffer was preserved |
| [SB3 normalization examples](https://stable-baselines3.readthedocs.io/en/master/guide/examples.html) | Save VecNormalize statistics at every checkpoint, freeze them during evaluation | Loading only network weights changes the observation distribution |
| [PPO paper](https://arxiv.org/abs/1707.06347) | Explain clipped policy objective, advantage and update constraints | Our educational implementation uses SB3; the separate lesson implements REINFORCE |
| [SAC paper](https://arxiv.org/abs/1812.05905) | Explain entropy temperature, stochastic policy and twin critics | A general algorithm's research results are not evidence that this rocket task has converged |
| [CVXPY second-order cone examples](https://www.cvxpy.org/examples/basic/socp.html) | Convex powered-descent approximation with norm bounds and CLARABEL | Constant mass and relaxed lower thrust; it is not a proof of lossless convexification |
| [NASA time-varying mass guidance research](https://ntrs.nasa.gov/citations/20230018515) | Identify the gap between this approximation and research-grade 6-DOF optimization | This project does not implement full successive convexification or certification |
| [React Three Fiber introduction](https://r3f.docs.pmnd.rs/getting-started/introduction) | Browser-only rendering, imperative frame interpolation and procedural meshes | Browser rendering does not feed camera observations to the RL policy |
| [PyTorch local installation](https://pytorch.org/get-started/locally/) | Verify installed CUDA architecture and execute a GPU operation | Installed build is recorded exactly in `data/runtime.json`; this machine's nightly wheel is not a portable lockfile |
| [Three.js responsive rendering](https://threejs.org/manual/pages/responsive.html) | Separate CSS size, drawing-buffer pixels and camera aspect; report measured live resolution | A smaller viewport may supersample but its physical monitor does not become a 4K display |
| [Three.js texture sampling](https://threejs.org/docs/pages/Texture.html) | Mipmapped filtering and up to 16× supported anisotropy for grazing ground angles | More samples cost GPU work; normal/roughness maps must not be treated as sRGB color |
| [Three.js shadow mapping](https://threejs.org/manual/pages/shadows.html) | Bound shadow frustum, use bias and high-resolution maps; separate road/pad surfaces | Large shadow textures or triangle counts alone do not remove acne or depth fighting |
| [Three.js material polygon offset](https://threejs.org/docs/pages/Material.html) | Offset asphalt/pad drawing depth in addition to actual surface height separation | Offset is a rendering aid, not a physical-contact correction |
| [Three.js color management](https://threejs.org/manual/pages/color-management.html) | Linear lighting with sRGB output and ACES tone mapping | Correct color pipeline does not establish photorealism |
| [OrbitControls](https://threejs.org/docs/pages/OrbitControls.html) | Live rotation, zoom, pan and damping while recorded playback continues | Follow logic must preserve the control target and user-relative camera offset |
| [Web Audio practices](https://developer.mozilla.org/en-US/docs/Web/API/Web_Audio_API/Best_practices) | Explicit user-click audio activation and page/playback lifecycle controls | Browser autoplay policy and actual speaker output still need user checks |
| [Rocky Terrain 02](https://polyhaven.com/a/rocky_terrain_02), [CC0 license](https://polyhaven.com/license) | Bundle 2K/4K color/normal/roughness maps; use the documented 90 m terrain tile scale | The texture is a scan, while this scene's geographic layout is illustrative |

## What the research changed

We preserve state around MuJoCo mass updates, save normalization with every policy, keep MLP PPO on CPU by default, and separate train-time curriculum seeds, development evaluation seeds, and qualification seeds. A convex guidance plan is a useful baseline, but actuator dynamics and minimum thrust can invalidate its ideal trajectory. The final controller therefore uses an LQR lateral/attitude regulator and a differentiable descent-speed reference with feedforward.

## Evidence policy

Numbers come from saved simulation records or evaluation CSV files. A curve with zero successes remains a failed/learning curve. Four replay slots never establish four distinct levels of competence. Full qualification means an actual completed 10,000-seed batch, not the default value of a command-line argument.
