import numpy as np
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from rocket_lab.schemas import FlightPlan,TrainRequest
from rocket_lab.missions import configure_flight
from rocket_lab.config import load_config
from rocket_lab.physics import RocketPhysics
from rocket_lab.envs import RocketEnv
from rocket_lab.simulation import simulate


@pytest.mark.parametrize('values',[{'launch':[float('nan'),0]},{'landing':[0,10001]},
                                  {'separation_altitude':79},{'separation_altitude':1501}])
def test_invalid_geometry_is_rejected(values):
    with pytest.raises(ValidationError):FlightPlan(**values)


def test_training_budget_includes_combined_and_one_hundred_million():
    request=TrainRequest(mission='combined',steps=100000000)
    assert request.mission=='combined' and request.steps==100000000
    with pytest.raises(ValidationError):TrainRequest(steps=100000001)


def test_target_is_phase_specific_and_translation_invariant():
    cfg,plan=configure_flight(load_config(),dict(launch=[600,-300],landing=[680,-260],separation_altitude=350),'combined')
    env=RocketEnv('combined',config=cfg,noise=False,randomize=False)
    obs,_=env.reset(seed=42)
    np.testing.assert_allclose(env.physics.state()['position'][:2],plan.launch)
    rest=env.physics.rest
    np.testing.assert_allclose(env._target(),[600,-300,rest+350])
    np.testing.assert_allclose(obs[:2],[0,0])
    env.phase='landing';np.testing.assert_allclose(env._target(),[680,-260,rest])
    env.close()


def test_separation_preserves_pose_velocity_time_and_drops_only_attached_mass():
    cfg=load_config();cfg['vehicle']['upper_stage_mass']=2500.
    physics=RocketPhysics(cfg);before=physics.reset(42,position=[10,20,420],velocity=[2,3,25])
    event=physics.separate();after=physics.state()
    for key in ('position','velocity','angular_velocity','quaternion'):np.testing.assert_array_equal(before[key],after[key])
    assert event['mass']==2500 and before['mass']-after['mass']==2500
    assert before['t']==after['t'] and before['fuel_mass']==after['fuel_mass']


@pytest.mark.parametrize('mission',['landing','takeoff','combined'])
def test_full_flight_to_separate_site_and_recorded_plan(mission):
    plan=dict(launch=[200,-100],landing=[240,-80],separation_altitude=300)
    replay=simulate(mission,save=False,flight_plan=plan)
    assert replay.run.outcome=='success',replay.run.model_dump()
    assert replay.run.flight_plan.launch==(200,-100)
    assert replay.run.flight_plan.landing==(240,-80)
    assert replay.run.dynamics_hash and '-src' in replay.run.id
    if mission=='combined':
        event=replay.run.separation
        assert event is not None and event.mass>0
        assert event.position[2]-20>=300
        phases=[frame.phase for frame in replay.frames]
        assert phases[0]=='takeoff' and phases[-1]=='landing'
        at=next(i for i,frame in enumerate(replay.frames) if frame.phase=='landing')
        assert replay.frames[at-1].mass-replay.frames[at].mass>=event.mass
    assert np.linalg.norm(np.array(replay.frames[-1].position[:2])-(plan['launch'] if mission=='takeoff' else plan['landing']))<=5


def test_custom_flight_is_retrievable_and_validation_runs_through_api(monkeypatch,tmp_path):
    import rocket_lab.api as api
    import rocket_lab.simulation as simulation
    import rocket_lab.storage as storage
    for module in (api,simulation,storage):monkeypatch.setattr(module,'DATA',tmp_path)
    client=TestClient(api.app)
    response=client.post('/simulate',json=dict(mission='takeoff',flight_plan=dict(launch=[500,700],landing=[1700,1100],separation_altitude=200)))
    assert response.status_code==200
    identifier=response.json()['run']['id']
    assert client.get(f'/runs/{identifier}/telemetry').json()['run']['flight_plan']['launch']==[500,700]
    assert client.post('/simulate',json={'flight_plan':{'launch':[20000,0]}}).status_code==422


def test_curriculum_moves_the_start_and_never_the_landing_site():
    from rocket_lab.campaign import campaign_config
    cfg=campaign_config('combined',dict(launch=[0,0],landing=[80,40],separation_altitude=400))
    # The takeoff goal stays a training-only shrink.
    takeoff=RocketEnv('combined',config=cfg,training=True,difficulty=0)
    flight=RocketEnv('combined',config=cfg,difficulty=0)
    takeoff.reset(seed=42);flight.reset(seed=42)
    assert takeoff.takeoff_altitude==5 and flight.takeoff_altitude==400
    takeoff.phase=flight.phase='landing'
    np.testing.assert_array_equal(takeoff._target()[:2],[80,40])
    np.testing.assert_array_equal(flight._target()[:2],[80,40])
    # The landing curriculum ramps the start position toward the real pad, so a
    # stage-trained policy still practises on the site it is evaluated against.
    easy=RocketEnv('landing',config=cfg,training=True,difficulty=0);easy.reset(seed=42)
    replay=RocketEnv('landing',config=cfg,difficulty=0);replay.reset(seed=42)
    np.testing.assert_allclose(easy.physics.state()['position'][:2],[80,40])
    np.testing.assert_allclose(replay.physics.state()['position'][:2],[80,40])
    np.testing.assert_array_equal(replay._target()[:2],[80,40])
    full=RocketEnv('landing',config=cfg,difficulty=1);full.reset(seed=42)
    assert np.linalg.norm(full.physics.state()['position'][:2])<12.1
    for env in (takeoff,flight,easy,replay,full):env.close()


def test_campaign_dispatch_uses_saved_plan_and_conflict_guard(monkeypatch,tmp_path):
    import rocket_lab.api as module
    monkeypatch.setattr(module,'DATA',tmp_path)
    monkeypatch.setattr(module,'training_jobs',lambda:[])
    commands=[]
    def launch(command,folder):commands.append(command);return 1
    monkeypatch.setattr(module,'launch_job',launch)
    client=TestClient(module.app)
    response=client.post('/campaigns',json={'steps':100000000,'flight_plan':{'launch':[10,20],'landing':[1210,420],'separation_altitude':400}})
    assert response.status_code==202
    assert commands[0][1:3]==['-m','rocket_lab.campaign'] and '100000000' in commands[0]
    assert client.post('/training',json={'steps':1000}).status_code==409
    identifier=response.json()['id']
    assert client.get('/campaigns').json()[0]['status']=='starting'
    assert client.post(f'/campaigns/{identifier}/stop').status_code==200
    assert (tmp_path/'campaigns'/identifier/'stop').exists()


def test_automatic_combined_replay_uses_the_matching_trained_combined_policy(monkeypatch):
    import rocket_lab.simulation as module
    selections=[]
    def select(mission,level,config=None):
        selections.append((mission,config['mission']['pad']))
        return {'id':'combined-test__step-000001000'}
    class Policy:
        def __init__(self,identifier,observation_config=None):
            self.meta=dict(mission='combined',algorithm='PPO',steps=1000)
        def action(self,observation):return np.array([-1.,0.,0.])
    monkeypatch.setattr(module,'select_checkpoint',select)
    monkeypatch.setattr(module,'LearnedPolicy',Policy)
    replay=module.simulate('combined','rl',save=False,flight_plan=dict(launch=[10,20],landing=[40,50],separation_altitude=400))
    assert selections==[('combined',[40.,50.,0.])]
    assert replay.run.checkpoint_id=='combined-test__step-000001000'


def test_midair_retarget_replans_and_lands_on_the_new_site():
    plan=dict(launch=[0,0],landing=[80,40],separation_altitude=400)
    replay=simulate('landing','classical',save=False,flight_plan=plan,
                    retarget=dict(time=3.,landing=[95,55]))
    assert replay.run.outcome=='success',replay.run.model_dump()
    assert len(replay.run.retargets)==1
    event=replay.run.retargets[0]
    assert event.t>=3. and event.t<3.6
    assert event.previous_landing==(80.,40.) and event.landing==(95.,55.)
    assert replay.run.flight_plan.landing==(95.,55.)
    assert np.linalg.norm(np.array(replay.frames[-1].position[:2])-[95,55])<=5.
    # The flight is a distinct, reproducible branch of the same seed.
    again=simulate('landing','classical',save=False,flight_plan=plan,
                   retarget=dict(time=3.,landing=[95,55]))
    assert again.run.id==replay.run.id
    np.testing.assert_allclose([frame.t for frame in again.frames],[frame.t for frame in replay.frames])


def test_retarget_rejects_takeoff_and_a_command_after_the_flight_ends():
    with pytest.raises(ValueError,match='takeoff'):
        simulate('takeoff','classical',save=False,retarget=dict(time=2.,landing=[10,10]))
    baseline=simulate('landing','classical',save=False)
    late=baseline.run.duration+1.
    with pytest.raises(ValueError,match='flight ends before'):
        simulate('landing','classical',save=False,retarget=dict(time=late,landing=[10,10]))
    with pytest.raises(ValueError,match='within'):
        simulate('landing','classical',save=False,retarget=dict(time=2.,landing=[10001,0]))


def test_training_retargets_are_seeded_and_absent_from_evaluation():
    cfg=load_config()
    cfg['training']['retarget_probability']=1.
    cfg['training']['retarget_min_altitude']=45.
    # A high start keeps every sampled delay (2-6 s) above the altitude gate,
    # so the test asserts the scheduling contract rather than seed luck.
    cfg['mission']['landing_altitude']=[600.,600.]
    def rollout(training):
        env=RocketEnv('landing',config=cfg,training=training,difficulty=1.)
        env.reset(seed=7)
        for _ in range(400):
            _,_,terminated,truncated,_=env.step(np.zeros(3,dtype=np.float32))
            if terminated or truncated:break
        events=list(env.retargets);env.close();return events
    first=rollout(True);second=rollout(True)
    assert len(first)==1 and first==second
    assert first[0]['landing']!=tuple(first[0]['previous_landing'])
    assert rollout(False)==[]
