import json
import sys
import time
from pathlib import Path
import threading
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from .config import DATA, ROOT, load_config
from .schemas import SimRequest, TrainRequest, RunMeta, Telemetry
from .storage import runs, read_json, training_jobs, checkpoints, atomic_json, config_hash,dynamics_hash
from .simulation import simulate
from .missions import configure_flight
from .jobs import launch_job

app=FastAPI(title="Rocket Mission Lab",version="1.0.0")
app.add_middleware(CORSMiddleware,allow_origins=["http://localhost:5180","http://127.0.0.1:5180"],allow_methods=["GET","POST"],allow_headers=["Content-Type"])
job_lock=threading.Lock()

def campaign_list():
    values=[value for path in (DATA/'campaigns').glob('*/status.json') if (value:=read_json(path))]
    for value in values:
        if value['status']=='running' and value.get('active_job'):
            active=read_json(DATA/'jobs'/value['active_job']/'status.json',{})
            value['steps']+=max(0,active.get('steps',0)-active.get('initial_steps',0))
            if active.get('mission') in value['missions']:value['missions'][active['mission']]['steps']=active.get('steps',0)
            value['active_job_status']=active.get('status')
            value['updated_at']=max(value['updated_at'],active.get('updated_at',0))
    return sorted(values,key=lambda value:value['started_at'],reverse=True)

def ensure_idle():
    for campaign in campaign_list():
        if campaign['status']=='running':
            raise HTTPException(409,'A three-mission campaign is active. Stop it before starting another job.')
    for job in training_jobs():
        if job['status'] in ('running','starting') and time.time()-job['updated_at']<120:
            raise HTTPException(409,'A training job is already active. Stop it or wait for completion.')

@app.get("/health")
def health(): return {"status":"ok","physics":"MuJoCo","schema_version":"1.1"}

@app.get("/missions")
def missions():
    return [{"id":x,"name":x.title(),"description":d} for x,d in [("landing","Powered descent to your landing coordinates"),("takeoff","Liftoff to your selected altitude"),("combined","Launch, release an unpowered upper stage and return to a separate landing site")]]

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
        ensure_idle()
        job_id=f"{request.mission}-{request.algorithm.lower()}-{time.time_ns()}"
        folder=DATA/"jobs"/job_id; folder.mkdir(parents=True,exist_ok=True)
        cfg,_=configure_flight(load_config(),request.flight_plan,request.mission)
        if request.flight_plan is not None:
            cfg['training'].update(target_curriculum=True,takeoff_goal_curriculum=True,
                                   takeoff_curriculum_altitude=5.,takeoff_curriculum_velocity=3.)
        atomic_json(folder/'requested-config.json',cfg)
        atomic_json(folder/"status.json",dict(id=job_id,mission=request.mission,algorithm=request.algorithm,status="starting",steps=0,total_steps=request.steps,started_at=time.time(),updated_at=time.time(),curve=[],episodes=[],device=request.device))
        pid=launch_job([sys.executable,"-m","rocket_lab.train","--mission",request.mission,"--algorithm",request.algorithm,"--steps",str(request.steps),"--seed",str(request.seed),"--device",request.device,"--job-id",job_id,'--config',str(folder/'requested-config.json')],folder)
        return {"id":job_id,"pid":pid,"status":"starting"}

@app.get('/campaigns')
def campaigns():return campaign_list()

@app.post('/campaigns',status_code=202)
def start_campaign(request:TrainRequest):
    if request.algorithm!='PPO' or request.device=='cuda':raise HTTPException(422,'The three-mission campaign uses PPO on CPU. Use single-mission training for SAC or CUDA.')
    if request.steps<4096:raise HTTPException(422,'Campaigns need at least 4,096 environment steps')
    with job_lock:
        ensure_idle()
        identifier=f'mission-campaign-{time.time_ns()}'
        folder=DATA/'campaigns'/identifier;folder.mkdir(parents=True)
        from .schemas import FlightPlan
        atomic_json(folder/'plan.json',(request.flight_plan or FlightPlan()).model_dump(mode='json'))
        atomic_json(folder/'status.json',dict(id=identifier,status='running',budget=request.steps,steps=0,missions={},active_job=None,started_at=time.time(),updated_at=time.time()))
        block=min(1000000,max(4096,request.steps//3//4096*4096))
        pid=launch_job([sys.executable,'-m','rocket_lab.campaign','--id',identifier,'--steps',str(request.steps),'--block-steps',str(block),'--plan',str(folder/'plan.json')],folder)
        return dict(id=identifier,pid=pid,status='running')

@app.post('/campaigns/{identifier}/stop')
def stop_campaign(identifier:str):
    campaign=next((value for value in campaign_list() if value['id']==identifier),None)
    if not campaign:raise HTTPException(404,'Unknown campaign')
    (DATA/'campaigns'/identifier/'stop').touch()
    if campaign.get('active_job'):
        job_folder=DATA/'jobs'/campaign['active_job'];job_folder.mkdir(parents=True,exist_ok=True)
        (job_folder/'stop').touch()
    return dict(id=identifier,status='stop_requested')

@app.post("/training/{job_id}/stop")
def stop_training(job_id:str):
    if not any(x["id"]==job_id for x in training_jobs()): raise HTTPException(404,"Unknown job")
    (DATA/"jobs"/job_id/"stop").touch()
    return {"id":job_id,"status":"stop_requested","message":"Finishes the current callback and saves a checkpoint."}

@app.get("/system")
def system():
    return {"runtime":read_json(DATA/"runtime.json",{}),"config":load_config(),"config_hash":config_hash(),"dynamics_hash":dynamics_hash(),"research":read_json(DATA/"research.json",[])}
