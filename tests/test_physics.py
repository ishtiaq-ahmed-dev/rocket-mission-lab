import numpy as np
import pytest
from gymnasium.utils.env_checker import check_env
from rocket_lab.config import load_config
from rocket_lab.physics import RocketPhysics
from rocket_lab.envs import LandingEnv, TakeoffEnv
from rocket_lab.controllers import ClassicalController

def vacuum():
    cfg=load_config(); cfg["world"]["density_sea_level"]=0; cfg["world"]["wind_mean"]=[0,0,0]; cfg["world"]["gust_std"]=0
    return cfg

def test_free_fall():
    p=RocketPhysics(vacuum()); p.reset(7,position=[0,0,1020],velocity=[0,0,0])
    for _ in range(10): s=p.step([-1,0,0])
    assert s["position"][2]==pytest.approx(1020-0.5*9.80665*s["t"]**2,abs=1e-7)
    assert s["velocity"][2]==pytest.approx(-9.80665*s["t"],abs=1e-7)

def test_vacuum_energy():
    p=RocketPhysics(vacuum()); initial=p.reset(2,position=[0,0,1020],velocity=[3,0,0])
    e0=0.5*np.dot(initial["velocity"],initial["velocity"])+9.80665*initial["position"][2]
    for _ in range(10): s=p.step([-1,0,0])
    assert .5*np.dot(s["velocity"],s["velocity"])+9.80665*s["position"][2]==pytest.approx(e0,rel=1e-9)
    assert s["velocity"][0]==pytest.approx(3)

def test_fuel_and_limits():
    p=RocketPhysics(vacuum()); initial=p.fuel; s=p.step([-.9,1,1])
    assert s["throttle"]==pytest.approx(p.v["min_throttle"])
    assert initial-s["fuel_mass"]==pytest.approx(p.thrust*s["t"]/(p.v["isp"]*p.w["gravity"]))
    assert np.max(np.abs(s["gimbal"]))<=np.deg2rad(p.v["gimbal_limit_deg"])
    p.fuel=0; s=p.step([1,0,0]); assert s["throttle"]==0

@pytest.mark.parametrize("cls",[LandingEnv,TakeoffEnv])
def test_gym_and_determinism(cls):
    check_env(cls(),skip_render_check=True)
    a,b=cls(),cls(); oa,_=a.reset(seed=42); ob,_=b.reset(seed=42)
    np.testing.assert_array_equal(oa,ob)
    for _ in range(5):
        x=a.step([.1,.02,0]); y=b.step([.1,.02,0]); np.testing.assert_array_equal(x[0],y[0]); assert np.isfinite(x[1])

def test_classical_improvement():
    results=[]
    for level in [1,4]:
        successes=0
        for seed in range(10):
            e=LandingEnv(); e.reset(seed=seed); c=ClassicalController(level)
            for _ in range(1000):
                _,_,term,trunc,info=e.step(c.action(e))
                if term or trunc: break
            successes+=info["outcome"]=="success"
        results.append(successes)
    assert results[1]>results[0], results
