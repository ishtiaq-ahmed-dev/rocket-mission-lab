"""Inspect a learned actor's distribution along a real deterministic flight."""
from pathlib import Path
import argparse
import sys
import numpy as np
import torch
from scipy.special import ndtr
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from rocket_lab.config import DATA
from rocket_lab.envs import RocketEnv
from rocket_lab.simulation import LearnedPolicy
from rocket_lab.storage import atomic_json

def diagnose(identifier,seed=21000):
    torch.set_num_threads(2)
    policy=LearnedPolicy(identifier);env=RocketEnv();observation,_=env.reset(seed=seed);rows=[]
    while True:
        normalized=policy.norm.normalize_obs(np.array([observation]))
        tensor,_=policy.model.policy.obs_to_tensor(normalized)
        with torch.no_grad():distribution=policy.model.policy.get_distribution(tensor).distribution
        mean=distribution.mean[0].cpu().numpy();std=distribution.stddev[0].cpu().numpy();state=env.physics.state()
        rows.append(dict(t=state['t'],altitude=state['altitude'],velocity=state['velocity'].tolist(),
                         action_mean=mean.tolist(),action_std=std.tolist(),
                         probability_throttle_sample_above_engine_cutoff=float(ndtr((mean[0]+.96)/std[0])),
                         probability_throttle_sample_outside_bounds=float(ndtr((-1-mean[0])/std[0])+ndtr((mean[0]-1)/std[0]))))
        observation,_,terminated,truncated,info=env.step(policy.action(observation))
        if terminated or truncated:break
    report=dict(checkpoint_id=identifier,seed=seed,difficulty=1.,
                scope='Gaussian distribution diagnostic on one deterministic development trajectory; not a training or reliability result',
                engine_cutoff_normalized_action=-.96,outcome=info,rows=rows)
    atomic_json(DATA/'diagnostics'/f'{identifier}-s{seed}.json',report);env.close()
    print(f"{identifier}: initial throttle mean {rows[0]['action_mean'][0]:.4f}, std {rows[0]['action_std'][0]:.4f}, engine-on sampling probability {rows[0]['probability_throttle_sample_above_engine_cutoff']:.3g}")
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('checkpoint_id');parser.add_argument('--seed',type=int,default=21000)
    args=parser.parse_args();diagnose(args.checkpoint_id,args.seed)
