import hashlib
import json
import os
import time
import uuid
import math
from pathlib import Path
from .config import DATA, ROOT, load_config

def atomic_json(path, value):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(f".{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        temp.write_text(json.dumps(value,indent=2,allow_nan=False),encoding="utf-8")
        # Windows readers/antivirus can briefly deny replacement of an open file.
        for attempt in range(12):
            try:
                os.replace(temp,path)
                return
            except PermissionError:
                if attempt==11: raise
                time.sleep(.01*(attempt+1))
    finally:
        # An interrupted/full-disk write must not leave a corrupt record in
        # place of the previous value or accumulate temporary files.
        try:temp.unlink(missing_ok=True)
        except OSError:pass

def read_json(path, fallback=None):
    try: return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError,ValueError): return fallback

def config_hash(config=None):
    if config is None or config==load_config():return hashlib.sha256((ROOT/"config.yaml").read_bytes()).hexdigest()[:16]
    return hashlib.sha256(json.dumps(config,sort_keys=True,separators=(',',':')).encode()).hexdigest()[:16]

def dynamics_hash():
    names=('physics.py','envs.py','controllers.py','simulation.py','missions.py')
    return hashlib.sha256(b''.join((ROOT/'rocket_lab'/name).read_bytes() for name in names)).hexdigest()

def runs():
    return sorted([v for p in (DATA/"runs").glob("*.meta.json") if (v:=read_json(p))],key=lambda x:(x["mission"],x["method"],x["level"]))

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

def select_checkpoint(mission,level,config=None):
    cfg=config or load_config();baseline_hash=config_hash()
    if mission=='combined':
        from .missions import configure_flight
        cfg,_=configure_flight(cfg,mission=mission)
    def compatible(item):
        recorded=item.get('config')
        return (all(recorded.get(key)==cfg.get(key) for key in ('vehicle','world','mission')) if recorded else item.get('config_hash')==baseline_hash)
    items=[x for x in checkpoints(mission) if compatible(x) and x.get("evaluation_episodes",0)>0 and x.get("steps",0)>0]
    if not items: raise ValueError(f"No trained {mission} checkpoint available. Start training first.")
    results=[value for path in (DATA/'results').glob('*.json') if (value:=read_json(path)) and value.get('mission')==mission and value.get('scenario')=='nominal']
    def evidence(item):
        allowed_hashes={baseline_hash,item.get('config_hash')}
        return max((value for value in results if value.get('checkpoint_id')==item['id'] and value.get('config_hash') in allowed_hashes and value.get('episodes',0)>=item['evaluation_episodes']),key=lambda value:value['episodes'],default=None)
    def rank(item):
        result=evidence(item)
        n=result['episodes'] if result else item['evaluation_episodes']
        k=result.get('successes',0) if result else item.get('successes',round(item.get('success_rate',0)*n))
        if not 0<=k<=n:raise ValueError('Invalid saved checkpoint success count')
        rate=k/n;z=1.95996398454;denominator=1+z*z/n
        lower=max(0.,(rate+z*z/(2*n)-z*math.sqrt(rate*(1-rate)/n+z*z/(4*n*n)))/denominator)
        # Ascent records contain speed magnitude, not target-speed error.
        error=(result['mean_touchdown_speed']/2+result['mean_tilt']/5+result['mean_pad_distance']/5) if result and mission=='landing' else 0.
        return (lower,n,rate,-error,item['steps'])
    # Raw rewards across different reward profiles are never compared.
    best=max(items,key=rank)
    sequence=sorted([x for x in items if x["job_id"]==best["job_id"] and x['steps']<=best['steps']],key=lambda x:x['steps'])
    index=round((len(sequence)-1)*(level-1)/3)
    return best if level==4 else sequence[index]
