import numpy as np
import pytest
from rocket_lab.physics import RocketPhysics, gravity_at
from rocket_lab.config import load_config
from rocket_lab.simulation import simulate

def test_launch_support_is_a_one_way_physical_release():
    p=RocketPhysics();p.reset(1,position=[20,-30,20],velocity=[0,0,0])
    before=p.data.qpos.copy()
    for _ in range(3):
        s=p.step([1,.5,-.5])
        assert s['hold_down'] and s['release_time'] is None
        np.testing.assert_array_equal(p.data.qpos,before)
    for _ in range(20):
        s=p.step([1,0,0])
        if not s['hold_down']:break
    assert not s['hold_down'] and s['release_time']>0 and s['altitude']>0
    release=s['release_time'];p.step([-1,0,0]);assert p.release_time==release

def test_tilted_feet_contact_above_the_old_center_height_plane():
    from scipy.spatial.transform import Rotation
    p=RocketPhysics();q=Rotation.from_euler('x',4,degrees=True).as_quat()
    p.reset(7,position=[2,3,21+p.stand],velocity=[0,0,-1],quaternion=[q[3],*q[:3]])
    for _ in range(30):
        s=p.step([-1,0,0])
        if s['clearance']<1e-7:break
    assert abs(s['clearance'])<1e-7
    assert s['altitude']>.1 and s['velocity'][2]<-1
    assert s['position'][0]==pytest.approx(2,abs=.01)

def test_cutoff_precedes_separation_and_released_stage_is_recorded():
    t=simulate('combined',save=False,flight_plan=dict(launch=[0,0],landing=[80,40],separation_altitude=400))
    first=next(i for i,f in enumerate(t.frames) if f.upper_stage)
    assert t.frames[first].throttle==0 and t.frames[first].phase=='landing'
    assert t.run.separation.t==t.frames[first].t
    assert t.frames[first].upper_stage.position[2]>t.frames[first].position[2]+20
    assert t.frames[first+1].upper_stage.position!=t.frames[first].upper_stage.position

def test_repeated_retargets_preserve_the_entire_previous_flight_prefix():
    plan=dict(launch=[0,0],landing=[80,40],separation_altitude=400)
    a=simulate('landing',save=False,flight_plan=plan,retargets=[dict(time=3,landing=[95,55])])
    b=simulate('landing',save=False,flight_plan=plan,retargets=[dict(time=3,landing=[95,55]),dict(time=6,landing=[70,50])])
    assert [f.model_dump() for f in a.frames if f.t<6]==[f.model_dump() for f in b.frames if f.t<6]
    assert b.run.initial_flight_plan.landing==(80,40)
    assert b.run.flight_plan.landing==(70,50) and len(b.run.retargets)==2
    assert b.run.outcome=='success' and b.run.pad_distance<=1
    with pytest.raises(ValueError,match='increasing'):
        simulate(save=False,retargets=[dict(time=6,landing=[0,0]),dict(time=3,landing=[1,1])])

def test_body_fixed_gimbal_torque_does_not_invent_roll():
    cfg=load_config();cfg['world']['density_sea_level']=0
    p=RocketPhysics(cfg);p.reset(1,position=[0,0,10020],velocity=[0,0,0])
    for _ in range(100):p.step([1,.4,-.3])
    assert abs(p.data.qvel[5])<1e-9

def test_suborbital_profile_has_distinct_vehicle_gravity_and_budget():
    from rocket_lab.missions import configure_flight
    cfg,plan=configure_flight(load_config(),dict(profile='suborbital',separation_altitude=100000),'combined')
    assert cfg['vehicle']['fuel_mass']==140000 and cfg['mission']['timeout']>=1000
    assert gravity_at(cfg['world'],100000)<gravity_at(cfg['world'],0)
    assert gravity_at(cfg['world'],100000)==pytest.approx(9.80665*(6371000/6471000)**2)
