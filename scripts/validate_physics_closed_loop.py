"""Compare saved pre-optimization dynamics against live dynamics in feedback.

This is numerical regression evidence, not a new reliability qualification.
Both controllers see independently simulated observations and calculate their
own actions, exposing amplification through feedback and noisy measurements.
"""
from pathlib import Path
from collections import Counter
import hashlib
import sys
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rocket_lab.config import DATA, ROOT, load_config
from rocket_lab.controllers import ClassicalController
from rocket_lab.envs import RocketEnv
from rocket_lab.physics import RocketPhysics
from rocket_lab.simulation import LearnedPolicy
from rocket_lab.storage import atomic_json


def run():
    reference_text=(DATA/'performance'/'physics-reference.txt').read_text(encoding='utf-8')
    namespace={'__name__':'rocket_lab._reference_closed_loop','__package__':'rocket_lab'}
    exec(compile(reference_text,'<saved-physics-reference>','exec'),namespace)
    reference=namespace['RocketPhysics']
    live_text=(ROOT/'rocket_lab'/'physics.py').read_text(encoding='utf-8')
    cfg=load_config()
    rows=[]
    cases=[('landing',None),('takeoff',None),
           ('landing','landing-ppo-pad-v10-pilot__step-006905328'),
           ('takeoff','takeoff-ppo-horizon-v13-continued__step-002011136')]
    keys=('position','velocity','quaternion','angular_velocity','fuel_mass','wind','tilt')
    for mission,checkpoint in cases:
        envs=[RocketEnv(mission,config=cfg),RocketEnv(mission,config=cfg)]
        envs[0].physics=reference(cfg)
        policies=[LearnedPolicy(checkpoint,observation_config=cfg) for _ in envs] if checkpoint else None
        max_error={key:0. for key in (*keys,'action','reward')}
        episodes=[]
        for seed in range(24000,24016):
            observations=[env.reset(seed=seed)[0] for env in envs]
            controllers=[ClassicalController(4) for _ in envs]
            steps=0
            while True:
                actions=[policies[i].action(observations[i]) if policies else controllers[i].action(envs[i]) for i in range(2)]
                max_error['action']=max(max_error['action'],float(np.max(np.abs(actions[0]-actions[1]))))
                results=[env.step(action) for env,action in zip(envs,actions)]
                observations=[result[0] for result in results]
                max_error['reward']=max(max_error['reward'],abs(results[0][1]-results[1][1]))
                for key in keys:
                    a,b=[env.last_state[key] for env in envs]
                    error=float(np.max(np.abs(np.asarray(a)-np.asarray(b))))
                    max_error[key]=max(max_error[key],error)
                    np.testing.assert_allclose(a,b,atol=1e-5,rtol=0,err_msg=f'{mission} seed {seed} {key}')
                done=[result[2] or result[3] for result in results]
                assert done[0]==done[1], (mission,seed,'termination step changed')
                steps+=1
                if done[0]:
                    assert results[0][4]['outcome']==results[1][4]['outcome'], (mission,seed,'outcome changed')
                    episodes.append(dict(seed=seed,steps=steps,outcome=results[0][4]['outcome']))
                    break
        for env in envs:env.close()
        rows.append(dict(mission=mission,method='rl' if checkpoint else 'classical',checkpoint_id=checkpoint,
                         episodes=episodes,outcomes=dict(Counter(row['outcome'] for row in episodes)),maximum_absolute_differences=max_error))
        print(f'CHECKED {mission} {checkpoint or "classical L4"}: 16 matching outcomes/termination steps',flush=True)
    report=dict(scope='64 full-difficulty closed-loop regression episodes, fixed seeds 24000-24015; numerical equivalence, not reliability qualification',
                reference_sha256=hashlib.sha256(reference_text.encode()).hexdigest(),live_sha256=hashlib.sha256(live_text.encode()).hexdigest(),
                tolerance=1e-5,all_outcomes_and_termination_steps_equal=True,cases=rows)
    atomic_json(DATA/'physics-closed-loop-validation.json',report)
    print('Saved data/physics-closed-loop-validation.json',flush=True)


if __name__=='__main__':run()
