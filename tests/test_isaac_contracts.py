import numpy as np
from fastapi.testclient import TestClient
from rocket_lab.config import load_config
from rocket_lab.isaac.actuators import Engine,gravity_at,contact_geometry
from rocket_lab.isaac.stream import TelemetryServer,exchange
from rocket_lab.api import app


def test_native_engine_burn_torque_spool_cutoff_and_finite_action():
    import pytest
    cfg=load_config();engine=Engine(cfg['vehicle'],cfg['world']['gravity']);fuel=1000.
    for _ in range(50):
        force,torque,burn=engine.step([1,.5,-.5],.02,fuel);fuel-=burn
        assert burn>=0 and engine.throttle<=1
        assert np.allclose(torque,np.cross([0,0,-cfg['vehicle']['engine_lever']],force))
    assert fuel<1000. and force[2]>0
    for _ in range(20):engine.step([-1,0,0],.02,fuel)
    assert engine.throttle==0
    with pytest.raises(ValueError):engine.step([float('nan'),0,0],.02,fuel)


def test_native_contact_and_altitude_gravity_units():
    assert np.isclose(contact_geometry(np.array([0,0,20]),np.eye(3),20)[0],0.)
    cfg=load_config()['world'];cfg['gravity_model']='inverse_square'
    assert 0<gravity_at(cfg,100000)<cfg['gravity']


def test_real_socket_roundtrip_and_commands_are_bounded():
    import pytest
    server=TelemetryServer(0).start()
    try:
        server.publish(dict(frame=dict(t=.1),engine='Isaac Sim PhysX'))
        value=exchange(dict(op='status'),port=server.port)
        assert value['snapshot']['frame']['t']==.1 and value['sequence']==1
        assert not exchange(None,port=server.port)['ok']
        assert exchange(dict(op='command',command=dict(type='retarget',landing=[20,-30])),port=server.port)['ok']
        assert list(server.drain())==[dict(type='retarget',landing=[20,-30])]
        assert not exchange(dict(op='command',command=dict(type='retarget',landing=[20000,0])),port=server.port)['ok']
        assert exchange(dict(op='command',command=dict(type='manual',action=[.5,-.5,0])),port=server.port)['ok']
        assert next(server.drain())['action']==[.5,-.5,0]
        assert not exchange(dict(op='command',command=dict(type='manual',action=[2,0,0])),port=server.port)['ok']
        for kind in ('pause','resume','step'):
            assert exchange(dict(op='command',command=dict(type=kind)),port=server.port)['ok']
            assert next(server.drain())['type']==kind
        assert exchange(dict(op='command',command=dict(type='camera',mode='follow')),port=server.port)['ok']
        assert next(server.drain())['mode']=='follow'
        assert not exchange(dict(op='command',command=dict(type='camera',mode='unknown')),port=server.port)['ok']
        server.publish(dict(payload_attached=False,control_mode='guidance'))
        assert not exchange(dict(op='command',command=dict(type='detach')),port=server.port)['ok']
        server.publish(dict(payload_attached=True,control_mode='training'))
        assert not exchange(dict(op='command',command=dict(type='pause')),port=server.port)['ok']
        server.publish(dict(payload_attached=True,control_mode='guidance'))
        for _ in range(16):assert exchange(dict(op='command',command=dict(type='stop')),port=server.port)['ok']
        assert not exchange(dict(op='command',command=dict(type='stop')),port=server.port)['ok']
        with pytest.raises(ValueError):server.publish(dict(value=float('nan')))
    finally:server.close()


def test_dashboard_native_bridge_contract_and_origin(monkeypatch):
    import rocket_lab.isaac.api as module
    calls=[]
    def request(value):
        calls.append(value)
        return dict(ok=True,snapshot=dict(engine='Isaac Sim PhysX'),sequence=1)
    monkeypatch.setattr(module,'exchange',request)
    client=TestClient(app)
    assert client.get('/native/status').json()['connected']
    assert client.post('/native/command',json=dict(type='retarget',landing=[25,0])).status_code==200
    assert client.post('/native/command',json=dict(type='retarget',landing=[10001,0])).status_code==422
    assert client.post('/native/command',json=dict(type='execute')).status_code==422
    assert calls[-1]['command']['landing']==[25,0]


def test_shared_env_accepts_injected_native_backend_without_constructing_mujoco():
    from rocket_lab.envs import RocketEnv
    fake=object();env=RocketEnv(physics_factory=lambda config:fake)
    assert env.physics is fake and env.observation_space.shape==(21,)


def test_native_start_validates_geometry_and_does_not_accept_executable_fields(monkeypatch):
    import rocket_lab.isaac.api as module
    calls=[]
    monkeypatch.setattr(module,'start',lambda settings:calls.append(settings) or dict(state='starting_or_running'))
    client=TestClient(app)
    assert client.post('/native/start',json=dict(renderer='headless',launch=[-10,20],landing=[1200,400])).status_code==200
    assert calls[0].launch==(-10.,20.)
    assert client.post('/native/start',json=dict(separation_altitude=100000)).status_code==422
    assert client.post('/native/start',json=dict(profile='suborbital',separation_altitude=100000)).status_code==200
    assert client.post('/native/start',json=dict(landing=[10001,0])).status_code==422
    assert client.post('/native/start',json=dict(renderer='command.exe')).status_code==422
    assert client.post('/native/start',json=dict(executable='command.exe')).status_code==422


def test_native_guidance_uses_compound_inertia_without_changing_physical_engine(monkeypatch):
    from types import SimpleNamespace
    from rocket_lab.isaac.guidance import NativeGuidance
    from rocket_lab.controllers import ClassicalController
    captured=[]
    monkeypatch.setattr(ClassicalController,'action',lambda self,env:captured.append(env.physics) or np.zeros(3))
    state=dict(t=0.,mass=40500.,altitude=400.,position=np.array([0.,0.,420.]),velocity=np.zeros(3))
    inertia=np.array([[0.,0.,0.],[5100000.,5100000.,61000.]])
    physics=SimpleNamespace(v=dict(max_thrust=760000.),model=SimpleNamespace(body_inertia=inertia),
        engine_lever=17.9,attached=True,payload_mass=2500.,half=20.,rest=23.,state=lambda:state)
    controller=NativeGuidance();controller.action(SimpleNamespace(physics=physics,sensed_state=state))
    assert captured[0].model.body_inertia[1,0]>inertia[1,0]
    assert captured[0].engine_lever>physics.engine_lever
    assert physics.v['max_thrust']==760000. and physics.engine_lever==17.9
    controller.terminal_captured=True;controller.on_retarget();assert not controller.terminal_captured


def test_native_descent_reference_does_not_reuse_launch_stand_height(monkeypatch):
    from types import SimpleNamespace
    from rocket_lab.isaac.guidance import NativeGuidance
    from rocket_lab.controllers import ClassicalController
    from rocket_lab.envs import RocketEnv
    captured=[]
    monkeypatch.setattr(ClassicalController,'action',lambda self,env:captured.append(env) or np.zeros(3))
    state=dict(t=0.,mass=38000.,altitude=0.,position=np.array([1200.,400.,23.]),velocity=np.zeros(3))
    physics=SimpleNamespace(v=dict(max_thrust=760000.),model=SimpleNamespace(body_inertia=np.ones((2,3))),
        engine_lever=17.9,attached=False,half=20.,rest=23.,landing_rest=20.,state=lambda:state)
    env=SimpleNamespace(phase='landing',physics=physics,sensed_state=state,launch=np.array([0.,0.]),landing=np.array([1200.,400.]),takeoff_altitude=600.)
    NativeGuidance().action(env)
    assert captured[0].physics.rest==20. and captured[0].sensed_state['altitude']==3.
    assert physics.rest==23. and state['altitude']==0.
    assert RocketEnv._target(env)[2]==20.
    env.phase='takeoff';assert RocketEnv._target(env)[2]==623.


def test_native_engine_identifier_learns_from_motion_without_reading_true_thrust_scale():
    from types import SimpleNamespace
    from rocket_lab.isaac.guidance import NativeGuidance
    config=load_config();vehicle={**config['vehicle'],'drag_coefficient':0.}
    physics=SimpleNamespace(v=vehicle,w=config['world'],half=20.,rest=23.,rotation=lambda:np.eye(3),gravity=lambda:9.80665)
    controller=NativeGuidance();acceleration=.97*.6*vehicle['max_thrust']/40000.-9.80665
    for index in range(101):
        t=index*.1
        controller.identify(SimpleNamespace(physics=physics),dict(t=t,throttle=.6,gimbal=np.zeros(2),hold_down=False,
            clearance=100.,mass=40000.,position=np.array([0.,0.,120.]),velocity=np.array([0.,0.,acceleration*t]),wind=np.zeros(3)))
    assert abs(controller.engine_scale-.97)<.002
    assert physics.v['max_thrust']==config['vehicle']['max_thrust']


def test_native_startup_recovery_and_cancel_preserve_unrelated_shared_processes(monkeypatch):
    import rocket_lab.isaac.launcher as launcher
    from types import SimpleNamespace
    import pytest
    owned=SimpleNamespace(cmdline=lambda:[str(launcher.ROOT/'scripts/isaac_runner.py')],kill=lambda:actions.append('owned-kit'))
    shared=SimpleNamespace(cmdline=lambda:['hub.exe','--mode=shared'],kill=lambda:actions.append('shared-hub'))
    process=SimpleNamespace(create_time=lambda:123.,cmdline=lambda:['powershell.exe',str(launcher.ROOT/'scripts/run_isaac.ps1')],
        children=lambda recursive:[owned,shared],terminate=lambda:actions.append('launcher'))
    actions=[]
    monkeypatch.setattr(launcher,'_process',None);monkeypatch.setattr(launcher,'_last',dict(pid=101,born=123.))
    monkeypatch.setattr(launcher.psutil,'Process',lambda pid:process)
    monkeypatch.setattr(launcher,'atomic_json',lambda *args:None)
    monkeypatch.setattr(launcher,'exchange',lambda *args,**kwargs:dict(snapshot=None))
    assert launcher._running()
    launcher.cancel_start();assert actions==['owned-kit','launcher']
    actions.clear();monkeypatch.setattr(launcher,'exchange',lambda *args,**kwargs:dict(snapshot=dict(frame=dict(t=1))))
    with pytest.raises(ValueError,match='Stop native run'):launcher.cancel_start()
    assert actions==[]
    monkeypatch.setattr(launcher,'_last',dict(pid=101,born=124.));assert not launcher._running()


def test_roll_jets_use_bounded_finite_propellant_and_impulse():
    from rocket_lab.isaac.actuators import RollThrusters
    jets=RollThrusters(dict(rcs_fuel_mass=.1,rcs_jet_force=500.,rcs_lever=1.8,rcs_isp=60.))
    torque=jets.step(1.,1.)
    assert 0<torque<1800.
    assert np.isclose(torque/1.8,.1*60.*9.80665)
    assert jets.fuel==0 and jets.step(-1.,.1)==0
    jets.reset();assert jets.step(-1.,.001)<0
