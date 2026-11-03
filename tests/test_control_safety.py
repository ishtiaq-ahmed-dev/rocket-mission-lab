import numpy as np
import pytest

from rocket_lab.envs import RocketEnv
from rocket_lab.physics import RocketPhysics


@pytest.mark.parametrize("value", [np.nan, np.inf, -np.inf])
@pytest.mark.parametrize("index", range(6))
def test_invalid_rl_action_does_not_mutate_physics(value, index):
    env = RocketEnv(mission="combined", rcs_action=True, noise=False)
    env.reset(seed=42)
    before = env.physics.state()
    torque = env.physics.rcs_torque.copy()
    action = np.zeros(6)
    action[index] = value
    with pytest.raises(ValueError, match="finite"):
        env.step(action)
    np.testing.assert_array_equal(env.physics.data.qpos[:3], before["position"])
    np.testing.assert_array_equal(env.physics.rcs_torque, torque)
    assert env.physics.data.time == before["t"]


@pytest.mark.parametrize("value", [np.nan, np.inf, -np.inf])
def test_physics_rejects_nonfinite_before_clipping(value):
    physics = RocketPhysics()
    with pytest.raises(ValueError, match="finite"):
        physics.step([value, 0, 0])
    assert physics.data.time == 0


def test_free_body_arena_has_headroom_without_default_multimegabyte_reservation():
    physics = RocketPhysics()
    for _ in range(100):
        physics.step([1, 0.5, -0.5])
    assert physics.model.narena <= 256 * 1024
    assert physics.data.maxuse_arena < physics.model.narena / 4
    assert not np.any(physics.data.warning.number)


def test_light_booster_can_cut_off_below_twelve_metres_instead_of_bouncing():
    from rocket_lab.controllers import ClassicalController
    env = RocketEnv(noise=False, randomize=False)
    env.reset(seed=42, options={'state':dict(position=[0,0,28.5],velocity=[0,0,-0.2])})
    env.physics.fuel = 1000.
    env.physics._mass_update()
    env.last_state = env.physics.state()
    env._obs(env.last_state)
    action = ClassicalController(4).action(env)
    assert action[0] == -1.


@pytest.mark.parametrize('altitude', [0., 100000.])
def test_native_engine_uses_the_same_pressure_and_isp_model_as_guidance(altitude):
    from rocket_lab.config import load_config
    from rocket_lab.isaac.actuators import Engine
    from rocket_lab.propulsion import engine_performance
    config = load_config()
    engine = Engine(config['vehicle'], config['world']['gravity'], config['world'])
    for _ in range(100):
        force, torque, burn = engine.step([0.2,0,0],0.02,1000.,altitude=altitude)
    thrust, isp = engine_performance(config['world'],config['vehicle'],0.6,altitude)
    assert force[2] == pytest.approx(thrust)
    assert burn == pytest.approx(thrust*0.02/(isp*config['world']['gravity']))


def test_resolved_collision_does_not_hide_impact_speed_from_rl_reward_or_report(monkeypatch):
    env = RocketEnv(noise=False, randomize=False)
    env.reset(seed=1)
    contact = {**env.last_state, 't':0.1, 'clearance':0., 'contact_speed':3., 'velocity':np.array([0.,0.,-.1])}
    monkeypatch.setattr(env.physics, 'step', lambda action: contact)
    _, _, terminated, _, info = env.step([-1,0,0])
    assert terminated and info['outcome'] == 'crash_speed'
    assert info['touchdown_speed'] == 3.


@pytest.mark.parametrize('height,emergency_hold', [(600.,False),(100.,True)])
def test_native_retarget_preserves_fuel_by_using_existing_high_altitude_shelf(monkeypatch,height,emergency_hold):
    from types import SimpleNamespace
    from rocket_lab.controllers import ClassicalController
    from rocket_lab.isaac.guidance import NativeGuidance
    state = dict(t=0.,mass=38000.,position=np.array([0.,0.,height+20.]),velocity=np.zeros(3))
    physics = SimpleNamespace(v=dict(max_thrust=914000.),model=SimpleNamespace(body_inertia=np.ones((2,3))),
                              engine_lever=17.9,attached=False,half=20.,rest=23.,state=lambda:state)
    monkeypatch.setattr(ClassicalController,'action',lambda self,env:np.zeros(3))
    controller=NativeGuidance()
    controller.on_retarget()
    controller.action(SimpleNamespace(phase='landing',physics=physics,sensed_state=state))
    assert controller.divert is emergency_hold


@pytest.mark.parametrize('noise', [False,True])
def test_native_perfect_state_does_not_acquire_navigation_filter_lag(monkeypatch,noise):
    from types import SimpleNamespace
    from rocket_lab.controllers import ClassicalController
    from rocket_lab.isaac.guidance import NativeGuidance
    state=dict(t=0.,mass=38000.,position=np.array([0.,0.,520.]),velocity=np.zeros(3))
    physics=SimpleNamespace(v=dict(max_thrust=914000.),model=SimpleNamespace(body_inertia=np.ones((2,3))),
                            engine_lever=17.9,attached=False,half=20.,rest=23.,state=lambda:state)
    captured=[]
    monkeypatch.setattr(ClassicalController,'action',lambda self,env:captured.append(self.estimate) or np.zeros(3))
    controller=NativeGuidance()
    previous={'velocity':np.array([0.,0.,-3.])}
    controller.estimate=previous
    controller.action(SimpleNamespace(phase='landing',physics=physics,sensed_state=state,noise=noise))
    assert captured[0] is (previous if noise else None)
