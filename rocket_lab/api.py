import json
import subprocess
import sys
import time
from pathlib import Path
import threading
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from .config import DATA, ROOT, load_config
from .schemas import SimRequest, TrainRequest, RunMeta, Telemetry
from .storage import runs, read_json, training_jobs, checkpoints, atomic_json
from .simulation import simulate

app=FastAPI(title="Rocket Mission Lab",version="1.0.0")
app.add_middleware(CORSMiddleware,allow_origins=["http://localhost:5180","http://127.0.0.1:5180"],allow_methods=["GET","POST"],allow_headers=["Content-Type"])
job_lock=threading.Lock()

@app.get("/health")
def health(): return {"status":"ok","physics":"MuJoCo","schema_version":"1.1"}

@app.get("/missions")
def missions():
    return [{"id":x,"name":x.title(),"description":d} for x,d in [("landing","Controlled powered descent onto a static pad"),("takeoff","Liftoff to 400 m separation; not orbit"),("combined","Takeoff, phase separation and return landing")]]

@app.get("/runs",response_model=list[RunMeta])
def list_runs(mission:str|None=None,method:str|None=None,level:int|None=None,seed:int|None=None):
    return [r for r in runs() if all(v is None or r[k]==v for k,v in dict(mission=mission,method=method,level=level,seed=seed).items())]

@app.get("/runs/{run_id}/telemetry",response_model=Telemetry)
def telemetry(run_id:str):
    if not any(r["id"]==run_id for r in runs()): raise HTTPException(404,"Run not found")
    value=read_json(DATA/"runs"/f"{run_id}.json")
    if not value: raise HTTPException(404,"Telemetry not found")
    return value

@app.post("/simulate",response_model=Telemetry)
def new_simulation(request:SimRequest):
    try: return simulate(**request.model_dump())
    except ValueError as ex: raise HTTPException(409,str(ex)) from ex

@app.get("/results/summary")
def results():
    return [r for p in (DATA/"results").glob("*.json") if (r:=read_json(p))]

@app.get("/results/failures")
def failures(): return [{"mission":r["mission"],"method":r["method"],"level":r["level"],"scenario":r["scenario"],"episodes":r["episodes"],"failures":r["failures"]} for r in results()]

@app.get("/schema/telemetry")
def schema(): return Telemetry.model_json_schema()

@app.get("/training")
def training(): return training_jobs()

@app.get("/checkpoints")
def checkpoint_list(mission:str|None=None): return checkpoints(mission)

@app.post("/training",status_code=202)
def start_training(request:TrainRequest):
    with job_lock:
        for job in training_jobs():
            if job["status"] in ("running","starting") and time.time()-job["updated_at"]<120:
                raise HTTPException(409,"A training job is already active. Stop it or wait for completion.")
        job_id=f"{request.mission}-{request.algorithm.lower()}-{time.time_ns()}"
        folder=DATA/"jobs"/job_id; folder.mkdir(parents=True,exist_ok=True)
        atomic_json(folder/"status.json",dict(id=job_id,mission=request.mission,algorithm=request.algorithm,status="starting",steps=0,total_steps=request.steps,started_at=time.time(),updated_at=time.time(),curve=[],episodes=[],device=request.device))
        with (folder/"output.log").open("w") as log:
            process=subprocess.Popen([sys.executable,"-m","rocket_lab.train","--mission",request.mission,"--algorithm",request.algorithm,"--steps",str(request.steps),"--seed",str(request.seed),"--device",request.device,"--job-id",job_id],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=="win32" else 0)
        return {"id":job_id,"pid":process.pid,"status":"starting"}

@app.post("/training/{job_id}/stop")
def stop_training(job_id:str):
    if not any(x["id"]==job_id for x in training_jobs()): raise HTTPException(404,"Unknown job")
    (DATA/"jobs"/job_id/"stop").touch()
    return {"id":job_id,"status":"stop_requested","message":"Finishes the current callback and saves a checkpoint."}

@app.get("/system")
def system():
    return {"runtime":read_json(DATA/"runtime.json",{}),"config":load_config(),"research":read_json(DATA/"research.json",[])}
