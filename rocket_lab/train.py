"""Reproducible PPO/SAC jobs; no expert demonstrations or classical hints."""
import argparse
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
from .config import DATA, load_config
from .envs import RocketEnv
from .storage import atomic_json, config_hash
from .evaluate import evaluate, save_result

class TrainingCallback(BaseCallback):
    def __init__(self, job_id, mission, algorithm, total, eval_episodes=12):
        super().__init__()
        self.job_id,self.mission,self.algorithm,self.total=job_id,mission,algorithm,total
        self.folder=DATA/"jobs"/job_id
        self.started=time.time(); self.last_write=0; self.recent=deque(maxlen=40)
        self.history=[]; self.curve=[]; self.completed=set(); self.eval_episodes=eval_episodes
        cfg=load_config()
        # Add quartiles to short runs so the UI can show a real checkpoint progression.
        self.milestones=sorted(set([0,total,*[x for x in cfg["training"]["checkpoints"] if x<=total],total//4,total//2,3*total//4]))
        self.difficulty=.15
        self.status="running"

    def write_status(self, error=None):
        atomic_json(self.folder/"status.json",dict(id=self.job_id,mission=self.mission,algorithm=self.algorithm,
                    status=self.status,steps=self.num_timesteps,total_steps=self.total,started_at=self.started,
                    updated_at=time.time(),elapsed_seconds=time.time()-self.started,
                    steps_per_second=self.num_timesteps/max(1,time.time()-self.started),
                    device=str(self.model.device),seed=self.model.seed,difficulty=self.difficulty,
                    episode_count=len(self.history),recent_successes=sum(self.recent),recent_episodes=len(self.recent),
                    curve=self.curve,episodes=self.history[-400:],error=error,pid=os.getpid(),config_hash=config_hash()))

    def checkpoint(self):
        steps=self.num_timesteps
        folder=DATA/"checkpoints"/self.job_id/f"step-{steps:09d}"
        folder.mkdir(parents=True,exist_ok=True)
        self.model.save(folder/"model.zip")
        self.training_env.save(folder/"normalize.pkl")
        meta=dict(job_id=self.job_id,mission=self.mission,algorithm=self.algorithm,steps=steps,
                  seed=self.model.seed,config_hash=config_hash(),difficulty=self.difficulty,
                  created_at=datetime.now(timezone.utc).isoformat(),success_rate=0,mean_reward=-1e9,
                  evaluation_episodes=0,qualification="evaluation pending")
        atomic_json(folder/"checkpoint.json",meta)
        # Separate fixed held-out seeds, full distribution with wind/noise at every checkpoint.
        identifier=f"{self.job_id}__{folder.name}"
        result,rows=evaluate(self.mission,episodes=self.eval_episodes,checkpoint_id=identifier,start_seed=10000)
        meta.update(success_rate=result["success_rate"],mean_reward=result["mean_reward"],evaluation_episodes=self.eval_episodes,
                    successes=result["successes"],confidence_interval=result["confidence_interval"],failures=result["failures"],
                    qualification=result["qualification"])
        atomic_json(folder/"checkpoint.json",meta)
        save_result(result,rows)
        self.curve.append(dict(steps=steps,reward=result["mean_reward"],success_rate=result["success_rate"],successes=result["successes"],episodes=self.eval_episodes,checkpoint_id=identifier))
        print(f"CHECKPOINT {identifier} successes={result['successes']}/{self.eval_episodes} reward={result['mean_reward']:.1f}",flush=True)
        self.write_status()

    def _on_training_start(self):
        self.checkpoint(); self.completed.add(0)

    def _on_step(self):
        for done,info in zip(self.locals.get("dones",[]),self.locals.get("infos",[])):
            if done:
                success=info.get("outcome")=="success"
                self.recent.append(success)
                ep=info.get("episode",{})
                self.history.append(dict(steps=self.num_timesteps,reward=float(ep.get("r",0)),length=int(ep.get("l",0)),outcome=info.get("outcome"),difficulty=self.difficulty))
        # Advance only after the measured rolling threshold is met.
        cfg=load_config()["training"] if self.num_timesteps%10000==0 else None
        threshold=cfg["curriculum_threshold"] if cfg else .75
        if len(self.recent)==40 and np.mean(self.recent)>=threshold and self.difficulty<1:
            self.difficulty=min(1.,self.difficulty+.15)
            self.training_env.set_attr("difficulty",self.difficulty)
            self.recent.clear()
        if any(self.num_timesteps>=x and x not in self.completed for x in self.milestones):
            for x in self.milestones:
                if self.num_timesteps>=x: self.completed.add(x)
            self.checkpoint()
        if time.time()-self.last_write>2:
            self.last_write=time.time(); self.write_status()
        return not (self.folder/"stop").exists()

def train(mission="landing",algorithm="PPO",steps=100000,seed=42,device="auto",job_id=None,eval_episodes=12):
    torch.set_num_threads(2)
    np.random.seed(seed); torch.manual_seed(seed)
    cfg=load_config()
    job_id=job_id or f"{mission}-{algorithm.lower()}-{int(time.time())}"
    folder=DATA/"jobs"/job_id; folder.mkdir(parents=True,exist_ok=True)
    vec=VecNormalize(DummyVecEnv([lambda:Monitor(RocketEnv(mission,difficulty=.15)) for _ in range(cfg["training"]["n_envs"])]),norm_obs=True,norm_reward=True,clip_obs=10)
    vec.seed(seed)
    # MLP PPO is generally CPU-bound; CUDA is useful for larger SAC updates.
    if device=="auto": device="cpu" if algorithm=="PPO" else ("cuda" if torch.cuda.is_available() else "cpu")
    common=dict(policy="MlpPolicy",env=vec,learning_rate=cfg["training"]["learning_rate"],seed=seed,device=device,
                verbose=0,tensorboard_log=str(DATA/"tensorboard"/job_id))
    if algorithm=="PPO":
        model=PPO(**common,n_steps=512,batch_size=256,n_epochs=6,gamma=.995,ent_coef=.002,policy_kwargs=dict(net_arch=[128,128],log_std_init=-1.5))
    else:
        model=SAC(**common,batch_size=256,buffer_size=250000,learning_starts=2000,train_freq=4,gradient_steps=1,gamma=.995,policy_kwargs=dict(net_arch=[128,128]))
    callback=TrainingCallback(job_id,mission,algorithm,steps,eval_episodes)
    try:
        model.learn(total_timesteps=steps,callback=callback)
        if callback.num_timesteps not in [x["steps"] for x in callback.curve]: callback.checkpoint()
        callback.status="stopped" if (folder/"stop").exists() else "completed"
        callback.write_status()
        # Export genuine level snapshots for the frontend after training.
        from .simulation import simulate
        for level in range(1,5): simulate(mission,"rl",level,42)
    except Exception:
        callback.status="failed"; callback.write_status(traceback.format_exc()); raise
    finally: vec.close()
    return job_id

if __name__=="__main__":
    parser=argparse.ArgumentParser(); parser.add_argument("--mission",default="landing",choices=["landing","takeoff"]); parser.add_argument("--algorithm",default="PPO",choices=["PPO","SAC"]); parser.add_argument("--steps",type=int,default=100000); parser.add_argument("--seed",type=int,default=42); parser.add_argument("--device",default="auto",choices=["auto","cpu","cuda"]); parser.add_argument("--job-id"); parser.add_argument("--eval-episodes",type=int,default=12)
    args=parser.parse_args(); train(args.mission,args.algorithm,args.steps,args.seed,args.device,args.job_id,args.eval_episodes)
