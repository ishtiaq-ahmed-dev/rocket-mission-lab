"""Measured curriculum competence, kept separate from full-task qualification."""
import argparse
import time
from collections import Counter
import numpy as np
from .config import DATA,ROOT,load_config
from .envs import RocketEnv
from .simulation import LearnedPolicy,simulate
from .storage import atomic_json,config_hash,checkpoint_path,read_json

def publish_probes():
    summaries=[]
    for path in (DATA/"probes").glob("*.json"):
        value=read_json(path)
        if not value:continue
        try:meta=read_json(checkpoint_path(value["checkpoint_id"])/"checkpoint.json",{})
        except ValueError:meta={}
        summaries.append({key:item for key,item in value.items() if key!="stages"} | dict(
            profile=meta.get("config",{}).get("reward",{}).get("profile","unknown"),
            training_profile=meta.get("config",{}).get("training",{}).get("profile","standard curriculum"),
            algorithm=meta.get('algorithm','unknown'),
            training_config_hash=meta.get("config_hash"),
            stages=[{key:item for key,item in stage.items() if key!="rows"} for stage in value["stages"]]))
    summaries.sort(key=lambda item:item["steps"],reverse=True)
    atomic_json(ROOT/"frontend"/"public"/"model-probes.json",summaries)
    if (ROOT/"frontend"/"dist").exists():atomic_json(ROOT/"frontend"/"dist"/"model-probes.json",summaries)
    evaluations=[]
    for path in (DATA/"results").glob("*.json"):
        value=read_json(path,{})
        if not value.get("evaluation_role","").startswith("additional development"):continue
        try:meta=read_json(checkpoint_path(value["checkpoint_id"])/"checkpoint.json",{})
        except ValueError:continue
        evaluations.append(value | dict(steps=meta["steps"],algorithm=meta['algorithm'],result_file=path.name))
    for folder in (ROOT/"frontend"/"public",ROOT/"frontend"/"dist"):
        if folder.exists():atomic_json(folder/"model-evaluations.json",evaluations)
    qualifications=[]
    for path in (DATA/'results').glob('*.json'):
        value=read_json(path,{})
        if value.get('evaluation_role')!='frozen-candidate nominal qualification':continue
        qualifications.append(value|dict(result_file=path.name))
    for folder in (ROOT/'frontend'/'public',ROOT/'frontend'/'dist'):
        if folder.exists():atomic_json(folder/'model-qualifications.json',qualifications)

def export_replays(checkpoint_id):
    """Export the first fixed seed at every stage, without outcome selection."""
    path=DATA/"probes"/f"{checkpoint_id}.json";result=read_json(path)
    if not result:raise ValueError("Run the difficulty probe before exporting its replays")
    cfg=load_config()
    if result["config_hash"]!=config_hash(cfg):raise ValueError("Probe physical configuration changed")
    for stage in result["stages"]:
        seed=stage["seeds"][0]
        replay=simulate(result["mission"],"rl",4,seed,checkpoint_id,save=False,config=cfg,difficulty=stage["difficulty"])
        expected=stage["rows"][0]
        if replay.run.outcome!=expected["outcome"] or not np.allclose(
            [replay.run.touchdown_speed,replay.run.tilt,replay.run.pad_distance],
            [expected["touchdown_speed"],expected["tilt"],expected["pad_distance"]],atol=1e-6,rtol=0):
            raise ValueError("Replay no longer matches the saved probe outcome")
        replay.run.source="MuJoCo development replay; first fixed seed, no outcome selection"
        filename=f"{checkpoint_id}-d{stage['difficulty']:.3f}-s{seed}.json"
        for folder in (ROOT/"frontend"/"public",ROOT/"frontend"/"dist"):
            if folder.exists():atomic_json(folder/"model-replays"/filename,replay.model_dump())
        stage.update(replay_url=f"/model-replays/{filename}",replay_seed=seed,replay_outcome=replay.run.outcome)
    atomic_json(path,result);publish_probes()

def probe(checkpoint_id,episodes=32,difficulties=(.2,.4,.6,1.),start_seed=21000):
    cfg=load_config();policy=LearnedPolicy(checkpoint_id,observation_config=cfg)
    result=dict(checkpoint_id=checkpoint_id,mission=policy.meta["mission"],steps=policy.meta["steps"],
                config_hash=config_hash(),training_config_hash=policy.meta.get("config_hash"),created_at=time.time(),scope="development curriculum probes; not qualification",stages=[])
    for difficulty in difficulties:
        env=RocketEnv(policy.meta["mission"],config=cfg,difficulty=difficulty);rows=[]
        for seed in range(start_seed,start_seed+episodes):
            observation,_=env.reset(seed=seed)
            while True:
                observation,_,terminated,truncated,info=env.step(policy.action(observation))
                if terminated or truncated:break
            rows.append(dict(seed=seed,**info))
        stage=dict(difficulty=difficulty,episodes=episodes,seeds=[start_seed,start_seed+episodes-1],
                   successes=sum(row["outcome"]=="success" for row in rows),
                   failures=dict(Counter(row["outcome"] for row in rows if row["outcome"]!="success")),
                   mean_speed=float(np.mean([row["touchdown_speed"] for row in rows])),
                   mean_tilt=float(np.mean([row["tilt"] for row in rows])),
                   mean_offset=float(np.mean([row["pad_distance"] for row in rows])),rows=rows)
        result["stages"].append(stage);env.close()
        atomic_json(DATA/"probes"/f"{checkpoint_id}.json",result)
        publish_probes()
        print(f"{checkpoint_id} difficulty={difficulty:.2f}: {stage['successes']}/{episodes}, speed={stage['mean_speed']:.2f}, tilt={stage['mean_tilt']:.2f}, offset={stage['mean_offset']:.2f}",flush=True)
    export_replays(checkpoint_id)
    return result

if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument('checkpoint_id');parser.add_argument('--episodes',type=int,default=32)
    parser.add_argument('--replays-only',action='store_true')
    args=parser.parse_args()
    if args.replays_only:export_replays(args.checkpoint_id)
    else:probe(args.checkpoint_id,args.episodes)
