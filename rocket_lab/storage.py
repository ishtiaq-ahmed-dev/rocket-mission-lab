import hashlib
import json
import os
import time
import uuid
from pathlib import Path
from .config import DATA, ROOT

def atomic_json(path, value):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(f".{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp")
    temp.write_text(json.dumps(value,indent=2,allow_nan=False),encoding="utf-8")
    # Windows readers/antivirus can briefly deny replacement of an open file.
    for attempt in range(12):
        try:
            os.replace(temp,path)
            return
        except PermissionError:
            if attempt==11: raise
            time.sleep(.01*(attempt+1))

def read_json(path, fallback=None):
    try: return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError,ValueError): return fallback

def config_hash(): return hashlib.sha256((ROOT/"config.yaml").read_bytes()).hexdigest()[:16]

def runs():
    current=config_hash()
    return sorted([v for p in (DATA/"runs").glob("*.meta.json") if (v:=read_json(p)) and v["id"].endswith(current)],key=lambda x:(x["mission"],x["method"],x["level"]))

def training_jobs():
    jobs=[v for p in (DATA/"jobs").glob("*/status.json") if (v:=read_json(p))]
    for job in jobs:
        if job.get("status") in ("running","starting") and time.time()-job.get("updated_at",0)>120:
            job["status"]="stale"
            job["error"]=job.get("error") or "Heartbeat is older than two minutes. Inspect output.log before restarting."
    return sorted(jobs,key=lambda x:x.get("started_at",0),reverse=True)

def checkpoints(mission=None):
    entries=[]
    for p in (DATA/"checkpoints").glob("*/*/checkpoint.json"):
        value=read_json(p)
        if value and (mission is None or value["mission"]==mission) and (p.parent/"model.zip").exists():
            value["id"]=p.parent.parent.name+"__"+p.parent.name
            entries.append(value)
    return sorted(entries,key=lambda x:x["steps"])

def checkpoint_path(identifier):
    # IDs come from the index; never accept arbitrary filesystem paths.
    for item in checkpoints():
        if item["id"]==identifier:
            job,folder=identifier.split("__",1)
            return DATA/"checkpoints"/job/folder
    raise ValueError("Unknown checkpoint")

def select_checkpoint(mission,level):
    items=[x for x in checkpoints(mission) if x.get("config_hash")==config_hash() and x.get("evaluation_episodes",0)>0 and x.get("steps",0)>0]
    if not items: raise ValueError(f"No trained {mission} checkpoint available. Start training first.")
    # Rank algorithms by measured full-distribution evaluation; no invented maturity.
    best=max(items,key=lambda x:(x.get("success_rate",0),x.get("mean_reward",-1e9)))
    sequence=[x for x in items if x["job_id"]==best["job_id"]]
    index=round((len(sequence)-1)*(level-1)/3)
    return best if level==4 else sequence[index]
