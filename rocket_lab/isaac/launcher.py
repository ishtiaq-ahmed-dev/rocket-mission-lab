"""Start one explicitly requested native session from the local dashboard."""
import os
from pathlib import Path
import subprocess
import threading
import time
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,model_validator
import psutil
from ..config import ROOT
from ..storage import atomic_json,read_json
from .stream import exchange

ISAAC_ROOT=Path(os.environ.get('ROCKET_ISAAC_ROOT',r'D:\AppInstalled\NVIDIA\IsaacSim\6.2.0'))
_process=None
_record=ROOT/'data/isaac/launcher.json'
_saved=read_json(_record,{})
_last={key:value for key,value in _saved.items() if key in ('pid','born','started_at','settings','log','stop_requested_at')} if isinstance(_saved,dict) else {}
_lock=threading.Lock()


class NativeStart(BaseModel):
    model_config=ConfigDict(extra='forbid')
    mission:Literal['landing','takeoff','combined']='combined'
    profile:Literal['research','suborbital']='research'
    renderer:Literal['real-time','path-tracing','headless']='real-time'
    flow:bool=False
    paused:bool=True
    randomized:bool=False
    sensor_noise:bool=False
    gpu_physics:bool=False
    physics_hz:Literal[50,100,120,240]=120
    seed:int=Field(default=42,ge=0,le=2147483647)
    separation_altitude:float=Field(default=400.,ge=100.,le=200000.,allow_inf_nan=False)
    launch:tuple[float,float]=(0.,0.)
    landing:tuple[float,float]=(80.,40.)

    @model_validator(mode='after')
    def geometry(self):
        import math
        if any(not math.isfinite(value) or abs(value)>10000 for value in (*self.launch,*self.landing)):
            raise ValueError('Site coordinates must be finite and within +/-10000 m')
        if self.profile=='research' and self.separation_altitude>2000:
            raise ValueError('Use the separately sized suborbital vehicle for targets above 2000 m')
        return self


def _running():
    if _process is not None:return _process.poll() is None
    if type(_last.get('pid')) is not int:return False
    try:
        process=psutil.Process(_last['pid']);command=' '.join(process.cmdline())
        return abs(process.create_time()-_last.get('born',0))<.1 and str(ROOT/'scripts/run_isaac.ps1').lower() in command.lower()
    except (psutil.Error,ValueError,TypeError):return False


def runtime_status():
    running=_running()
    return dict(installed=(ISAAC_ROOT/'python.bat').is_file(),license_accepted=(ISAAC_ROOT.parent/'rocket-lab-license-accepted.json').is_file(),
        state=('stopping' if _last.get('stop_requested_at') else 'starting_or_running') if running else 'exited' if _last else 'idle',exit_code=None if running or _process is None else _process.returncode,**_last)


def mark_stopping():
    if _running():_last['stop_requested_at']=time.time();atomic_json(_record,_last)


def cancel_start():
    if not _running():return runtime_status()
    try:
        if exchange(dict(op='status'),timeout=.1).get('snapshot'):raise ValueError('The simulator is ready; use Stop native run')
    except OSError:pass
    process=psutil.Process(_last['pid'])
    command=' '.join(process.cmdline()).lower()
    if abs(process.create_time()-_last.get('born',0))>=.1 or str(ROOT/'scripts/run_isaac.ps1').lower() not in command:
        raise ValueError('Session ownership no longer matches the recorded launcher')
    for child in reversed(process.children(recursive=True)):
        try:
            child_command=' '.join(child.cmdline()).lower()
            if str(ROOT/'scripts/isaac_runner.py').lower() in child_command:child.kill()
        except psutil.NoSuchProcess:pass
    try:process.terminate()
    except psutil.NoSuchProcess:pass
    _last['stop_requested_at']=time.time();atomic_json(_record,_last)
    return runtime_status()


def start(request:NativeStart):
    global _process,_last
    with _lock:
        if _running():raise ValueError('A dashboard-owned native session is already starting or running')
        try:exchange(dict(op='status'))
        except OSError:pass
        else:raise ValueError('A native simulator is already connected')
        state=runtime_status()
        if not state['installed']:raise FileNotFoundError(f'Shared Isaac runtime not found at {ISAAC_ROOT}')
        if not state['license_accepted']:raise ValueError('The shared runtime has no recorded NVIDIA license acceptance')
        stamp=str(time.time_ns());log=ROOT/'logs'/f'isaac-session-{stamp}.log';log.parent.mkdir(exist_ok=True)
        arguments=['powershell.exe','-NoProfile','-File',str(ROOT/'scripts/run_isaac.ps1'),'-IsaacRoot',str(ISAAC_ROOT)]
        if request.renderer=='headless':arguments+=['-Headless']
        elif request.renderer=='path-tracing':arguments+=['-PathTracing']
        if request.flow and request.renderer!='headless':arguments+=['-Flow']
        arguments+=['--mission',request.mission,'--profile',request.profile,'--seed',str(request.seed),
            '--launch',*map(str,request.launch),'--landing',*map(str,request.landing),
            '--separation-altitude',str(request.separation_altitude),'--max-seconds','1200' if request.profile=='suborbital' else '180',
            '--physics-hz',str(request.physics_hz),
            '--output',str(ROOT/'data/isaac'/f'session-{stamp}.json')]
        if request.paused:arguments+=['--start-paused']
        if request.randomized:arguments+=['--randomized']
        if request.sensor_noise:arguments+=['--sensor-noise']
        if request.gpu_physics:arguments+=['--gpu-physics']
        with log.open('w',encoding='utf-8') as output:
            _process=subprocess.Popen(arguments,cwd=ROOT,stdout=output,stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        _last=dict(pid=_process.pid,born=psutil.Process(_process.pid).create_time(),started_at=time.time(),log=str(log),settings=request.model_dump(mode='json'))
        atomic_json(_record,_last)
        return runtime_status()
