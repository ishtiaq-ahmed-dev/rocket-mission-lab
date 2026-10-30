import math
import time
from types import SimpleNamespace

import pytest
import torch

from rocket_lab.config import load_config
from rocket_lab.train import TrainingCallback


def fake_env(num_envs=1, calls=None):
    return SimpleNamespace(num_envs=num_envs, normalize_obs=lambda x: x,
                           env_method=lambda name, value=None, indices=None: (calls.append((name, value, indices)) if calls is not None else None))


def callback(difficulty=0., config=None, num_envs=1, calls=None):
    cfg = config or load_config()
    instance = TrainingCallback("curriculum-test", "landing", "PPO", 100000, config=cfg, initial_difficulty=difficulty)
    instance.milestones = []
    instance.last_write = time.time()
    env = fake_env(num_envs, calls)
    instance.locals = {"self": SimpleNamespace(get_env=lambda: env)}
    instance.model = SimpleNamespace(policy=SimpleNamespace(log_std=torch.zeros(3)), get_env=lambda: env)
    return instance


def test_stage_check_runs_once_per_interval_not_every_step_in_a_window():
    # A modulo window re-ran the probe for every step under the interval
    # boundary, so several stages could be granted before the actor ever
    # practised them. Each interval must produce at most one decision.
    instance = callback()
    probes, saved = [], []
    instance.stage_flown = lambda: probes.append(instance.num_timesteps) or True
    instance.checkpoint = lambda *a, **k: saved.append((instance.num_timesteps, instance.difficulty))
    for step in (4, 24996, 25000, 25004, 49996, 50000):
        instance.num_timesteps = step
        instance._on_step()
    assert probes == [25000, 50000]
    assert instance.difficulty == pytest.approx(0.1)
    # The actor that passed is saved at the stage it passed, before the bump.
    assert saved == [(25000, 0.), (50000, pytest.approx(0.05))]


def test_stage_probe_flies_the_practised_takeoff_goal_without_noise(monkeypatch):
    import numpy as np
    import rocket_lab.train as module
    calls = []

    class Probe:
        def __init__(self, mission, config=None, difficulty=0., training=False, randomize=True, noise=True):
            calls.append(dict(mission=mission, training=training, randomize=randomize, noise=noise))
        def reset(self, seed=None):
            return np.zeros(21), {}
        def step(self, action):
            return np.zeros(21), 0., True, False, {"outcome": "success"}
        def close(self): pass

    monkeypatch.setattr(module, "RocketEnv", Probe)
    for mission, expected in (("takeoff", True), ("landing", False)):
        instance = TrainingCallback(f"probe-{mission}", mission, "PPO", 1000, config=load_config(), initial_difficulty=.2)
        instance.model = SimpleNamespace(predict=lambda *a, **k: (np.zeros(3), None), get_env=lambda: fake_env())
        instance.locals = {"self": instance.model}
        assert instance.stage_flown() is True
        assert calls[-1] == dict(mission=mission, training=expected, randomize=False, noise=False)


def test_previous_stage_rehearsal_splits_the_vector_env():
    # Rehearsal lives in the training callback, not the environment: editing the
    # env would change the dynamics identity and orphan every saved checkpoint.
    cfg = load_config()
    cfg["training"]["previous_stage_probability"] = .5
    cfg["training"]["n_envs"] = 4
    calls = []
    instance = callback(difficulty=.2, config=cfg, num_envs=4, calls=calls)
    values = instance.practice_difficulties()
    assert values == pytest.approx([.2, .2, .15, .15])
    assert [name for name, _, _ in calls] == ["set_difficulty", "set_difficulty"]
    assert [value for _, value, _ in calls] == pytest.approx([.15, .2])
    assert [indices for _, _, indices in calls] == [[2, 3], [0, 1]]


def test_previous_stage_rehearsal_rejects_out_of_range_probability():
    cfg = load_config()
    cfg["training"]["previous_stage_probability"] = 1.5
    with pytest.raises(ValueError, match="previous_stage_probability"):
        callback(difficulty=.2, config=cfg).practice_difficulties()


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
