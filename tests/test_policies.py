import numpy as np
import torch
from stable_baselines3 import PPO
from rocket_lab.envs import LandingEnv
from rocket_lab.policies import BoundedMeanPolicy

def test_bounded_gaussian_mean_has_finite_gradients_outside_action_range():
    env=LandingEnv(difficulty=0)
    model=PPO(BoundedMeanPolicy,env,n_steps=8,batch_size=8,n_epochs=1,seed=42,device='cpu')
    with torch.no_grad():model.policy.action_net.weight.zero_();model.policy.action_net.bias.fill_(-1.25)
    obs,_=env.reset(seed=12);tensor,_=model.policy.obs_to_tensor(obs)
    distribution=model.policy.get_distribution(tensor)
    mean=distribution.distribution.mean
    np.testing.assert_allclose(mean.detach().numpy(),np.full((1,3),np.tanh(-1.25)),atol=1e-7)
    mean.sum().backward()
    assert torch.isfinite(model.policy.action_net.bias.grad).all()
    assert torch.all(model.policy.action_net.bias.grad>0)
    env.close()

def test_warm_start_exploration_changes_sampling_without_changing_mean_actions():
    import pytest
    from rocket_lab.train import configure_warm_start_exploration
    from rocket_lab.config import load_config
    env=LandingEnv(difficulty=0);model=PPO('MlpPolicy',env,n_steps=8,batch_size=8,device='cpu')
    obs,_=env.reset(seed=12);before=model.predict(obs,deterministic=True)[0]
    gimbal_std=model.policy.log_std[1:].detach().clone()
    cfg=load_config();cfg['training']['warm_start_action_std']=[.15,None,None]
    configure_warm_start_exploration(model,cfg)
    np.testing.assert_array_equal(before,model.predict(obs,deterministic=True)[0])
    assert model.policy.log_std[0].exp().item()==pytest.approx(.15)
    assert torch.equal(model.policy.log_std[1:],gimbal_std)
    cfg['training']['warm_start_action_std']=[.15,0,None]
    with pytest.raises(ValueError,match='positive finite'):configure_warm_start_exploration(model,cfg)
    env.close()

def test_bounded_policy_updates_and_serializes_with_the_same_actions(tmp_path):
    env=LandingEnv(difficulty=0)
    model=PPO(BoundedMeanPolicy,env,n_steps=8,batch_size=8,n_epochs=1,seed=91,device='cpu')
    before=model.policy.action_net.weight.detach().clone();model.learn(32)
    assert not torch.equal(before,model.policy.action_net.weight)
    obs,_=env.reset(seed=13);expected=model.predict(obs,deterministic=True)[0]
    model.save(tmp_path/'bounded.zip');restored=PPO.load(tmp_path/'bounded.zip',device='cpu')
    assert isinstance(restored.policy,BoundedMeanPolicy)
    np.testing.assert_array_equal(expected,restored.predict(obs,deterministic=True)[0])
    env.close()
