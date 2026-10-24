"""Native PhysX/RTX simulation and optional SB3 training. No browser renderer."""
import argparse
import json
import os
from pathlib import Path
import sys
import time
import traceback
import faulthandler
import hashlib

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def source_manifest():
    paths=[Path(__file__),*sorted((ROOT/'rocket_lab/isaac').glob('*.py')),
        *sorted((ROOT/'config').glob('isaac-*.kit')),
        *(ROOT/'rocket_lab'/name for name in ('envs.py','controllers.py','missions.py','atmosphere.py','schemas.py'))]
    return {str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


def arguments():
    parser=argparse.ArgumentParser()
    parser.add_argument('--headless',action='store_true');parser.add_argument('--diagnostic',action='store_true')
    parser.add_argument('--renderer',choices=['real-time','path-tracing'],default='real-time')
    parser.add_argument('--flow',action='store_true');parser.add_argument('--follow-camera',action='store_true')
    parser.add_argument('--gpu-physics',action='store_true');parser.add_argument('--mission',choices=['landing','takeoff','combined'],default='combined')
    parser.add_argument('--profile',choices=['research','suborbital'],default='research');parser.add_argument('--separation-altitude',type=float,default=600.)
    parser.add_argument('--landing',type=float,nargs=2,default=[1050.,250.]);parser.add_argument('--seed',type=int,default=42)
    parser.add_argument('--launch',type=float,nargs=2,default=[0.,0.])
    parser.add_argument('--retarget-at',type=float,nargs=3,metavar=('SECONDS','EAST','NORTH'),help='One reproducible target change at simulation time')
    parser.add_argument('--checkpoint');parser.add_argument('--train-steps',type=int,default=0)
    parser.add_argument('--controller',choices=['native','legacy'],default='native')
    parser.add_argument('--qualification-runs',type=int,default=0,help='Bounded combined-flight sample; alternates nominal and retargeted flights')
    parser.add_argument('--max-seconds',type=float,default=180.);parser.add_argument('--port',type=int,default=8766)
    parser.add_argument('--time-scale',type=float,default=1.,help='Visual playback rate; physical integration timestep stays fixed')
    parser.add_argument('--start-paused',action='store_true',help='Connect the dashboard and set up cameras before advancing physics')
    parser.add_argument('--lean-headless',action='store_true',help='Use the reduced native Kit experience; qualification required on each SDK release')
    parser.add_argument('--lean-visual',action='store_true',help='Use the reduced native RTX viewport experience')
    parser.add_argument('--full-experience',action='store_true',help='Use NVIDIA full base experience for SDK troubleshooting')
    parser.add_argument('--randomized',action='store_true',help='Use seeded mass, thrust, wind and initial-state variation')
    parser.add_argument('--sensor-noise',action='store_true',help='Use the project navigation noise model')
    parser.add_argument('--physics-hz',type=int,choices=[50,100,120,240],default=120)
    parser.add_argument('--record',action='store_true',help='Encode the native viewport flight into an MP4 (visual mode)')
    parser.add_argument('--cinematic',action='store_true',help='After the flight, replay the recorded pose track into a frame-exact cinematic MP4 (visual mode)')
    parser.add_argument('--cine-fps',type=float,default=60.,help='Cinematic replay frame rate')
    parser.add_argument('--cine-preset',choices=['balanced','cinematic','pathtraced'],default='cinematic')
    parser.add_argument('--cine-size',type=int,choices=[720,1080],default=1080)
    parser.add_argument('--cine-output',type=Path,default=ROOT/'videos/rocket_mission_takeoff_detach_landing.mp4')
    parser.add_argument('--track-out',type=Path,default=None,help='Save the 120 Hz flight pose track as .npz')
    parser.add_argument('--output',type=Path,default=ROOT/'data/isaac/diagnostic.json')
    return parser.parse_args()


def settle_landing(env,publish,server=None,time_scale=1.):
    """Keep PhysX running after contact, shut down the engine, detect toppling."""
    import numpy as np
    first_contact=dict(env.last_info);start=env.physics.data.time;wall_start=time.monotonic();paused_wall=0.;steps=0;settle_trace=[]
    action=np.array([-1.,0.,0.])
    while steps<40:
        iteration_start=time.monotonic();single_step=False
        if server:
            for command in server.drain():
                kind=command['type']
                if kind=='stop':env.last_info.update(outcome='stopped',failure_reason='stopped_during_settling');publish('stopped');return first_contact
                if kind=='pause':env.physics.world.pause()
                elif kind=='resume':env.physics.world.play()
                elif kind=='step':single_step=not env.physics.world.is_playing()
                elif kind=='manual':action=np.array(command['action'])
                elif kind in ('guidance','cutoff'):action=np.array([-1.,0.,0.])
                elif kind=='retarget':env.command_landing(command['landing'])
                elif kind=='camera' and env.physics.visuals:env.physics.visuals.camera(command['mode'])
        if env.physics.world.is_stopped():env.last_info.update(outcome='stopped',failure_reason='timeline_stopped');return first_contact
        if not env.physics.world.is_playing():
            if single_step:env.physics.world.play()
            else:
                if not env.physics.headless:
                    env.physics.visuals.pause_effects(True);env.physics.world.render()
                publish('settling');time.sleep(.05);paused_wall+=time.monotonic()-iteration_start;continue
        env.physics.step(action,stop_on_impact=False);steps+=1
        state=env.physics.state()
        settle_trace.append(dict(t=state['t'],velocity=state['velocity'].tolist(),tilt=state['tilt'],clearance=state['clearance']))
        if single_step:env.physics.world.pause()
        publish('settling')
        if not env.physics.headless:time.sleep(max(0.,min(.5,wall_start+paused_wall+(env.physics.data.time-start)/time_scale-time.monotonic())))
    state=env.physics.state();speed=float(np.linalg.norm(state['velocity']))
    error=float(np.linalg.norm(state['position'][:2]-env.landing))
    stable=speed<.15 and state['tilt']<env.cfg['mission']['touchdown_tilt_deg'] and error<=env.cfg['mission']['landing_tolerance'] and state['throttle']<=1e-8
    env.last_info.update(settled=bool(stable),settle_seconds=env.physics.data.time-start,
        settled_speed=speed,settled_tilt=state['tilt'],settled_pad_distance=error,engine_off=state['throttle']<=1e-8,settle_trace=settle_trace)
    if not stable:env.last_info.update(outcome='unstable_touchdown',failure_reason='unstable_touchdown')
    publish(env.last_info['outcome'])
    return first_contact


def main():
    args=arguments();app=None;server=None;env=None
    report=dict(status='starting',started_at=time.time(),headless=args.headless,renderer=args.renderer,gpu_physics=args.gpu_physics,
        arguments={key:str(value) if isinstance(value,Path) else value for key,value in vars(args).items()},source_manifest=source_manifest())
    try:
        # Caller/installer must obtain human license acceptance. Never silently set it here.
        if os.environ.get('OMNI_KIT_ACCEPT_EULA','').lower() not in ('yes','y','1'):
            raise RuntimeError('NVIDIA license acceptance required. Use the installation wrapper after accepting the license.')
        if not .1<=args.time_scale<=10 or not 0<args.max_seconds<=3600:raise ValueError('Time scale must be 0.1..10 and mission duration 0..3600 seconds')
        from rocket_lab.isaac.stream import TelemetryServer,exchange
        # Reserve this project's port before Kit startup, so a second launcher
        # cannot start another GPU process while the first compiles shaders.
        server=TelemetryServer(args.port).start()
        from isaacsim import SimulationApp
        experience='' if args.full_experience else str(ROOT/'config/isaac-headless.kit') if args.headless else str(ROOT/'config/isaac-visual.kit')
        extension_folders=[]
        if experience:
            for folder in ('extscache','extsDeprecated'):
                extension_folders+=['--ext-folder',str(Path(os.environ['ISAAC_PATH'])/folder)]
            extension_folders+=['--ext-folder',str(ROOT/'config')]
        report['experience']=Path(experience).stem if experience else 'Isaac base'
        app=SimulationApp(dict(headless=args.headless,renderer='MinimalRendering' if args.headless else 'PathTracing' if args.renderer=='path-tracing' else 'RealTimePathTracing',
            width=1280,height=720,active_gpu=0,physics_gpu=0,multi_gpu=False,max_gpu_count=1,limit_cpu_threads=4,
            samples_per_pixel_per_frame=16,max_bounces=4,disable_viewport_updates=args.headless and not experience,
            extra_args=['--/app/window/hideUi=false','--/app/asyncRendering=false',
                        '--enable','isaacsim.core.api','--enable','isaacsim.core.prims',
                        *(['--enable','omni.flowusd'] if args.flow and not args.headless else []),*extension_folders]),experience=experience)
        from isaacsim.core.version import get_version
        report['isaac_version']=list(get_version())
        import torch
        report['torch_version']=torch.__version__;report['torch_cuda_available']=torch.cuda.is_available()
        report['rendering_enabled']=not args.headless
        faulthandler.dump_traceback_later(90,repeat=True)
        print('NATIVE: application ready; importing rocket backend',flush=True)
        # Native extension imports must come after SimulationApp initialization.
        import numpy as np
        from rocket_lab.isaac.physics import IsaacRocketPhysics
        from rocket_lab.isaac.stream import TelemetryServer,exchange
        from rocket_lab.config import load_config
        from rocket_lab.missions import configure_flight
        from rocket_lab.envs import RocketEnv
        from rocket_lab.controllers import ClassicalController
        from rocket_lab.isaac.guidance import NativeGuidance
        from rocket_lab.schemas import Frame,FlightPlan
        cfg,plan=configure_flight(load_config(),FlightPlan(launch=args.launch,landing=args.landing,separation_altitude=args.separation_altitude,profile=args.profile),args.mission)
        cfg['mission']['timeout']=args.max_seconds
        cfg['world'].update(timestep=1/args.physics_hz,control_substeps=round(args.physics_hz/10))
        cfg['vehicle'].update(separation_pusher_force=12000.,separation_pusher_seconds=.2,
            rcs_fuel_mass=40.,rcs_jet_force=500.,rcs_lever=1.8,rcs_isp=60.)
        if args.cinematic:
            # The film flies the full 600 m staging profile end to end; the
            # stock 16 t propellant load runs dry ~2 m above the pad on this
            # conservative classical descent, so the demo carries margin.
            cfg['vehicle']['fuel_mass']=24000.
        report['configuration']=cfg
        report['configuration_sha256']=hashlib.sha256(json.dumps(cfg,sort_keys=True).encode()).hexdigest()
        visuals=None
        if not args.headless:
            from rocket_lab.isaac.visuals import NativeVisuals
            visuals=NativeVisuals(args.flow,args.follow_camera)
        factory=lambda config:IsaacRocketPhysics(config,args.headless,args.gpu_physics,visuals)
        print('NATIVE: constructing PhysX environment',flush=True)
        env=RocketEnv(args.mission,config=cfg,randomize=args.randomized,noise=args.sensor_noise,physics_factory=factory,training=bool(args.train_steps))
        observation,_=env.reset(seed=args.seed)
        report['physx_gpu_dynamics_enabled']=env.physics.world.get_physics_context().is_gpu_dynamics_enabled()
        assert report['physx_gpu_dynamics_enabled']==args.gpu_physics
        print('NATIVE: environment reset complete',flush=True)
        make_controller=NativeGuidance if args.controller=='native' else lambda:ClassicalController(4)
        controller=make_controller();policy=None
        if args.checkpoint:
            from rocket_lab.isaac.policy import NativePolicy
            policy=NativePolicy(args.checkpoint,cfg)
            if policy.meta['mission']!=args.mission:raise ValueError('Checkpoint mission does not match native mission')
        count=0;cutoff=False;detach_requested=False;stop=False;manual=None;manual_roll=0.
        report.update(status='running',socket_port=server.port,engine='Isaac Sim PhysX',plan=plan.model_dump(mode='json'))
        last_heartbeat=time.monotonic()
        def publish(outcome=None):
            nonlocal count,last_heartbeat
            if time.monotonic()-last_heartbeat>15:
                last_heartbeat=time.monotonic();faulthandler.dump_traceback_later(90,repeat=True)
                print(f'NATIVE: t={env.physics.data.time:.2f} s, altitude={env.physics.position[2]-env.physics.half:.1f} m, phase={env.phase}',flush=True)
            state=env.physics.state();values={key:(value.tolist() if isinstance(value,np.ndarray) else value) for key,value in state.items() if key in Frame.model_fields}
            frame=Frame(**values,phase=env.phase)
            server.publish(dict(protocol='rocket-native-v1',engine='Isaac Sim PhysX',frame=frame.model_dump(mode='json'),
                mission=env.mission,landing=env.landing.tolist(),outcome=outcome,headless=args.headless,renderer=args.renderer,
                rcs=dict(fuel_kg=state['rcs_fuel_mass'],torque_nm=state['rcs_torque'],roll_rate_rad_s=state['roll_rate']),
                payload_attached=env.physics.attached,paused=not env.physics.world.is_playing(),time_scale=args.time_scale,steps=count,control_mode='training' if args.train_steps else 'qualification' if args.qualification_runs else 'manual' if manual is not None else 'guidance',qualification=policy.qualification if policy else 'Classical controller; native development evidence only'))
        if args.start_paused and not (args.diagnostic or args.qualification_runs or args.train_steps):env.physics.world.pause()
        publish()
        if args.qualification_runs:
            if not args.headless or args.mission!='combined' or not 1<=args.qualification_runs<=100:
                raise ValueError('Qualification requires headless combined mission and 1..100 flights')
            samples=[];suite_start=time.monotonic();suite_stop=False
            for index in range(args.qualification_runs):
                env.command_landing(args.landing);observation,_=env.reset(seed=args.seed+index)
                controller=make_controller();changed=False;terminal=truncated=False
                while env.physics.data.time<args.max_seconds and not (terminal or truncated):
                    if any(command['type']=='stop' for command in server.drain()):suite_stop=True;break
                    if index%2 and not changed and env.phase=='landing' and env.physics.data.time>=30.:
                        env.command_landing([args.landing[0]+40.,args.landing[1]-70.]);controller.on_retarget();changed=True
                    observation,_,terminal,truncated,info=env.step(controller.action(env));count+=1
                    if count%10==0:publish(info['outcome'])
                if suite_stop:env.last_info.update(outcome='stopped',failure_reason='qualification_interrupted')
                if env.last_info.get('outcome')=='success' and env.phase=='landing':settle_landing(env,publish,server)
                state=env.physics.state()
                sample=dict(seed=args.seed+index,retargeted=changed,seconds=env.physics.data.time)
                sample.update(pad_distance=float(np.linalg.norm(state['position'][:2]-env.landing)),touchdown_speed=float(np.linalg.norm(state['velocity'])))
                sample.update(env.last_info)
                sample['impact']=env.physics.impact_state
                samples.append(sample)
                print(f"QUALIFICATION: {index+1}/{args.qualification_runs} seed={sample['seed']} outcome={sample['outcome']} error={sample['pad_distance']:.4f} m speed={sample['touchdown_speed']:.4f} m/s",flush=True)
                if suite_stop or env.last_info.get('outcome')=='stopped':break
            successes=sum(item['outcome']=='success' for item in samples);n=len(samples);z=1.96;p=successes/n
            center=(p+z*z/(2*n))/(1+z*z/n);radius=z*((p*(1-p)/n+z*z/(4*n*n))**.5)/(1+z*z/n)
            report.update(status='stopped' if suite_stop or env.last_info.get('outcome')=='stopped' else 'qualification_finished',successes=successes,episodes=n,samples=samples,
                wilson_95=[center-radius,center+radius],suite_wall_seconds=time.monotonic()-suite_start,
                qualification='Development sample using a generic vehicle; not hardware validation or flight certification')
        elif args.diagnostic:
            print('NATIVE: running physics/telemetry diagnostic',flush=True)
            def capture_views():
                vehicle=visuals.capture(app,args.output.with_suffix('.png'))
                report['engine_render_artifact']=visuals.capture(app,args.output.with_name(args.output.stem+'-engine.png'),view='engine')
                return vehicle
            capture=capture_views if visuals else None
            report.update(_diagnostic(env,server,publish,exchange,capture));report['status']='passed'
            if visuals:
                env.reset(seed=args.seed)
                report['launch_render_artifact']=visuals.capture(app,args.output.with_name(args.output.stem+'-launch.png'),view='launch')
                report['landing_render_artifact']=visuals.capture(app,args.output.with_name(args.output.stem+'-landing.png'),view='landing')
        elif args.train_steps:
            if not 1<=args.train_steps<=100000000:raise ValueError('Training steps must be between 1 and 100000000')
            from stable_baselines3 import PPO
            from stable_baselines3.common.callbacks import BaseCallback
            from stable_baselines3.common.vec_env import DummyVecEnv,VecNormalize
            from rocket_lab.resources import configure_background_worker,yield_background_work
            import torch
            configure_background_worker();torch.set_num_threads(1)
            class StreamCallback(BaseCallback):
                def _on_step(self):
                    nonlocal count
                    count=self.num_timesteps
                    if count%10==0:publish()
                    if count%128==0:yield_background_work()
                    return not any(command['type']=='stop' for command in server.drain())
            vector=VecNormalize(DummyVecEnv([lambda:env]),norm_obs=True,norm_reward=True)
            rollout_steps=min(1024,max(64,((args.train_steps+63)//64)*64))
            model=PPO('MlpPolicy',vector,device='cpu',seed=args.seed,n_steps=rollout_steps,batch_size=min(256,rollout_steps),policy_kwargs=dict(net_arch=[256,256,128]),verbose=1)
            try:model.learn(args.train_steps,callback=StreamCallback())
            finally:
                folder=ROOT/'data/isaac'/f'ppo-{int(time.time())}';folder.mkdir(parents=True,exist_ok=True)
                model.save(folder/'model.zip');vector.save(folder/'normalize.pkl')
                (folder/'config.json').write_text(json.dumps(cfg,indent=2));report.update(requested_training_steps=args.train_steps,training_steps=model.num_timesteps,checkpoint=str(folder),qualification='Unqualified native PhysX study')
            report['status']='training_finished'
        else:
            recording=None
            if visuals and args.record:
                recording=visuals.start_record(args.output.with_name(args.output.stem+'-flight.mp4'))
                report['video_encoding']=str(recording)
            flight_started=time.monotonic();trace=[];scheduled_retarget=False;pause_wall=0.
            track=None
            if args.cinematic or args.track_out:
                from rocket_lab.isaac.cinematic import FlightTrack
                track=FlightTrack();env.physics.track_hook=track.capture
                print('CINEMATIC: recording the flight pose track at',round(1/cfg['world']['timestep']),'Hz',flush=True)
            while app.is_running() and env.physics.data.time<args.max_seconds and not stop:
                iteration_start=time.monotonic();single_step=False
                if args.retarget_at and not scheduled_retarget and env.physics.data.time>=args.retarget_at[0]:
                    env.command_landing(args.retarget_at[1:]);controller.on_retarget();scheduled_retarget=True
                for command in server.drain():
                    if command['type']=='stop':stop=True
                    elif command['type']=='cutoff':cutoff=True
                    elif command['type']=='retarget':env.command_landing(command['landing']);controller.on_retarget()
                    elif command['type']=='detach':detach_requested=True;cutoff=True
                    elif command['type']=='manual':manual=np.asarray(command['action']);manual_roll=command.get('roll',0.);cutoff=False
                    elif command['type']=='guidance':manual=None;cutoff=False;controller.on_retarget()
                    elif command['type']=='pause':env.physics.world.pause()
                    elif command['type']=='resume':env.physics.world.play()
                    elif command['type']=='step':single_step=not env.physics.world.is_playing()
                    elif command['type']=='camera' and visuals:visuals.camera(command['mode'])
                if stop:break
                if env.physics.world.is_stopped():stop=True;break
                if not env.physics.world.is_playing():
                    if single_step:env.physics.world.play()
                    else:
                        if not args.headless:visuals.pause_effects(True);env.physics.world.render()
                        publish();time.sleep(.05);pause_wall+=time.monotonic()-iteration_start;continue
                action=policy.action(observation) if policy else controller.action(env)
                if manual is not None:action=manual.copy();env.physics.set_roll_command(manual_roll)
                if cutoff or detach_requested:action=np.array([-1.,0.,0.])
                observation,_,terminal,truncated,info=env.step(action);count+=1
                if single_step:env.physics.world.pause()
                if detach_requested and env.physics.throttle<=1e-8 and env.physics.attached:
                    env.separation=env.physics.separate();env.phase='landing';env.separated=True;detach_requested=False;cutoff=False
                    observation=env._obs(env.physics.state());controller.on_retarget()
                publish(info['outcome'])
                if count%10==0 or terminal or truncated:
                    state=env.physics.state()
                    trace.append(dict(t=state['t'],position=state['position'].tolist(),velocity=state['velocity'].tolist(),
                        tilt=state['tilt'],throttle=state['throttle'],phase=env.phase,pad_distance=info['pad_distance']))
                if not args.headless:
                    target_wall=flight_started+pause_wall+env.physics.data.time/args.time_scale
                    time.sleep(max(0.,min(.5,target_wall-time.monotonic())))
                if terminal or truncated:
                    if info['outcome']=='success' and env.phase=='landing':settle_landing(env,publish,server,args.time_scale)
                    if env.last_info.get('outcome')=='stopped':stop=True
                    break
            if recording:
                report['video_artifact']=str(visuals.stop_record())
            elapsed=time.monotonic()-flight_started
            report.update(status='stopped' if stop else 'finished',steps=count,outcome=env.last_info.get('outcome'),
                physical_seconds=env.physics.data.time,flight_wall_seconds=elapsed,real_time_factor=env.physics.data.time/max(elapsed,1e-6),
                final_info=env.last_info,trace=trace,impact=env.physics.impact_state,release_time=env.physics.release_time,payload_released=env.physics.detached)
            report['engine_scale_estimate']=getattr(controller,'engine_scale',None)
            if track is not None:
                track.finalize(env.last_info.get('outcome'))
                report['track_samples']=int(len(track.t));report['track_seconds']=round(track.duration,3)
                if args.track_out:report['track_artifact']=str(track.save(args.track_out))
                if args.cinematic and visuals:
                    from rocket_lab.isaac.cinematic import OfflineRenderer
                    env.physics.world.pause()
                    size=(1280,720) if args.cine_size==720 else (1920,1080)
                    renderer=OfflineRenderer(visuals,env.physics.stage,preset=args.cine_preset,
                        fps=args.cine_fps,size=size)
                    print(f'CINEMATIC: offline replay of {track.duration:.1f} s flight at {args.cine_fps:.0f} fps {size[0]}x{size[1]}',flush=True)
                    report['cinematic']=renderer.render(track,args.cine_output,
                        (cfg,env.physics.half,env.physics.engine_lever),on_frame=150)
        if visuals:
            report['flow_asset']=getattr(visuals,'flow_asset',None)
            report['flow_active_blocks']=getattr(visuals,'flow_active_blocks',None)
            report['sky_asset']=getattr(visuals,'sky_asset',None)
    except BaseException:
        report.update(status='failed',error=traceback.format_exc());raise
    finally:
        faulthandler.cancel_dump_traceback_later()
        report['source_changed_during_run']=report['source_manifest']!=source_manifest()
        report['finished_at']=time.time();args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2,allow_nan=False))
        if server:server.close()
        if env:env.physics.close()
        if app:app.close(wait_for_replicator=False,exit_code=0 if report['status'] in ('passed','finished','stopped','training_finished','qualification_finished') else 1)


def _diagnostic(env,server,publish,exchange,capture=None):
    import numpy as np
    env.reset(seed=7,options={'state':dict(position=[0.,0.,250.],velocity=[0.,0.,0.],quaternion=[1.,0.,0.,0.])})
    assert env.physics.attached,'Diagnostic requires a combined vehicle with a payload'
    initial=env.physics.state();packets=0
    for index in range(15):
        env.physics.step([.1,.15,-.1]);publish();packets+=1
        if index==0:
            assert 249.8<env.physics.position[2]<250.2,'First native step snapped to an authored/stale pose'
    after=env.physics.state();assert after['t']>initial['t'] and after['fuel_mass']<initial['fuel_mass']
    assert np.linalg.norm(after['angular_velocity'])>1e-5,'Gimbal torque did not produce rotation'
    artifact=capture() if capture else None
    env.physics._sync()
    assert np.allclose(env.physics.position,after['position'],atol=1e-5),'Render capture advanced physics outside the physical clock'
    for _ in range(8):env.physics.step([-1.,0.,0.])
    assert env.physics.throttle<=1e-8
    before=env.physics.payload.get_velocities().copy();env.physics.separate();after_release=env.physics.payload.get_velocities()
    assert np.allclose(before,after_release,atol=.01),'Detachment rewrote velocity'
    assert not env.physics.stage_joint.GetJointEnabledAttr().Get()
    p0=env.physics.payload.get_world_poses()[0][0].copy()
    for _ in range(15):env.physics.step([-1.,0.,0.]);publish();packets+=1
    p1=env.physics.payload.get_world_poses()[0][0];assert np.linalg.norm(p1-p0)>0.01
    assert np.isclose(env.physics.data.time,3.8,atol=.01),'Unexpected early physical contact in the free-flight diagnostic'
    received=exchange(dict(op='status'),port=server.port)
    assert received['ok'] and received['snapshot']['frame']['upper_stage'] is not None
    assert received['snapshot']['frame']['t']>0
    import urllib.request
    with urllib.request.urlopen('http://127.0.0.1:5180/api/native/status',timeout=2) as response:
        bridged=json.load(response)
    assert bridged['connected'] and bridged['snapshot']['frame']['t']==received['snapshot']['frame']['t']
    unchanged_position=env.physics.position.copy();unchanged_velocity=env.physics.velocity.copy()
    exchange(dict(op='command',command=dict(type='retarget',landing=[25.,-10.])),port=server.port)
    command=next(server.drain());env.command_landing(command['landing']);assert np.allclose(env.landing,[25.,-10.])
    assert np.array_equal(env.physics.position,unchanged_position) and np.array_equal(env.physics.velocity,unchanged_velocity),'Target command changed physical state'
    result=dict(physics_seconds=env.physics.data.time,fuel_burned=initial['fuel_mass']-env.physics.fuel,final_position=env.physics.position.tolist(),
        payload_joint_disabled=True,payload_moved_after_release=True,telemetry_packets=packets,socket_received=True,dashboard_backend_received=True,retarget_applied=True,retarget_preserved_state=True,render_artifact=artifact,
        note='Native runtime diagnostic; visual quality and mission reliability require separate validation')
    physics=env.physics;drag=physics.v['drag_coefficient'];gust=physics.w['gust_std']
    try:
        physics.v['drag_coefficient']=0.;physics.w['gust_std']=0.
        physics.reset(11,position=[0.,0.,1000.],velocity=[0.,0.,0.],wind_scale=0.)
        g=physics.gravity()
        for _ in range(10):physics.step([-1.,0.,0.])
        # Semi-implicit PhysX integration has a bounded O(dt) position error.
        assert abs(physics.velocity[2]+g)<.01,'Vacuum drop does not match gravitational acceleration'
        expected_discrete_height=1000.-.5*g*physics.data.time*(physics.data.time+physics.w['timestep'])
        assert abs(physics.position[2]-expected_discrete_height)<.01,'Vacuum drop height does not match the native semi-implicit integrator'
        result['vacuum_drop_velocity_error']=float(abs(physics.velocity[2]+g))
        result['vacuum_drop_height_error']=float(abs(physics.position[2]-(1000.-.5*g)))
        physics.reset(11,position=[0.,0.,physics.half],velocity=[0.,0.,0.],wind_scale=0.)
        for _ in range(3):physics.step([-1.,0.,0.])
        assert physics.on_pad and abs(physics.position[2]-physics.half)<.01,'Launch restraints failed under gravity'
        for _ in range(10):physics.step([1.,0.,0.])
        assert not physics.on_pad and physics.position[2]>physics.half+.1,'Launch restraints did not release after positive thrust margin'
        result.update(analytic_free_fall_passed=True,hold_down_and_release_passed=True)
        physics.reset(11,position=[0.,0.,500.],velocity=[0.,0.,0.],wind_scale=0.)
        physics.separate();booster_mass=physics.mass;payload_mass=physics.payload_mass
        for _ in range(3):physics.step([-1.,0.,0.])
        payload_velocity=physics.payload.get_velocities()[0,:3]
        expected=physics.v['separation_pusher_force']*physics.v['separation_pusher_seconds']*(1/booster_mass+1/payload_mass)
        relative=float(payload_velocity[2]-physics.velocity[2]);assert abs(relative-expected)<.01,'Pusher relative velocity does not match its physical impulse'
        momentum=booster_mass*physics.velocity+payload_mass*payload_velocity
        expected_momentum=np.array([0.,0.,-(booster_mass+payload_mass)*physics.gravity()*physics.data.time])
        error=float(np.linalg.norm(momentum-expected_momentum));assert error<2.,'Separation pusher did not conserve system momentum'
        result.update(separation_pusher_verified=True,pusher_momentum_error_kg_m_s=error,pusher_relative_speed=relative)
        physics.reset(11,position=[0.,0.,500.],velocity=[0.,0.,0.],wind_scale=0.)
        # Establish rotation through actual engine torque, rather than injecting
        # velocities into actors that may still be completing reset callbacks.
        for _ in range(15):physics.step([.1,.2,-.1])
        for _ in range(8):physics.step([-1.,0.,0.])
        booster_mass=physics.mass-physics.payload_mass;payload_mass=physics.payload_mass
        physics.separate()
        def angular_momentum():
            from scipy.spatial.transform import Rotation
            position,quaternion=physics.payload.get_world_poses();velocity=physics.payload.get_velocities()[0]
            center=(booster_mass*physics.position+payload_mass*position[0])/(booster_mass+payload_mass)
            rotation=Rotation.from_quat([*quaternion[0,1:],quaternion[0,0]]).as_matrix()
            booster_inertia=physics.booster.get_inertias()[0].reshape(3,3)
            payload_inertia=physics.payload.get_inertias()[0].reshape(3,3)
            assert np.allclose(booster_inertia,np.diag(physics.model.body_inertia[1]),rtol=1e-5)
            return physics.rotation()@booster_inertia@physics.rotation().T@physics.omega_world+rotation@payload_inertia@rotation.T@velocity[3:]+np.cross(physics.position-center,booster_mass*physics.velocity)+np.cross(position[0]-center,payload_mass*velocity[:3])
        before_angular=angular_momentum()
        assert np.linalg.norm(before_angular)>1000.,'Torque-driven spin test did not establish rotation'
        for _ in range(3):physics.step([-1.,0.,0.])
        angular_error=float(np.linalg.norm(angular_momentum()-before_angular)/np.linalg.norm(before_angular))
        assert angular_error<.002,f'Separation pusher angular momentum error {angular_error:.6g}; before={before_angular}, after={angular_momentum()}'
        result['pusher_relative_angular_momentum_error']=angular_error
        physics.reset(19,position=[0.,0.,500.],velocity=[0.,0.,0.],wind_scale=0.)
        initial_gas=physics.rcs.fuel
        inertia_z=physics.model.body_inertia[1,2]+physics.payload.get_inertias()[0].reshape(3,3)[2,2]
        maximum=2*physics.v['rcs_lever']*physics.v['rcs_jet_force']
        physics.set_roll_command(1.)
        for _ in range(5):physics.step([-1.,0.,0.])
        expected_rate=maximum*physics.data.time/inertia_z
        actual_rate=physics.state()['roll_rate']
        assert abs(actual_rate-expected_rate)<.0001,'RCS angular impulse does not match native roll acceleration'
        expected_gas=maximum/physics.v['rcs_lever']*physics.data.time/(physics.v['rcs_isp']*9.80665)
        assert abs(initial_gas-physics.rcs.fuel-expected_gas)<1e-6,'RCS gas consumption does not match jet impulse'
        result.update(rcs_impulse_verified=True,rcs_roll_rate=actual_rate,rcs_expected_roll_rate=expected_rate,rcs_gas_used_kg=initial_gas-physics.rcs.fuel)
        physics.set_roll_command(0.)
    finally:physics.v['drag_coefficient']=drag;physics.w['gust_std']=gust
    return result


if __name__=='__main__':main()
