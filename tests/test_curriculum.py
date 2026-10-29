import math
import time
from types import SimpleNamespace

import pytest
import torch

from rocket_lab.config import load_config
from rocket_lab.train import TrainingCallback


def callback(difficulty=0., config=None):
    cfg = config or load_config()
    instance = TrainingCallback("curriculum-test", "landing", "PPO", 100000, config=cfg, initial_difficulty=difficulty)
    instance.milestones = []
    instance.last_write = time.time()
    instance.model = SimpleNamespace(policy=SimpleNamespace(log_std=torch.zeros(3)),
                                     get_env=lambda: SimpleNamespace(env_method=lambda *a, **k: None, normalize_obs=lambda x: x))
    return instance


def test_stage_check_runs_once_per_interval_not_every_step_in_a_window():
    # A modulo window re-ran the probe for every step under the interval
    # boundary, so several stages could be granted before the actor ever
    # practised them. Each interval must produce at most one decision.
    instance = callback()
    probes = []
    instance.stage_flown = lambda: probes.append(instance.num_timesteps) or True
    for step in (4, 24996, 25000, 25004, 49996, 50000):
        instance.num_timesteps = step
        instance._on_step()
    assert probes == [25000, 50000]
    assert instance.difficulty == pytest.approx(0.1)


def test_exploration_floor_shrinks_with_curriculum_but_never_vanishes():
    instance = callback(difficulty=0.)
    assert instance.exploration_floor() == pytest.approx(load_config()["training"]["policy_exploration_std"])
    instance.difficulty = 1.
    assert instance.exploration_floor() == pytest.approx(load_config()["training"]["policy_min_std"])
    instance.difficulty = .5
    easy = load_config()["training"]["policy_exploration_std"]
    hard = load_config()["training"]["policy_min_std"]
    assert instance.exploration_floor() == pytest.approx(hard + (easy - hard) * .5)


def test_keep_exploration_raises_a_collapsed_std_to_the_floor():
    instance = callback(difficulty=0.)
    instance.model.policy.log_std = torch.full((3,), -6.)
    instance.keep_exploration()
    floor = load_config()["training"]["policy_exploration_std"]
    assert torch.allclose(instance.model.policy.log_std, torch.full((3,), math.log(floor)))


def test_mismatched_exploration_bounds_are_rejected():
    cfg = load_config()
    cfg["training"]["policy_min_std"] = cfg["training"]["policy_exploration_std"] + .1
    with pytest.raises(ValueError, match="policy_min_std"):
        callback(config=cfg).exploration_floor()


def test_ppo_exploration_floor_does_not_access_sac_policy_variance():
    instance=callback();instance.algorithm='SAC'
    instance.model.policy=SimpleNamespace()
    instance.keep_exploration()
