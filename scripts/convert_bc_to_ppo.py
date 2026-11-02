"""Convert the behavior-cloned combined actor into a PPO resume checkpoint.

The cloned actor already reaches the pad; PPO continues from its weights and
uses the terminal reward to learn the engine/RCS switching that regression
smooths away. The clone's observation normalizer is carried into VecNormalize,
so the transferred actor sees exactly the input distribution it was trained on.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import torch
from torch import nn
import yaml
from stable_baselines3 import PPO
from stable_baselines3.common.monitor import Monitor
from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize

from rocket_lab.config import load_config
from rocket_lab.envs import RocketEnv
from rocket_lab.missions import configure_flight
from rocket_lab.policies import BoundedMeanPolicy
from rocket_lab.storage import atomic_json, config_hash, dynamics_hash


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--bc', default='bc-combined-v3__step-000000001')
    parser.add_argument('--output', default='data/checkpoints/bc-warmstart-combined-v1/step-000000000')
    parser.add_argument('--config', default='config/combined-bc-ppo-v1.yaml')
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args()
    from rocket_lab.storage import checkpoint_path
    bc_path = checkpoint_path(args.bc)
    meta = json.loads((bc_path / 'checkpoint.json').read_text(encoding='utf-8'))
    cfg = meta['config']
    # The transfer is on the full mission; RCS is now an explicit action.
    cfg['training'].update(
        rcs_action=True,
        takeoff_goal_curriculum=False,
        target_curriculum=False,
        retarget_probability=0.,
        initial_difficulty=1.,
        curriculum_increment=0.,
        curriculum_check_interval=0,
        previous_stage_probability=0.,
        observation_normalization=True,
        reward_normalization=True,
        policy_architecture=[384, 384],
        bounded_action_mean=True,
        policy_log_std=-2.5,
        ppo_n_steps=1024,
        ppo_batch_size=512,
        ppo_epochs=10,
        ppo_gamma=.999,
        ppo_gae_lambda=.98,
        ppo_entropy=.0005,
        ppo_target_kl=.02,
        learning_rate=.0001,
        evaluation_episodes=24,
        checkpoints=[10000, 50000, 100000, 200000],
        checkpoint_interval=1000000,
        profile='bc-ppo-finetune-v1',
    )
    cfg['reward'].update(
        success=1000., failure=-100., terminal_speed=.5, terminal_tilt=.2,
        terminal_position=1., potential_horizontal_speed=12., time_cost=.5,
        success_fuel_bonus=500.,
    )
    cfg, _ = configure_flight(cfg, mission='combined')
    Path(args.config).write_text(yaml.safe_dump(cfg, sort_keys=False), encoding='utf-8')

    stats = np.load(bc_path / 'normalizer.npz')
    mean, std = stats['mean'].astype(np.float32), stats['std'].astype(np.float32)
    vector = DummyVecEnv([
        lambda: Monitor(RocketEnv('combined', config=cfg, difficulty=1., training=True))
        for _ in range(4)
    ])
    vector = VecNormalize(vector, norm_obs=True, norm_reward=True, clip_obs=10.)
    vector.obs_rms.mean = mean
    vector.obs_rms.var = std ** 2
    vector.obs_rms.count = 1e6
    model = PPO(
        BoundedMeanPolicy, vector, n_steps=1024, batch_size=512, n_epochs=10,
        gamma=.999, gae_lambda=.98, learning_rate=1e-4, ent_coef=.0005,
        target_kl=.02, seed=args.seed, device='cpu',
        policy_kwargs=dict(net_arch=[384, 384], activation_fn=nn.SiLU, log_std_init=-2.5),
    )
    state = model.policy.state_dict()
    clone = torch.load(bc_path / 'model.pt', map_location='cpu', weights_only=True)
    for target, source in (
        ('mlp_extractor.policy_net.0.weight', 'net.0.weight'),
        ('mlp_extractor.policy_net.0.bias', 'net.0.bias'),
        ('mlp_extractor.policy_net.2.weight', 'net.2.weight'),
        ('mlp_extractor.policy_net.2.bias', 'net.2.bias'),
        ('action_net.weight', 'net.4.weight'),
        ('action_net.bias', 'net.4.bias'),
    ):
        if target not in state:
            raise KeyError(f'PPO policy has no {target}')
        state[target] = clone[source].clone()
    with torch.no_grad():
        model.policy.log_std.fill_(-2.5)
    state['log_std'] = model.policy.log_std.detach().clone()
    model.policy.load_state_dict(state)

    output = ROOT / args.output
    output.mkdir(parents=True, exist_ok=True)
    model.save(output / 'model.zip')
    vector.save(output / 'normalize.pkl')
    checkpoint = dict(
        job_id=output.parent.name, mission='combined', algorithm='PPO', steps=0,
        seed=args.seed, config_hash=config_hash(cfg), difficulty=1., config=cfg,
        source_hash=None, dynamics_hash=dynamics_hash(), created_at=None,
        success_rate=0., mean_reward=-1e9, evaluation_episodes=0,
        qualification='BC-initialized PPO actor; evaluation pending',
        rcs_action=True, hidden=384, action_dim=6, observation_dim=22,
        initialized_from=args.bc,
    )
    atomic_json(output / 'checkpoint.json', checkpoint)
    print(json.dumps({k: checkpoint[k] for k in ('job_id', 'steps', 'algorithm', 'rcs_action', 'config_hash')}, indent=2))
    print(f'WARM START {output}')


if __name__ == '__main__':
    main()
