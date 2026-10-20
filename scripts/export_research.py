from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from rocket_lab.config import DATA
from rocket_lab.storage import atomic_json,read_json
sources=[
 {"title":"MuJoCo simulation programming","url":"https://mujoco.readthedocs.io/en/stable/programming/simulation.html","application":"Free-body integration, Cartesian forces and safe updates to mass constants."},
 {"title":"NASA: specific impulse","url":"https://www1.grc.nasa.gov/beginners-guide-to-aeronautics/specific-impulse/","application":"Thrust, effective exhaust velocity and consistent propellant flow."},
 {"title":"Stable-Baselines3: PPO","url":"https://stable-baselines3.readthedocs.io/en/master/modules/ppo.html","application":"Clipped policy optimization and a CPU default for small state networks."},
 {"title":"Stable-Baselines3: SAC","url":"https://stable-baselines3.readthedocs.io/en/master/modules/sac.html","application":"Entropy regularization, twin critics and off-policy learning."},
 {"title":"SB3: normalization and model persistence","url":"https://stable-baselines3.readthedocs.io/en/master/guide/examples.html","application":"Pair each model with VecNormalize statistics and freeze them during evaluation."},
 {"title":"Gymnasium: custom environment API","url":"https://gymnasium.farama.org/tutorials/gymnasium_basics/environment_creation/","application":"Seeded resets, observations, normalized actions and terminal versus truncated outcomes."},
 {"title":"CVXPY: second-order cone programming","url":"https://www.cvxpy.org/examples/basic/socp.html","application":"An inspectable constant-mass powered-descent approximation."},
 {"title":"NASA: guidance with time-varying mass properties","url":"https://ntrs.nasa.gov/citations/20230018515","application":"Research context and limits of this project's simpler convex planning model."},
 {"title":"React Three Fiber","url":"https://r3f.docs.pmnd.rs/getting-started/introduction","application":"Browser-only rendering of the procedural rocket and physics telemetry."},
 {"title":"PyTorch: local installation","url":"https://pytorch.org/get-started/locally/","application":"Select a compatible CUDA build and verify a real GPU computation."}
]
# Preserve reviewed sources added during later model/rendering investigations.
merged={source['url']:source for source in sources}
merged.update({source['url']:source for source in read_json(DATA/'research.json',[])})
atomic_json(DATA/'research.json',list(merged.values()))
