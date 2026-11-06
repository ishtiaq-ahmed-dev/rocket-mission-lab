import sys
import time
import threading
import math
from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from typing import Literal
from .config import DATA, load_config
from .schemas import SimRequest, TrainRequest, RunMeta, Telemetry
from .storage import runs, read_json, training_jobs, checkpoints, atomic_json, config_hash,dynamics_hash,select_checkpoint
from .simulation import simulate
from .missions import configure_flight
from .jobs import launch_job
from .isaac.api import router as native_router

app=FastAPI(title="Rocket Mission Lab",version="1.0.0")
app.include_router(native_router)
app.add_middleware(GZipMiddleware,minimum_size=2048,compresslevel=3)
LOCAL_ORIGINS=["http://localhost:5180","http://127.0.0.1:5180"]
app.add_middleware(CORSMiddleware,allow_origins=LOCAL_ORIGINS,allow_methods=["GET","POST"],allow_headers=["Content-Type"])
job_lock=threading.Lock()
LOADED_DYNAMICS_HASH=dynamics_hash()

@app.middleware('http')
async def guard_browser_mutations(request:Request, call_next):
    if request.method not in ('GET','HEAD','OPTIONS'):
        origin=request.headers.get('origin')
        same_origin=f'{request.url.scheme}://{request.url.netloc}'
        if ((origin is not None and origin not in (*LOCAL_ORIGINS,same_origin)) or
                (origin is None and request.headers.get('sec-fetch-site')=='cross-site')):
            return JSONResponse(status_code=403,content={'detail':'Untrusted browser origin'})
    return await call_next(request)

@app.exception_handler(RequestValidationError)
async def request_validation_error(request:Request, error:RequestValidationError):
    detail=jsonable_encoder(error.errors(),custom_encoder={float:lambda value:value if math.isfinite(value) else str(value)})
    return JSONResponse(status_code=422,content={'detail':detail})

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
        if campaign['status'] in ('running','starting'):
            raise HTTPException(409,'A three-mission campaign is active. Stop it before starting another job.')
    for job in training_jobs():
        if job['status'] in ('running','starting','waiting_for_memory') and time.time()-job['updated_at']<120:
            raise HTTPException(409,'A training job is already active. Stop it or wait for completion.')

@app.get("/health")
def health(): return {"status":"ok","physics":"MuJoCo","native_physics":"Isaac Sim PhysX (separate runner)","default_workspace":"native","schema_version":"1.1"}

@app.get('/dashboard')
def dashboard_snapshot(view:Literal['flight','training','results']='flight'):
    from .dashboard import dashboard
    return dashboard(view)

@app.get('/training/{job_id}')
def training_detail(job_id:str):
    if not job_id.replace('-','').replace('_','').isalnum():raise HTTPException(404,'Unknown job')
    value=read_json(DATA/'jobs'/job_id/'status.json')
    if not value:raise HTTPException(404,'Unknown job')
    config=read_json(DATA/'jobs'/job_id/'config.json')
    if config:value['config']=config
    return value

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
    if dynamics_hash()!=LOADED_DYNAMICS_HASH:
        raise HTTPException(409,'Flight dynamics changed on disk. Restart the local engine before simulating the new revision.')
    try:
        values=request.model_dump()
        if request.method=='rl' and not request.checkpoint_id:
            cfg,_=configure_flight(load_config(),request.flight_plan,request.mission)
            selected=select_checkpoint(request.mission,request.level,config=cfg)
            if selected.get('dynamics_hash')!=LOADED_DYNAMICS_HASH:
                raise ValueError('No measured checkpoint for the loaded dynamics and flight plan. Train this revision or explicitly select an archived experimental model.')
            values['checkpoint_id']=selected['id']
            # A policy trained on a curriculum stage is flown on that stage.
            # Asking it for the full-envelope mission is a different, harder
            # flight; the run records and displays the stage it actually flew.
            stage=selected.get('difficulty')
            if stage is not None and 0<stage<1: values['difficulty']=float(stage)
        return simulate(**values)
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
            # The difficulty ramp now moves the start along the flight path and
            # leaves the landing site fixed, so the mission never changes
            # meaning between practice and evaluation.
            cfg['training'].update(takeoff_goal_curriculum=True,
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
        atomic_json(folder/'status.json',dict(id=identifier,status='starting',budget=request.steps,seed=request.seed,steps=0,missions={},active_job=None,started_at=time.time(),updated_at=time.time()))
        block=min(1000000,max(4096,request.steps//3//4096*4096))
        pid=launch_job([sys.executable,'-m','rocket_lab.campaign','--id',identifier,'--steps',str(request.steps),'--seed',str(request.seed),'--block-steps',str(block),'--plan',str(folder/'plan.json')],folder)
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
    base=load_config()
    # A checkpoint records the mission's effective configuration, which is not
    # always the raw config.yaml file: combined adds the unpowered upper stage.
    # Expose the hash each mission would actually record so a client can tell a
    # current-configuration policy from an archived one.
    configured={mission:config_hash(configure_flight(base,None,mission)[0]) for mission in ('landing','takeoff','combined')}
    return {"runtime":read_json(DATA/"runtime.json",{}),"config":base,"config_hash":config_hash(),"config_hashes":configured,"dynamics_hash":LOADED_DYNAMICS_HASH,"source_is_current":dynamics_hash()==LOADED_DYNAMICS_HASH,"research":read_json(DATA/"research.json",[])}
