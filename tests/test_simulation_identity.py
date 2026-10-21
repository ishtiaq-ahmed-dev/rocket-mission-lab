import numpy as np
import pytest
from rocket_lab import simulation


def test_automatically_selected_actor_is_recorded_and_wrong_mission_rejected(monkeypatch):
    class FakePolicy:
        def __init__(self,identifier,observation_config=None):
            self.meta=dict(mission='landing',steps=100,algorithm='PPO')
        def action(self,observation):return np.array([-1.,0.,0.])
    monkeypatch.setattr(simulation,'LearnedPolicy',FakePolicy)
    monkeypatch.setattr(simulation,'select_checkpoint',lambda mission,level,**kwargs:dict(id='landing-job__step-000000100'))
    replay=simulation.simulate('landing','rl',seed=42,save=False)
    assert replay.run.checkpoint_id=='landing-job__step-000000100'
    assert 'landing-job__step-000000100' in replay.run.id
    with pytest.raises(ValueError,match='mission does not match'):
        simulation.simulate('takeoff','rl',checkpoint_id='landing-job__step-000000100',save=False)
    with pytest.raises(ValueError,match='separate checkpoint'):
        simulation.simulate('combined','rl',checkpoint_id='landing-job__step-000000100',save=False)
