import numpy as np
from .envs import RocketEnv
from .controllers import ClassicalController
from .schemas import Frame, RunMeta, Telemetry
from .storage import atomic_json, config_hash, checkpoint_path, select_checkpoint
from .config import DATA, load_config

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

def simulate(mission="landing",method="classical",level=4,seed=42,checkpoint_id=None,save=True,config=None,difficulty=1.,training=False):
    if not 0<=difficulty<=1:raise ValueError("difficulty must be within [0,1]")
    env=RocketEnv(mission,config=config,difficulty=difficulty,training=training)
    observation,_=env.reset(seed=seed)
    controller=ClassicalController(level)
    policies={}
    if method=="rl":
        for phase in (["takeoff","landing"] if mission=="combined" else [mission]):
            selected=checkpoint_id if checkpoint_id and mission!="combined" else select_checkpoint(phase,level)["id"]
            policies[phase]=LearnedPolicy(selected,observation_config=env.cfg)
        meta=policies[env.phase].meta
        steps,algorithm=meta["steps"],meta["algorithm"]
    else: steps,algorithm=None,None
    frames=[]
    def frame(reward=None):
        s=env.physics.state()
        values={k:s[k].tolist() if isinstance(s[k],np.ndarray) else s[k] for k in Frame.model_fields if k in s}
        return Frame(**values,phase=env.phase,reward=reward)
    frames.append(frame())
    while True:
        action=controller.action(env) if method=="classical" else policies[env.phase].action(observation)
        observation,reward,terminated,truncated,info=env.step(action)
        frames.append(frame(reward if method=="rl" else None))
        if terminated or truncated: break
    tag=f"-{checkpoint_id}" if checkpoint_id else ""
    if difficulty!=1.:tag+=f"-d{difficulty:.6f}"
    if training:tag+="-practice"
    run_hash=config_hash(env.cfg)
    run_id=f"{mission}-{method}-l{level}-s{seed}{tag}-{run_hash}"
    run=RunMeta(id=run_id,mission=mission,method=method,level=level,checkpoint_steps=steps,checkpoint_id=checkpoint_id,difficulty=difficulty,algorithm=algorithm,
                training_mode=training,target_altitude=env.takeoff_altitude if mission=="takeoff" else None,
                target_velocity=env.takeoff_velocity if mission=="takeoff" else None,
                seed=seed,outcome=info["outcome"],failure_reason=info["failure_reason"],touchdown_speed=info["touchdown_speed"],
                tilt=info["tilt"],pad_distance=info["pad_distance"],fuel_used=info["fuel_used"],duration=frames[-1].t,
                total_reward=env.total_reward,controller_status=controller.plan_status if method=="classical" else "measured checkpoint; maturity not certified")
    result=Telemetry(config_hash=run_hash,rocket_length=env.cfg["vehicle"]["length"],initial_fuel=env.cfg["vehicle"]["fuel_mass"]*env.physics.mass_scale,run=run,frames=frames)
    if save:
        atomic_json(DATA/"runs"/f"{run_id}.json",result.model_dump())
        atomic_json(DATA/"runs"/f"{run_id}.meta.json",run.model_dump())
    env.close()
    return result
