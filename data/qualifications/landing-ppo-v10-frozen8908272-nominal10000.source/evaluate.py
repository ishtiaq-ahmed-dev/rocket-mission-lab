"""Fixed-seed evaluation, Wilson confidence interval, exportable real results."""
import argparse
from collections import Counter
import csv
import math
import copy
import hashlib
import json
import os
from pathlib import Path
import time
import numpy as np
from .envs import RocketEnv
from .controllers import ClassicalController
from .simulation import LearnedPolicy
from .storage import atomic_json, config_hash, read_json
from .config import DATA, ROOT, load_config

def wilson(k,n):
    if n==0: return [0.,1.]
    z=1.95996398454; p=k/n; denom=1+z*z/n
    center=(p+z*z/(2*n))/denom
    margin=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/denom
    return [max(0.,center-margin),min(1.,center+margin)]

def evaluate(mission="landing",level=4,episodes=10000,checkpoint_id=None,start_seed=10000,scenario="nominal",config=None,progress_id=None):
    if episodes<1:raise ValueError("episodes must be positive")
    cfg=copy.deepcopy(config or load_config())
    if scenario=="gusts": cfg["world"]["gust_std"]*=4; cfg["world"]["wind_mean"]=[12,-8,0]
    elif scenario=="noise": cfg["world"]["sensor_noise"]*=4
    elif scenario=="thrust_loss": cfg["vehicle"]["max_thrust"]*=.8
    elif scenario=="extreme_starts": cfg["mission"]["horizontal_position"]*=4; cfg["mission"]["initial_tilt_deg"]*=4
    env=RocketEnv(mission,config=cfg)
    policy=LearnedPolicy(checkpoint_id,observation_config=cfg) if checkpoint_id else None
    rows=[]
    progress_folder=None;progress_log=None;started=time.time()
    if progress_id:
        if not progress_id.replace('-','').replace('_','').isalnum():raise ValueError("Invalid evaluation ID")
        progress_folder=DATA/"evaluations"/progress_id
        progress_folder.mkdir(parents=True,exist_ok=True)
        source=hashlib.sha256(b''.join((ROOT/"rocket_lab"/name).read_bytes() for name in ["physics.py","envs.py","controllers.py","simulation.py"])).hexdigest()
        identity=dict(mission=mission,level=level,episodes=episodes,checkpoint_id=checkpoint_id,start_seed=start_seed,scenario=scenario,config=cfg,source_hash=source)
        previous=read_json(progress_folder/"identity.json")
        if previous and previous!=identity:raise ValueError("Evaluation source/config changed; use a new progress ID")
        atomic_json(progress_folder/"identity.json",identity)
        progress_log=progress_folder/"episodes.jsonl"
        if progress_log.exists():
            rows=[json.loads(line) for line in progress_log.read_text().splitlines() if line.strip()]
            if len(rows)>episodes or any(r["seed"]!=start_seed+i for i,r in enumerate(rows)):raise ValueError("Evaluation seed journal is inconsistent")
        def heartbeat(status):
            atomic_json(progress_folder/"status.json",dict(id=progress_id,mission=mission,method="rl" if checkpoint_id else "classical",level=level,scenario=scenario,checkpoint_id=checkpoint_id,status=status,completed=len(rows),total=episodes,successes=sum(r["outcome"]=="success" for r in rows),started_at=started,updated_at=time.time(),pid=os.getpid(),source_hash=source))
        heartbeat("running")
    for seed in range(start_seed+len(rows),start_seed+episodes):
        obs,_=env.reset(seed=seed)
        controller=ClassicalController(level)
        while True:
            action=policy.action(obs) if policy else controller.action(env)
            obs,_,term,trunc,info=env.step(action)
            if term or trunc: break
        rows.append({**info,"seed":seed,"reward":env.total_reward})
        if progress_log:
            with progress_log.open("a",encoding="utf-8") as journal:
                journal.write(json.dumps(rows[-1],allow_nan=False)+"\n")
            if len(rows)%25==0 or len(rows)==episodes:
                heartbeat("running")
                print(f"EVALUATION {progress_id} {len(rows)}/{episodes}",flush=True)
    k=sum(x["outcome"]=="success" for x in rows)
    result=dict(mission=mission,method="rl" if checkpoint_id else "classical",level=level,checkpoint_id=checkpoint_id,
                episodes=episodes,seeds=[start_seed,start_seed+episodes-1],scenario=scenario,successes=k,success_rate=k/episodes,
                confidence_interval=wilson(k,episodes),mean_reward=float(np.mean([x["reward"] for x in rows])),
                failures=dict(Counter(x["outcome"] for x in rows if x["outcome"]!="success")),
                config_hash=config_hash(config),
                qualification="full fixed-seed batch" if episodes>=10000 else "pilot sample; 10,000-seed gate pending")
    for metric in ["touchdown_speed","tilt","pad_distance","fuel_used"]:
        result[f"mean_{metric}"]=float(np.mean([x[metric] for x in rows]))
        result[f"median_{metric}"]=float(np.median([x[metric] for x in rows]))
    env.close()
    if progress_folder:heartbeat("completed")
    return result,rows

def save_result(result,rows):
    identifier=f"{result['mission']}-{result['method']}-l{result['level']}-{result['checkpoint_id'] or 'controller'}-{result['scenario']}"
    folder=DATA/"results"; folder.mkdir(parents=True,exist_ok=True)
    # Preserve a completed full batch when a smaller pilot for that controller
    # finishes later. Keep the pilot separately rather than overwriting evidence.
    existing_path=folder/f"{identifier}.json"
    if existing_path.exists():
        from .storage import read_json
        existing=read_json(existing_path,{})
        if existing.get("episodes",0)>result["episodes"]:
            identifier+=f"-pilot-{result['episodes']}"
    atomic_json(folder/f"{identifier}.json",result)
    with (folder/f"{identifier}.csv").open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    ci=result["confidence_interval"]
    (folder/f"{identifier}.md").write_text(f"# {identifier}\n\nObserved successes: {result['successes']}/{result['episodes']}. 95% Wilson interval: {ci[0]:.4%} to {ci[1]:.4%}.\n\n{result['qualification']}\n\nFailure modes: {result['failures']}\n",encoding="utf-8")

if __name__=="__main__":
    parser=argparse.ArgumentParser(); parser.add_argument("--mission",default="landing",choices=["landing","takeoff","combined"]); parser.add_argument("--level",type=int,default=4); parser.add_argument("--episodes",type=int,default=10000); parser.add_argument("--checkpoint"); parser.add_argument("--scenario",default="nominal",choices=["nominal","gusts","noise","thrust_loss","extreme_starts"]);parser.add_argument("--progress-id")
    args=parser.parse_args(); result,rows=evaluate(args.mission,args.level,args.episodes,args.checkpoint,scenario=args.scenario,progress_id=args.progress_id); save_result(result,rows); print(result)
