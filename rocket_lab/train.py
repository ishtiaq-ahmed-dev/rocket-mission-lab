"""Reproducible PPO/SAC jobs; no expert demonstrations or classical hints."""
import argparse
import hashlib
import shutil
from collections import deque
from datetime import datetime, timezone
import os
import time
import traceback
import numpy as np
import torch
from stable_baselines3 import PPO, SAC
from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3.common.monitor import Monitor
from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize
from stable_baselines3.common.utils import FloatSchedule
from .config import DATA, ROOT, load_config
from .envs import RocketEnv
from .storage import atomic_json, config_hash, read_json, dynamics_hash
from .evaluate import evaluate, save_result
from .missions import configure_flight
from .resources import memory_headroom,memory_is_low,configure_background_worker,yield_background_work

class TrainingCallback(BaseCallback):
    def __init__(self, job_id, mission, algorithm, total, eval_episodes=12, config=None, initial_steps=0, initial_difficulty=None):
        super().__init__()
        self.job_id,self.mission,self.algorithm,self.total=job_id,mission,algorithm,total
        self.folder=DATA/"jobs"/job_id
        self.started=time.time(); self.last_write=0
        self.history=[]; self.curve=[]; self.completed=set(); self.eval_episodes=eval_episodes
        self.episode_count=0
        cfg=config or load_config()
        self.recent=deque(maxlen=cfg["training"].get("curriculum_window",40))
        self.config=cfg
        self.training_hash=config_hash(cfg)
        self.dynamics_identity=dynamics_hash()
        # Add quartiles to short runs so the UI can show a real checkpoint progression.
        # Bounded checkpoint cadence for long (up to 100M step) experiments.
        interval=cfg['training'].get('checkpoint_interval',1000000)
        self.milestones=sorted(set([0,total,*[x for x in cfg["training"]["checkpoints"] if x<=total],
            *range(initial_steps+interval,total,interval),*[initial_steps+(total-initial_steps)*k//4 for k in (1,2,3)]]))
        self.difficulty=cfg["training"].get("initial_difficulty",0.)
        self.status="running"
        self.initial_steps=initial_steps
        self.stop_reason=None
        if initial_difficulty is not None:self.difficulty=initial_difficulty
        self.completed={x for x in self.milestones if x<initial_steps}

    def write_status(self, error=None):
        atomic_json(self.folder/"status.json",dict(id=self.job_id,mission=self.mission,algorithm=self.algorithm,
                    status=self.status,steps=self.num_timesteps,initial_steps=self.initial_steps,total_steps=self.total,started_at=self.started,
                    updated_at=time.time(),elapsed_seconds=time.time()-self.started,
                    steps_per_second=(self.num_timesteps-self.initial_steps)/max(1,time.time()-self.started),
                    device=str(self.model.device),seed=self.model.seed,difficulty=self.difficulty,
                    episode_count=self.episode_count,recent_successes=sum(self.recent),recent_episodes=len(self.recent),
                    curve=self.curve,episodes=self.history[-400:],error=error or self.stop_reason,pid=os.getpid(),config_hash=self.training_hash))

    def checkpoint(self,final=False):
        if shutil.disk_usage(self.folder).free<32*1024**2:
            raise OSError('Checkpoint needs at least 32 MiB of free disk space; existing checkpoints are preserved')
        steps=self.num_timesteps
        suffix="-final" if final and any(point["steps"]==steps for point in self.curve) else ""
        folder=DATA/"checkpoints"/self.job_id/f"step-{steps:09d}{suffix}"
        folder.mkdir(parents=True,exist_ok=True)
        self.model.save(folder/"model.zip")
        self.training_env.save(folder/"normalize.pkl")
        meta=dict(job_id=self.job_id,mission=self.mission,algorithm=self.algorithm,steps=steps,
                  seed=self.model.seed,config_hash=self.training_hash,difficulty=self.difficulty,config=self.config,
                  source_hash=read_json(self.folder/"source.json",{}).get("source_hash"),dynamics_hash=self.dynamics_identity,
                  snapshot_phase="post-update final" if final else "rollout callback",
                  created_at=datetime.now(timezone.utc).isoformat(),success_rate=0,mean_reward=-1e9,
                  evaluation_episodes=0,qualification="evaluation pending")
        atomic_json(folder/"checkpoint.json",meta)
        # Separate fixed held-out seeds, full distribution with wind/noise at every checkpoint.
        identifier=f"{self.job_id}__{folder.name}"
        result,rows=evaluate(self.mission,episodes=self.eval_episodes,checkpoint_id=identifier,start_seed=20000,config=self.config)
        meta.update(success_rate=result["success_rate"],mean_reward=result["mean_reward"],evaluation_episodes=self.eval_episodes,
                    successes=result["successes"],confidence_interval=result["confidence_interval"],failures=result["failures"],
                    qualification=result["qualification"])
        atomic_json(folder/"checkpoint.json",meta)
        save_result(result,rows)
        self.curve.append(dict(steps=steps,reward=result["mean_reward"],success_rate=result["success_rate"],successes=result["successes"],episodes=self.eval_episodes,checkpoint_id=identifier))
        print(f"CHECKPOINT {identifier} successes={result['successes']}/{self.eval_episodes} reward={result['mean_reward']:.1f}",flush=True)
        self.write_status()

    def _on_training_start(self):
        self.training_env.env_method("set_difficulty",self.difficulty)
        self.checkpoint(); self.completed.add(self.num_timesteps)

    def _on_step(self):
        if self.num_timesteps%128==0:yield_background_work()
        if time.time()-self.last_write>5 and dynamics_hash()!=self.dynamics_identity:
            raise RuntimeError('Flight dynamics changed during training. Start a newly identified job; existing checkpoints are preserved.')
        if time.time()-self.last_write>5 and memory_is_low(memory_headroom()):
            self.status='waiting_for_memory'
            while memory_is_low(memory_headroom()):
                self.write_status(error='Waiting for host memory: at least 2 GiB physical and 4 GiB commit headroom are required. The optimizer remains in memory; Stop still requests a saved checkpoint.')
                if (self.folder/'stop').exists():return False
                time.sleep(2)
            self.status='running'
        for done,info in zip(self.locals.get("dones",[]),self.locals.get("infos",[])):
            if done:
                self.episode_count+=1
                success=info.get("outcome")=="success"
                # Full-start mixture episodes are logged, but stage advancement
                # measures the current/easier practice distribution only.
                episode_difficulty=info.get("episode_difficulty",self.difficulty)
                if episode_difficulty<=self.difficulty+1e-8:self.recent.append(success)
                ep=info.get("episode",{})
                self.history.append(dict(steps=self.num_timesteps,reward=float(ep.get("r",0)),length=int(ep.get("l",0)),outcome=info.get("outcome"),difficulty=episode_difficulty))
                self.history=self.history[-400:]
        # Advance only after the measured rolling threshold is met.
        threshold=self.config["training"]["curriculum_threshold"]
        if len(self.recent)==self.recent.maxlen and np.mean(self.recent)>=threshold and self.difficulty<1:
            self.difficulty=min(1.,self.difficulty+self.config["training"].get("curriculum_increment",.15))
            # env_method traverses Monitor wrappers; set_attr would only shadow
            # an attribute on the wrapper and leave the real environment easy.
            self.training_env.env_method("set_difficulty",self.difficulty)
            self.recent.clear()
        if any(self.num_timesteps>=x and x not in self.completed for x in self.milestones):
            for x in self.milestones:
                if self.num_timesteps>=x: self.completed.add(x)
            self.checkpoint()
        if time.time()-self.last_write>5:
            if shutil.disk_usage(self.folder).free<64*1024**2:
                self.stop_reason='Stopped before disk exhaustion: less than 64 MiB free. Final checkpoint requested; free space before continuing.'
                (self.folder/'stop').touch()
                self.write_status()
                return False
            self.last_write=time.time(); self.write_status()
        return not (self.folder/"stop").exists()

def warm_start_actor(model,identifier,mission,cfg):
    """Transfer only this project's learned PPO actor, with explicit lineage."""
    from .storage import checkpoint_path,read_json
    checkpoint=checkpoint_path(identifier);meta=read_json(checkpoint/"checkpoint.json")
    if meta["mission"]!=mission or meta["algorithm"]!="PPO":raise ValueError("Warm start requires a matching PPO mission")
    old=meta.get("config") or read_json(DATA/"jobs"/meta["job_id"]/"config.json",{})
    for section in ("vehicle","world","mission"):
        if old.get(section)!=cfg[section]:raise ValueError("Warm start cannot change physics or mission")
    for key in ("observation_position_scale","observation_velocity_scale","observation_normalization"):
        if old.get("training",{}).get(key)!=cfg["training"].get(key):raise ValueError("Warm start requires unchanged observation scaling")
    if cfg["training"].get("observation_normalization",True):raise ValueError("Actor-only transfer requires fixed physical observation scaling")
    parent=PPO.load(checkpoint/"model.zip",device="cpu")
    state=model.policy.state_dict()
    transferred={key:value for key,value in parent.policy.state_dict().items() if key.startswith(("mlp_extractor.policy_net.","action_net.")) or key=="log_std"}
    state.update(transferred);model.policy.load_state_dict(state)
    return meta

def configure_warm_start_exploration(model,cfg):
    """Optional per-action std reset; deterministic actor outputs are unchanged."""
    overrides=cfg["training"].get("warm_start_action_std")
    if overrides is None:return None
    if len(overrides)!=model.action_space.shape[0] or any(value is not None and (not np.isfinite(value) or value<=0) for value in overrides):
        raise ValueError("warm_start_action_std requires one positive finite value or null per action")
    with torch.no_grad():
        for axis,value in enumerate(overrides):
            if value is not None:model.policy.log_std[axis]=np.log(value)
    return overrides

def validate_optimizer_adaptation(previous,current):
    """Keep the learned value function meaningful: only optimizer controls vary."""
    if {key:value for key,value in previous.items() if key!='training'}!={key:value for key,value in current.items() if key!='training'}:
        raise ValueError('Optimizer adaptation requires unchanged physics, mission and reward')
    allowed={'profile','learning_rate','ppo_target_kl'}
    old={key:value for key,value in previous['training'].items() if key not in allowed}
    new={key:value for key,value in current['training'].items() if key not in allowed}
    if old!=new:raise ValueError('Optimizer adaptation permits only learning_rate, ppo_target_kl and profile changes')

def train(mission="landing",algorithm="PPO",steps=100000,seed=42,device="auto",job_id=None,eval_episodes=12,resume=None,warm_start=None,config_path=None,adapt_optimizer_from=None):
    if sum(bool(value) for value in (resume,warm_start,adapt_optimizer_from))>1:raise ValueError("Choose exact-config continuation, actor warm start, or optimizer adaptation")
    if adapt_optimizer_from and algorithm!='PPO':raise ValueError('Optimizer adaptation requires PPO')
    if warm_start and algorithm!="PPO":raise ValueError("Actor warm start is implemented for PPO only")
    resource_policy=configure_background_worker()
    torch.set_num_threads(1)
    np.random.seed(seed); torch.manual_seed(seed)
    cfg=load_config(config_path) if config_path else load_config()
    cfg,_=configure_flight(cfg,mission=mission)
    warm_difficulty=cfg["training"].get("warm_start_difficulty")
    if warm_difficulty is not None and not 0<=warm_difficulty<=1:raise ValueError("warm_start_difficulty must be within [0,1]")
    job_id=job_id or f"{mission}-{algorithm.lower()}-{int(time.time())}"
    folder=DATA/"jobs"/job_id; folder.mkdir(parents=True,exist_ok=True)
    atomic_json(folder/'resource-policy.json',resource_policy)
    atomic_json(folder/"config.json",cfg)
    source_folder=folder/"source";source_folder.mkdir(exist_ok=True)
    source_names=["physics.py","envs.py","train.py","simulation.py","controllers.py","storage.py","config.py","evaluate.py","schemas.py","policies.py","missions.py","atmosphere.py","resources.py"]
    source_hash=hashlib.sha256()
    for name in source_names:
        source=ROOT/"rocket_lab"/name;source_hash.update(source.read_bytes());shutil.copyfile(source,source_folder/name)
    atomic_json(folder/"source.json",dict(source_hash=source_hash.hexdigest(),files=source_names))
    vec=VecNormalize(DummyVecEnv([lambda:Monitor(RocketEnv(mission,config=cfg,difficulty=cfg["training"].get("initial_difficulty",0.),training=True)) for _ in range(cfg["training"]["n_envs"])]),norm_obs=cfg["training"].get("observation_normalization",True),norm_reward=cfg["training"].get("reward_normalization",True),clip_obs=10)
    vec.seed(seed)
    # MLP PPO is generally CPU-bound; CUDA is useful for larger SAC updates.
    if device=="auto": device="cpu" if algorithm=="PPO" else ("cuda" if torch.cuda.is_available() else "cpu")
    common=dict(policy="MlpPolicy",env=vec,learning_rate=cfg["training"]["learning_rate"],seed=seed,device=device,
                verbose=0,tensorboard_log=str(DATA/"tensorboard"/job_id))
    initial_steps=0;initial_difficulty=None
    if resume or adapt_optimizer_from:
        from .storage import checkpoint_path,read_json
        identifier=resume or adapt_optimizer_from
        checkpoint=checkpoint_path(identifier);meta=read_json(checkpoint/"checkpoint.json")
        if meta["mission"]!=mission or meta["algorithm"]!=algorithm:raise ValueError("Resume mission and algorithm must match checkpoint")
        if adapt_optimizer_from:
            previous=meta.get('config') or read_json(DATA/'jobs'/meta['job_id']/'config.json',{})
            validate_optimizer_adaptation(previous,cfg)
        elif meta.get("config_hash")!=config_hash(cfg):raise ValueError("Configuration changed; resume requires the exact recorded configuration")
        if algorithm!="PPO":raise ValueError("SAC training resume requires replay-buffer persistence; start a new SAC run instead")
        vec=VecNormalize.load(checkpoint/"normalize.pkl",vec.venv)
        vec.training=True;vec.seed(seed)
        model=PPO.load(checkpoint/"model.zip",env=vec,device=device)
        model.seed=seed
        model.set_random_seed(seed)
        model.tensorboard_log=str(DATA/"tensorboard"/job_id)
        initial_steps=model.num_timesteps;initial_difficulty=meta.get("difficulty",0.)
        if adapt_optimizer_from:
            model.learning_rate=float(cfg['training']['learning_rate']);model.lr_schedule=FloatSchedule(model.learning_rate)
            model.target_kl=cfg['training'].get('ppo_target_kl')
            for group in model.policy.optimizer.param_groups:group['lr']=model.learning_rate
            atomic_json(folder/'adaptation.json',dict(parent_checkpoint=identifier,parent_steps=initial_steps,additional_steps=steps,
                parent_config_hash=meta['config_hash'],new_config_hash=config_hash(cfg),preserved='actor, critic, optimizer moments and normalization',
                changed=['learning_rate','ppo_target_kl','profile'],deterministic_action_function_changed=False))
        else:atomic_json(folder/"resume.json",dict(parent_checkpoint=resume,parent_steps=initial_steps,additional_steps=steps))
    elif algorithm=="PPO":
        settings=cfg["training"]
        if settings.get("bounded_action_mean",False):
            from .policies import BoundedMeanPolicy
            common["policy"]=BoundedMeanPolicy
        architecture=settings.get('policy_architecture',[128,128])
        if not architecture or len(architecture)>6 or any(type(width) is not int or not 16<=width<=1024 for width in architecture):
            raise ValueError('policy_architecture requires 1 to 6 integer widths between 16 and 1024')
        model=PPO(**common,n_steps=settings.get("ppo_n_steps",512),batch_size=settings.get("ppo_batch_size",256),n_epochs=settings.get("ppo_epochs",8),gamma=settings.get("ppo_gamma",.995),gae_lambda=settings.get("ppo_gae_lambda",.95),ent_coef=settings.get("ppo_entropy",.0005),target_kl=settings.get("ppo_target_kl"),policy_kwargs=dict(net_arch=architecture,log_std_init=settings.get("policy_log_std",-1.5)))
        if warm_start:
            meta=warm_start_actor(model,warm_start,mission,cfg)
            exploration=configure_warm_start_exploration(model,cfg)
            initial_steps=int(meta["steps"]);initial_difficulty=float(warm_difficulty if warm_difficulty is not None else meta.get("difficulty",0.));model.num_timesteps=initial_steps
            parent_bounded=meta.get("config",{}).get("training",{}).get("bounded_action_mean",False)
            bounded=cfg["training"].get("bounded_action_mean",False)
            atomic_json(folder/"warm-start.json",dict(parent_checkpoint=warm_start,parent_steps=initial_steps,parent_config_hash=meta.get("config_hash"),new_config_hash=config_hash(cfg),additional_steps=steps,transferred="learned actor weights only",critic="fresh",optimizer="fresh",reward_normalization="fresh",action_mean_transform="tanh" if bounded else "linear",actor_function_changed=parent_bounded!=bounded or exploration is not None,deterministic_action_function_changed=parent_bounded!=bounded,exploration_std_override=exploration,initial_difficulty=initial_difficulty))
    else:
        settings=cfg["training"]
        model=SAC(**common,batch_size=settings.get("sac_batch_size",256),buffer_size=settings.get("sac_buffer_size",250000),learning_starts=settings.get("sac_learning_starts",2000),train_freq=settings.get("sac_train_freq",4),gradient_steps=settings.get("sac_gradient_steps",1),gamma=settings.get("sac_gamma",.995),policy_kwargs=dict(net_arch=[128,128]))
    callback=TrainingCallback(job_id,mission,algorithm,initial_steps+steps,eval_episodes,cfg,initial_steps,initial_difficulty)
    try:
        model.learn(total_timesteps=steps,callback=callback,reset_num_timesteps=not(resume or warm_start or adapt_optimizer_from))
        # An on-step checkpoint can precede the rollout's last optimization.
        # Keep a distinct final snapshot so an exact-budget run saves that update.
        callback.checkpoint(final=True)
        callback.status="stopped" if (folder/"stop").exists() else "completed"
        callback.write_status()
        # Export genuine level snapshots for the frontend after training.
        from .simulation import simulate
        from .storage import checkpoints
        candidates=[item for item in checkpoints(mission) if item["job_id"]==job_id and item.get("evaluation_episodes",0)>0]
        if candidates:
            best=max(candidates,key=lambda item:(item.get("success_rate",0),item.get("mean_reward",-1e9)))
            for level in range(1,5):
                chosen=best if level==4 else candidates[round((len(candidates)-1)*(level-1)/3)]
                simulate(mission,"rl",level,42,checkpoint_id=chosen["id"],config=cfg)
    except Exception:
        callback.status="failed"; callback.write_status(traceback.format_exc()); raise
    finally: vec.close()
    return job_id

if __name__=="__main__":
    parser=argparse.ArgumentParser(); parser.add_argument("--mission",default="landing",choices=["landing","takeoff","combined"]); parser.add_argument("--algorithm",default="PPO",choices=["PPO","SAC"]); parser.add_argument("--steps",type=int,default=100000); parser.add_argument("--seed",type=int,default=42); parser.add_argument("--device",default="auto",choices=["auto","cpu","cuda"]); parser.add_argument("--job-id"); parser.add_argument("--eval-episodes",type=int,default=12);parser.add_argument("--resume")
    parser.add_argument("--warm-start");parser.add_argument("--config");parser.add_argument('--adapt-optimizer-from');args=parser.parse_args()
    try:
        train(args.mission,args.algorithm,args.steps,args.seed,args.device,args.job_id,args.eval_episodes,args.resume,args.warm_start,args.config,args.adapt_optimizer_from)
    except BaseException:
        if args.job_id:
            from .storage import read_json
            path=DATA/"jobs"/args.job_id/"status.json"
            status=read_json(path,{"id":args.job_id,"mission":args.mission,"algorithm":args.algorithm,"steps":0,"total_steps":args.steps,"started_at":time.time(),"curve":[],"episodes":[],"device":args.device})
            status.update(status="failed",error=traceback.format_exc(),updated_at=time.time())
            atomic_json(path,status)
        raise
