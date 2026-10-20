"""Measure and label short ascent practice separately from full-task checks."""
import argparse
import time
from collections import Counter
import numpy as np
from .config import DATA,ROOT
from .envs import RocketEnv
from .simulation import LearnedPolicy,simulate
from .probe import publish_probes
from .storage import atomic_json,config_hash

def practice(identifier,episodes=32,start_seed=23000):
    if episodes<1:raise ValueError('episodes must be positive')
    policy=LearnedPolicy(identifier);cfg=policy.trained_config;meta=policy.meta
    if meta['mission']!='takeoff' or not cfg['training'].get('takeoff_goal_curriculum'):
        raise ValueError('Practice probes require a trained ascent-goal curriculum checkpoint')
    policy.input_config=cfg;difficulty=meta['difficulty']
    env=RocketEnv('takeoff',config=cfg,difficulty=difficulty,training=True);rows=[]
    for seed in range(start_seed,start_seed+episodes):
        obs,_=env.reset(seed=seed)
        while True:
            obs,_,terminated,truncated,info=env.step(policy.action(obs))
            if terminated or truncated:break
        rows.append(dict(seed=seed,**info))
    stage=dict(difficulty=difficulty,episodes=episodes,seeds=[start_seed,start_seed+episodes-1],
               successes=sum(row['outcome']=='success' for row in rows),
               failures=dict(Counter(row['outcome'] for row in rows if row['outcome']!='success')),
               mean_speed=float(np.mean([row['touchdown_speed'] for row in rows])),
               mean_tilt=float(np.mean([row['tilt'] for row in rows])),
               mean_offset=float(np.mean([row['pad_distance'] for row in rows])),
               target_altitude=env.takeoff_altitude,target_velocity=env.takeoff_velocity,rows=rows)
    replay=simulate('takeoff','rl',4,start_seed,identifier,save=False,config=cfg,difficulty=difficulty,training=True)
    assert replay.run.outcome==rows[0]['outcome']
    np.testing.assert_allclose([replay.run.touchdown_speed,replay.run.tilt,replay.run.pad_distance],
                              [rows[0]['touchdown_speed'],rows[0]['tilt'],rows[0]['pad_distance']],atol=1e-6,rtol=0)
    replay.run.source='MuJoCo development replay; training-only short ascent goal, first fixed seed'
    filename=f'{identifier}-practice-s{start_seed}.json'
    for folder in (ROOT/'frontend'/'public',ROOT/'frontend'/'dist'):
        if folder.exists():atomic_json(folder/'model-replays'/filename,replay.model_dump())
    stage.update(replay_url=f'/model-replays/{filename}',replay_seed=start_seed,replay_outcome=replay.run.outcome)
    result=dict(checkpoint_id=identifier,mission='takeoff',steps=meta['steps'],config_hash=config_hash(cfg),
                training_config_hash=meta['config_hash'],created_at=time.time(),practice=True,
                scope='short ascent training-stage practice; not full 400m mission evaluation',stages=[stage])
    atomic_json(DATA/'probes'/f'{identifier}-practice.json',result);publish_probes();env.close()
    print(f"Practice goal {stage['target_altitude']:.2f}m/{stage['target_velocity']:.2f}mps: {stage['successes']}/{episodes}; full-task evaluation is separate")
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('checkpoint');parser.add_argument('--episodes',type=int,default=32)
    args=parser.parse_args();practice(args.checkpoint,args.episodes)
