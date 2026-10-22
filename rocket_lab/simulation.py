import numpy as np
import json
import hashlib
from .envs import RocketEnv
from .controllers import ClassicalController
from .schemas import Frame, RunMeta, Telemetry, RetargetEvent, TargetUpdate
from .storage import atomic_json, config_hash, checkpoint_path, select_checkpoint,dynamics_hash
from .config import DATA, load_config
from .missions import configure_flight

class LearnedPolicy:
    def __init__(self, identifier, observation_config=None):
        from stable_baselines3 import PPO, SAC
        from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize
        from .storage import read_json
        path=checkpoint_path(identifier)
        self.meta=read_json(path/"checkpoint.json")
        self.input_config=observation_config or load_config()
        self.trained_config=self.meta.get("config") or read_json(DATA/"jobs"/self.meta["job_id"]/"config.json",{})
        cls=PPO if self.meta["algorithm"]=="PPO" else SAC
        self.norm=VecNormalize.load(path/"normalize.pkl",DummyVecEnv([lambda:RocketEnv(self.meta["mission"],config=self.trained_config or None)]))
        self.norm.training=False; self.norm.norm_reward=False
        # Inference never needs SAC's training replay buffer. Avoid allocating a
        # full 250k-transition buffer for every evaluation/replay policy load.
        self.model=cls.load(path/"model.zip",device="cpu",buffer_size=1) if cls is SAC else cls.load(path/"model.zip",device="cpu")

    def action(self, observation):
        observation=np.asarray(observation).copy()
        source=self.input_config.get("training",{});target=self.trained_config.get("training",{})
        position_ratio=np.asarray(source.get("observation_position_scale",[400]*3))/np.asarray(target.get("observation_position_scale",[400]*3))
        velocity_ratio=np.asarray(source.get("observation_velocity_scale",[50]*3))/np.asarray(target.get("observation_velocity_scale",[50]*3))
        observation[:3]*=position_ratio;observation[3:6]*=velocity_ratio;observation[15:18]*=position_ratio
        normalized=self.norm.normalize_obs(np.array([observation]))
        return self.model.predict(normalized,deterministic=True)[0][0]

def simulate(mission="landing",method="classical",level=4,seed=42,checkpoint_id=None,save=True,config=None,difficulty=1.,training=False,flight_plan=None,retarget=None,retargets=None):
    if not 0<=difficulty<=1:raise ValueError("difficulty must be within [0,1]")
    cfg,plan=configure_flight(config or load_config(),flight_plan,mission)
    initial_plan=plan.model_copy(deep=True)
    commands=[TargetUpdate.model_validate(value) for value in (retargets or [])]
    if retarget: commands.append(TargetUpdate.model_validate(retarget))
    if len(commands)>32: raise ValueError('A flight supports up to 32 target commands')
    if any(b.time<=a.time for a,b in zip(commands,commands[1:])):
        raise ValueError('Target commands must have strictly increasing times')
    if commands:
        if mission=='takeoff':raise ValueError("A takeoff flight has no landing target to retarget")
        # Diverting mid-air needs time to translate back over the surface.
        cfg['mission']['timeout']=max(cfg['mission']['timeout'],300.)
    env=RocketEnv(mission,config=cfg,difficulty=difficulty,training=training)
    observation,_=env.reset(seed=seed)
    controller=ClassicalController(level)
    policies={}
    if method=="rl":
        if mission=='combined' and not checkpoint_id:
            try:checkpoint_id=select_checkpoint('combined',level,config=env.cfg)['id']
            except ValueError:pass # legacy phase chaining remains available before a combined policy exists
        if mission=='combined' and checkpoint_id:
            policy=LearnedPolicy(checkpoint_id,observation_config=env.cfg)
            if policy.meta['mission']!='combined':
                raise ValueError('Select a combined policy, or omit the ID to use a separate checkpoint for each phase')
            policies={'takeoff':policy,'landing':policy}
        for phase in (["takeoff","landing"] if mission=="combined" else [mission]):
            if phase in policies:continue
            if checkpoint_id and mission!='combined':selected=checkpoint_id
            else:
                try:selected=select_checkpoint(phase,level,config=env.cfg)['id']
                except ValueError:selected=select_checkpoint(phase,level)['id']
            policies[phase]=LearnedPolicy(selected,observation_config=env.cfg)
            if policies[phase].meta['mission']!=phase:
                raise ValueError(f'Checkpoint mission does not match {phase}')
        if mission!='combined':checkpoint_id=selected
        meta=policies[env.phase].meta
        steps,algorithm=meta["steps"],meta["algorithm"]
    else: steps,algorithm=None,None
    frames=[]
    def frame(reward=None):
        s=env.physics.state()
        values={k:s[k].tolist() if isinstance(s[k],np.ndarray) else s[k] for k in Frame.model_fields if k in s}
        return Frame(**values,phase=env.phase,reward=reward)
    frames.append(frame())
    command_index=0
    while True:
        while command_index<len(commands) and env.physics.data.time+1e-8>=commands[command_index].time:
            command=commands[command_index]
            env.command_landing(command.landing)
            plan=plan.model_copy(update={'landing':command.landing})
            if method=="classical":controller.on_retarget()
            # Re-observe the changed goal before asking a learned actor for an
            # action. Do not sample sensor noise twice on the same time step.
            observation=observation.copy()
            scale=np.asarray(env.cfg['training'].get('observation_position_scale',[400]*3))
            observation[15:18]=(env._target()-env.sensed_state['position'])/scale
            command_index+=1
        action=controller.action(env) if method=="classical" else policies[env.phase].action(observation)
        observation,reward,terminated,truncated,info=env.step(action)
        frames.append(frame(reward if method=="rl" else None))
        if terminated or truncated: break
    if command_index<len(commands):
        env.close()
        raise ValueError(f"The flight ends before {commands[command_index].time:.1f} s, so the new target was never received")
    tag=f"-{checkpoint_id}" if checkpoint_id else ""
    if method=='rl' and mission=='combined' and not checkpoint_id:
        # The identity must include both actors; a different phase policy is a different flight.
        identities='|'.join(str(policies[p].meta.get('job_id',''))+':'+str(policies[p].meta['steps']) for p in ('takeoff','landing'))
        tag+='-phases-'+hashlib.sha256(identities.encode()).hexdigest()[:12]
    if difficulty!=1.:tag+=f"-d{difficulty:.6f}"
    if training:tag+="-practice"
    if env.retargets:tag+="-rt-"+hashlib.sha256(json.dumps(env.retargets,sort_keys=True).encode()).hexdigest()[:10]
    run_hash=config_hash(env.cfg)
    source_hash=dynamics_hash()
    run_id=f"{mission}-{method}-l{level}-s{seed}{tag}-src{source_hash[:12]}-{run_hash}"
    run=RunMeta(id=run_id,mission=mission,method=method,level=level,checkpoint_steps=steps,checkpoint_id=checkpoint_id,difficulty=difficulty,algorithm=algorithm,
                training_mode=training,target_altitude=env.takeoff_altitude if mission in ('takeoff','combined') else None,
                target_velocity=env.takeoff_velocity if mission=="takeoff" else None,
                seed=seed,outcome=info["outcome"],failure_reason=info["failure_reason"],touchdown_speed=info["touchdown_speed"],
                tilt=info["tilt"],pad_distance=info["pad_distance"],fuel_used=info["fuel_used"],duration=frames[-1].t,
                total_reward=env.total_reward,flight_plan=plan,initial_flight_plan=initial_plan,
                landing_tolerance=env.cfg['mission'].get('landing_tolerance',env.cfg['mission']['pad_radius']),
                launch_release_time=env.physics.release_time,separation=env.separation,dynamics_hash=source_hash,
                retargets=[RetargetEvent(**value) for value in env.retargets],
                controller_status=controller.plan_status if method=="classical" else "measured checkpoint; maturity not certified")
    result=Telemetry(config_hash=run_hash,rocket_length=env.cfg["vehicle"]["length"],initial_fuel=env.cfg["vehicle"]["fuel_mass"]*env.physics.mass_scale,
                     min_throttle=env.cfg['vehicle']['min_throttle'],max_thrust=env.cfg['vehicle']['max_thrust'],
                     gravity_model=env.cfg['world'].get('gravity_model','constant'),run=run,frames=frames)
    if save:
        atomic_json(DATA/"runs"/f"{run_id}.json",result.model_dump())
        atomic_json(DATA/"runs"/f"{run_id}.meta.json",run.model_dump())
    env.close()
    return result
