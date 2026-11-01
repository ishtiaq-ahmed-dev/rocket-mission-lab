import numpy as np
import pytest
from gymnasium.utils.env_checker import check_env
from rocket_lab.config import load_config
from rocket_lab.physics import RocketPhysics
from rocket_lab.envs import LandingEnv, TakeoffEnv
from rocket_lab.controllers import ClassicalController

def vacuum():
    cfg=load_config(); cfg["world"]["gravity_model"]='constant';cfg["world"]["atmosphere_model"]='exponential';cfg["world"]["density_sea_level"]=0; cfg["world"]["wind_mean"]=[0,0,0]; cfg["world"]["gust_std"]=0
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

def test_native_rotation_preserves_normalization_and_independent_return_values():
    from scipy.spatial.transform import Rotation
    physics=RocketPhysics(vacuum());physics.data.qpos[3:7]=[2.,.5,-.2,.1]
    stored=physics.data.qpos[3:7].copy()
    expected=Rotation.from_quat([.5,-.2,.1,2.]).as_matrix()
    actual=physics.rotation();np.testing.assert_allclose(actual,expected,atol=1e-14)
    np.testing.assert_array_equal(physics.data.qpos[3:7],stored)
    actual[:]=0;assert np.linalg.norm(physics.rotation())>1
    physics.data.qpos[3:7]=0
    with pytest.raises(ValueError,match='nonzero'):physics.rotation()

@pytest.mark.parametrize("angles",[[0,0,0],[.2,-.25,.4],[.65,.2,-.9]])
def test_tilted_thrust_and_engine_torque_follow_newton_euler(angles):
    from scipy.spatial.transform import Rotation
    cfg=vacuum();cfg["world"]["timestep"]=.0005;cfg["world"]["control_substeps"]=1
    p=RocketPhysics(cfg);rotation=Rotation.from_euler("xyz",angles);q=rotation.as_quat()
    initial=p.reset(42,position=[0,0,1020],velocity=[0,0,0],quaternion=[q[3],*q[:3]])
    p.throttle=.6
    state=p.step([.2,.4,-.3]);dt=state["t"]
    direction=np.array([np.tan(p.gimbal[0]),np.tan(p.gimbal[1]),1.]);force=direction/np.linalg.norm(direction)*p.thrust
    expected_acceleration=rotation.as_matrix()@force/initial["mass"]+np.array([0,0,-cfg["world"]["gravity"]])
    expected_rate=np.cross([0,0,-p.engine_lever],force)/(np.asarray(p.v["inertia"])*initial["mass"]/p.v["dry_mass"])*dt
    np.testing.assert_allclose(state["velocity"]/dt,expected_acceleration,atol=1e-8)
    np.testing.assert_allclose(state["angular_velocity"],expected_rate,atol=1e-9)

def test_fuel_and_limits():
    p=RocketPhysics(vacuum()); initial=p.fuel
    # The turbopump spools from zero at a bounded rate, so the first control
    # interval cannot jump straight to the minimum-thrust floor. Let it settle,
    # then verify the steady floor and the Isp fuel relation over one interval.
    for _ in range(10): p.step([-.9,1,1])
    before=p.fuel; s=p.step([-.9,1,1]); interval=p.w["timestep"]*p.w["control_substeps"]
    assert s["throttle"]==pytest.approx(p.v["min_throttle"])
    assert initial-s["fuel_mass"]==pytest.approx((initial-before)+p.thrust*interval/(p.isp*p.w["gravity"]))
    assert np.max(np.abs(s["gimbal"]))<=np.deg2rad(p.v["gimbal_limit_deg"])
    p.fuel=0; s=p.step([1,0,0]); assert s["throttle"]==0

def test_inverse_square_gravity_and_standard_atmosphere():
    from rocket_lab.physics import gravity_at
    from rocket_lab.atmosphere import temperature_at,pressure_at,air_density,speed_of_sound
    cfg=load_config();w=cfg['world']
    assert gravity_at(w,0.)==pytest.approx(9.80665)
    assert gravity_at(w,70000.)==pytest.approx(9.80665*(6371000/(6371000+70000))**2)
    assert gravity_at(w,400000.)==pytest.approx(8.68,abs=.01)
    assert temperature_at(w,0.)==pytest.approx(288.15)
    assert temperature_at(w,11000.)==pytest.approx(216.65,abs=.2)
    assert pressure_at(w,0.)==pytest.approx(101325.,rel=1e-6)
    # 11 km geometric altitude is slightly below 11 km geopotential; the
    # standard-table comparison tolerates the 0.3% conversion difference.
    assert pressure_at(w,11000.)==pytest.approx(22632.,rel=.004)
    assert air_density(w,0.)==pytest.approx(1.225,rel=1e-5)
    assert speed_of_sound(w,0.)==pytest.approx(340.3,abs=.2)

def test_engine_sea_level_and_vacuum_performance():
    from rocket_lab.propulsion import engine_performance
    from rocket_lab.atmosphere import drag_coefficient_at
    cfg=load_config();w,v=cfg['world'],cfg['vehicle']
    sea,isp_sea=engine_performance(w,v,1.,0.)
    vacuum,isp_vac=engine_performance(w,v,1.,100000.)
    assert sea==pytest.approx(914000.-101325.*.68,rel=1e-6)
    assert vacuum==pytest.approx(914000.,rel=1e-6)
    assert isp_sea==pytest.approx(282.,abs=.3)
    assert isp_vac==pytest.approx(311.,abs=.3)
    assert drag_coefficient_at(v,0.)==.5
    assert drag_coefficient_at(v,1.)==pytest.approx(.85)
    assert drag_coefficient_at(v,2.)==pytest.approx(.55)

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

def test_curriculum_reaches_environment_through_wrappers():
    from stable_baselines3.common.monitor import Monitor
    from stable_baselines3.common.vec_env import DummyVecEnv,VecNormalize
    vec=VecNormalize(DummyVecEnv([lambda:Monitor(LandingEnv(difficulty=0))]))
    vec.env_method("set_difficulty",.6)
    assert vec.envs[0].unwrapped.difficulty==pytest.approx(.6)
    vec.close()

def test_zero_difficulty_is_easy_not_full_altitude():
    env=LandingEnv(difficulty=0);env.reset(seed=42)
    s=env.physics.state()
    assert s["altitude"]==3
    np.testing.assert_array_equal(s["position"][:2],[0,0])
    np.testing.assert_array_equal(s["velocity"],[0,0,-.8])
    assert env.physics.wind_scale==0

def test_recorded_difficulty_changes_start_and_has_a_distinct_identity():
    from rocket_lab.simulation import simulate
    full=simulate(level=1,seed=21000,save=False)
    stage=simulate(level=1,seed=21000,save=False,difficulty=.4)
    cfg=load_config();rest=cfg["vehicle"]["length"]/2+cfg["mission"]["launch_stand_height"]
    assert stage.frames[0].position[2]-rest==pytest.approx(3+.4*(full.frames[0].position[2]-rest-3))
    assert stage.run.difficulty==.4 and full.run.difficulty==1
    assert stage.run.id!=full.run.id and '-d0.400000-' in stage.run.id
    assert full.run.id.startswith('landing-classical-l1-s21000-')
    assert stage.run.touchdown_speed==pytest.approx(np.linalg.norm(stage.frames[-1].velocity))
    with pytest.raises(ValueError,match='difficulty'):simulate(save=False,difficulty=1.1)

def test_v4_shaping_explicitly_penalizes_horizontal_drift_without_expert_actions():
    import copy
    cfg=load_config();cfg['reward']['profile']='state-potential-v3'
    old=LandingEnv(config=cfg);old.reset(seed=42);state=old.physics.state();state['velocity']=np.array([2.,-3.,-10.])
    updated=copy.deepcopy(cfg);updated['reward']['profile']='state-potential-v4';updated['reward']['potential_horizontal_speed']=12.
    new=LandingEnv(config=updated);new.reset(seed=42)
    assert new._potential(state)-old._potential(state)==pytest.approx(-12*np.sqrt(13))
    old.close();new.close()

def test_full_start_mixture_is_training_only_and_keeps_episode_noise_fixed():
    import copy
    cfg=load_config();cfg['training']['full_start_probability']=1.
    evaluation=LandingEnv(config=cfg,difficulty=.2)
    reference_cfg=copy.deepcopy(cfg);reference_cfg['training']['full_start_probability']=0.
    reference=LandingEnv(config=reference_cfg,difficulty=.2)
    np.testing.assert_array_equal(evaluation.reset(seed=42)[0],reference.reset(seed=42)[0])
    training=LandingEnv(config=cfg,difficulty=.2,training=True);training.reset(seed=42)
    assert training.episode_difficulty==1. and training.difficulty==.2
    assert cfg['mission']['landing_altitude'][0]<=training.physics.state()['altitude']<=cfg['mission']['landing_altitude'][1]
    assert training.physics.wind_scale==1.
    training.set_difficulty(.3)
    assert training.episode_difficulty==1. # noise/timeout belong to this reset
    _,_,_,_,info=training.step([-1,0,0]);assert info['episode_difficulty']==1.
    for env in (evaluation,reference,training):env.close()

def test_disabled_mixture_preserves_seeded_training_observations():
    cfg=load_config();cfg['training']['full_start_probability']=0.
    training=LandingEnv(config=cfg,difficulty=.4,training=True);evaluation=LandingEnv(config=cfg,difficulty=.4)
    np.testing.assert_array_equal(training.reset(seed=91)[0],evaluation.reset(seed=91)[0])
    for _ in range(10):np.testing.assert_array_equal(training.step([.1,.2,-.1])[0],evaluation.step([.1,.2,-.1])[0])
    training.close();evaluation.close()

def test_takeoff_goal_curriculum_exposes_the_actual_goal_and_keeps_evaluation_full():
    cfg=load_config();cfg['training'].update(takeoff_goal_curriculum=True,takeoff_curriculum_altitude=5.,takeoff_curriculum_velocity=3.)
    easy=TakeoffEnv(config=cfg,difficulty=0,training=True);obs,_=easy.reset(seed=42)
    assert easy.takeoff_altitude==5 and easy.takeoff_velocity==3
    assert easy._target()[2]==easy.physics.rest+5
    assert obs[17]==pytest.approx(5/cfg['training']['observation_position_scale'][2])
    assert obs[18]==pytest.approx(3/50)
    evaluation=TakeoffEnv(config=cfg,difficulty=0);evaluation.reset(seed=42)
    assert evaluation.takeoff_altitude==400 and evaluation.takeoff_velocity==25
    full=TakeoffEnv(config=cfg,difficulty=1,training=True);full.reset(seed=42)
    assert full.takeoff_altitude==400 and full.takeoff_velocity==25
    easy.set_difficulty(.5)
    assert easy.takeoff_altitude==5 # goals change on reset, not mid-flight
    easy.reset(seed=42);assert easy.takeoff_altitude==202.5
    for env in (easy,evaluation,full):env.close()
    from rocket_lab.simulation import simulate
    replay=simulate('takeoff',level=1,seed=42,save=False,config=cfg,difficulty=0,training=True)
    assert replay.run.training_mode and replay.run.target_altitude==5 and replay.run.target_velocity==3
    assert '-practice-' in replay.run.id


def test_axial_lateral_drag_uses_broadside_area_and_body_axis():
    from rocket_lab.atmosphere import aerodynamic_force
    cfg=load_config();vehicle=cfg['vehicle'];world=cfg['world']
    vertical=aerodynamic_force(world,vehicle,np.eye(3),[0,0,20],[0,0,0],0.)
    broadside=aerodynamic_force(world,vehicle,np.eye(3),[20,0,0],[0,0,0],0.)
    assert vertical[2]<0 and abs(vertical[0])<1e-12
    assert broadside[0]<0 and abs(broadside[2])<1e-12
    assert abs(broadside[0])>abs(vertical[2])


def test_legacy_isotropic_drag_is_unchanged_without_the_new_model():
    from rocket_lab.atmosphere import air_density, aerodynamic_force
    cfg=load_config();cfg['vehicle'].pop('aero_model')
    force=aerodynamic_force(cfg['world'],cfg['vehicle'],np.eye(3),[3,4,0],[0,0,0],0.)
    rho=air_density(cfg['world'],0.)
    np.testing.assert_allclose(force,-0.5*rho*cfg['vehicle']['drag_coefficient']*cfg['vehicle']['area']*5*np.array([3,4,0]))


def test_aerodynamic_center_weathercocks_a_tilted_descent():
    cfg=load_config();cfg['world']['wind_mean']=[0,0,0];cfg['world']['gust_std']=0
    tilt=np.deg2rad(10);quaternion=[np.cos(tilt/2),0,np.sin(tilt/2),0]
    def angular_rate(center):
        cfg['vehicle']['aero_center']=center
        p=RocketPhysics(cfg);p.reset(5,position=[0,0,600],velocity=[0,0,-20],quaternion=quaternion)
        return p.step([-1,0,0])['angular_velocity']
    without=angular_rate(0.)
    with_center=angular_rate(5.)
    assert abs(without[1])<1e-8
    assert with_center[1]<-1e-6


def test_wind_shear_increases_mean_wind_with_altitude():
    from rocket_lab.atmosphere import wind_at
    cfg=load_config();world=cfg['world']
    low=wind_at(world,[2.,-1.,0.],0.)
    high=wind_at(world,[2.,-1.,0.],120.)
    assert np.linalg.norm(high)>np.linalg.norm(low)


def test_combined_mission_gets_a_two_phase_timeout():
    from rocket_lab.envs import RocketEnv
    combined=RocketEnv('combined',config=load_config(),noise=False,randomize=False)
    landing=LandingEnv()
    assert combined.cfg['mission']['timeout']>=240.
    assert landing.cfg['mission']['timeout']==load_config()['mission']['timeout']
    combined.close();landing.close()


def test_curriculum_relaxes_tilt_at_easy_stages_and_restores_it_at_full():
    def outcome(difficulty):
        env=LandingEnv(difficulty=difficulty)
        tilt=np.deg2rad(8);quaternion=[np.cos(tilt/2),0,np.sin(tilt/2),0]
        env.reset(seed=1,options={'state':dict(position=[0,0,env.physics.rest+.2],velocity=[0,0,-.5],quaternion=quaternion)})
        while True:
            _,_,term,trunc,info=env.step([-1.,0.,0.])
            if term or trunc:return info['outcome']
    assert outcome(0.)=='success'
    assert outcome(1.)=='crash_tilt'
