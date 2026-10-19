import json
import numpy as np
import pytest
from fastapi.testclient import TestClient
from rocket_lab.api import app
from rocket_lab.schemas import Telemetry, RunMeta
from rocket_lab.config import ROOT, load_config
from rocket_lab.envs import RocketEnv
from rocket_lab.evaluate import wilson

client=TestClient(app)

@pytest.mark.parametrize("path",["/health","/missions","/runs","/results/summary","/results/failures","/schema/telemetry","/training","/checkpoints","/system"])
def test_read_endpoints(path):
    response=client.get(path)
    assert response.status_code==200
    value=response.json()
    if path=="/runs":
        for row in value:RunMeta.model_validate(row)
    if path=="/schema/telemetry":assert "frames" in value["properties"]

def test_replay_schema_and_endpoint():
    rows=client.get("/runs?mission=landing&method=classical&level=4&seed=42").json()
    assert rows, "Run scripts/bootstrap.py first"
    value=client.get(f"/runs/{rows[0]['id']}/telemetry")
    assert value.status_code==200
    telemetry=Telemetry.model_validate(value.json())
    assert len(telemetry.frames)>10
    assert telemetry.frames[-1].t==pytest.approx(telemetry.run.duration)
    assert all(b.t>a.t for a,b in zip(telemetry.frames,telemetry.frames[1:]))

def test_unknown_and_validation():
    assert client.get("/runs/not-a-run/telemetry").status_code==404
    assert client.post("/simulate",json={"mission":"orbit"}).status_code==422
    assert client.post("/simulate",json={"seed":-1}).status_code==422
    assert client.post("/training",json={"steps":999999999}).status_code==422
    assert client.post("/training",json={"algorithm":"shell"}).status_code==422
    assert client.post("/training/nonexistent/stop").status_code==404

def test_live_simulation():
    response=client.post("/simulate",json={"mission":"landing","method":"classical","level":4,"seed":43})
    assert response.status_code==200
    t=Telemetry.model_validate(response.json());assert t.run.seed==43

def test_shared_schema_and_types():
    schema=json.loads((ROOT/"shared"/"telemetry.schema.json").read_text())
    assert schema==Telemetry.model_json_schema()
    ts=(ROOT/"frontend"/"src"/"types.ts").read_text()
    for key in Telemetry.model_fields:assert key in ts
    for key in schema["$defs"]["Frame"]["properties"]:assert key in ts

@pytest.mark.parametrize("expected,state,adjust",[
 ("crash_speed",dict(position=[0,0,20.01],velocity=[0,0,-10]),None),
 ("crash_tilt",dict(position=[0,0,20.01],velocity=[0,0,-.2],quaternion=[np.cos(.2),np.sin(.2),0,0]),None),
 ("missed_pad",dict(position=[10,0,20.01],velocity=[0,0,-.2]),None),
 ("success",dict(position=[0,0,20.01],velocity=[0,0,-.2]),None),
 ("timeout",dict(position=[0,0,220],velocity=[0,0,0]),"timeout"),
 ("out_of_bounds",dict(position=[3000,0,220],velocity=[0,0,0]),None),
 ("out_of_fuel",dict(position=[0,0,220],velocity=[0,0,0]),"fuel"),
])
def test_outcomes(expected,state,adjust):
    cfg=load_config()
    if adjust=="timeout":cfg["mission"]["timeout"]=.05
    e=RocketEnv(config=cfg,noise=False,randomize=False);e.reset(seed=1,options={"state":state})
    if adjust=="fuel":e.physics.fuel=0
    _,reward,terminated,truncated,info=e.step([-1,0,0])
    assert info["outcome"]==expected
    assert (terminated or truncated) and np.isfinite(reward)

def test_wilson_not_certainty():
    lo,hi=wilson(10,10);assert 0<lo<1 and hi<=1
    lo,hi=wilson(0,10);assert 0<=lo<1e-15 and 0<hi<1
    lo,hi=wilson(5000,10000);assert lo<.5<hi and hi-lo<.02

def test_training_dispatch_is_bounded(monkeypatch,tmp_path):
    import rocket_lab.api as module
    monkeypatch.setattr(module,"DATA",tmp_path)
    monkeypatch.setattr(module,"training_jobs",lambda:[])
    commands=[]
    class FakeProcess:
        pid=12345
        def __init__(self,command,**kwargs):commands.append(command)
    monkeypatch.setattr(module.subprocess,"Popen",FakeProcess)
    response=client.post("/training",json={"mission":"landing","algorithm":"PPO","steps":1000,"device":"cpu"})
    assert response.status_code==202
    assert commands[0][1:3]==["-m","rocket_lab.train"]
    assert "1000" in commands[0]
