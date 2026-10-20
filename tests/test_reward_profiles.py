import copy
import numpy as np
import pytest
from rocket_lab.config import load_config
from rocket_lab.envs import RocketEnv


def test_ground_speed_reward_preserves_physics_and_only_penalizes_landing_near_surface():
    base=load_config();changed=copy.deepcopy(base)
    changed['reward'].update(ground_speed_cost=2.,ground_speed_height=50.)
    for mission,height in [('landing',20.),('landing',80.),('takeoff',20.)]:
        first=RocketEnv(mission,config=base,noise=False,randomize=False)
        second=RocketEnv(mission,config=changed,noise=False,randomize=False)
        options={'state':dict(position=[0,0,first.physics.half+height],velocity=[1.,.5,-3.])}
        a,_=first.reset(seed=60,options=options);b,_=second.reset(seed=60,options=options)
        np.testing.assert_array_equal(a,b)
        ar=first.step([0.,0.,0.]);br=second.step([0.,0.,0.])
        np.testing.assert_array_equal(ar[0],br[0]);assert ar[2:]==br[2:]
        state=second.last_state
        expected=.1*2.*max(0.,1-max(0.,state['altitude'])/50.)**2*float(np.dot(state['velocity'],state['velocity'])) if mission=='landing' else 0.
        assert ar[1]-br[1]==pytest.approx(expected,abs=1e-10)
        first.close();second.close()
    for cost,height in [(-1,50),(np.nan,50),(1,0),(1,np.inf)]:
        changed['reward'].update(ground_speed_cost=cost,ground_speed_height=height)
        with pytest.raises(ValueError,match='Ground speed'):RocketEnv(config=changed)
