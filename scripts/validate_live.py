"""Local production API and mission-contract checks; browser QA is separate."""
from pathlib import Path
import json
import sys
import time
import urllib.request
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from rocket_lab.config import DATA,ROOT
from rocket_lab.schemas import Telemetry,FlightPlan
from rocket_lab.storage import atomic_json,dynamics_hash


def get(path):
    with urllib.request.urlopen('http://127.0.0.1:5180'+path,timeout=60) as response:
        assert response.status==200
        return response.read()


def main():
    checks=dict(verified_at_unix=time.time(),scope='production localhost HTTP, schema, configured mission and replay identity',dynamics_hash=dynamics_hash())
    html=get('/');assert b'Rocket Mission Lab' in html and b'/assets/index-' in html
    checks['production_bundle']=True
    for path in ('health','missions','runs','training','campaigns','checkpoints','results/summary','results/failures','system','schema/telemetry'):
        json.loads(get('/api/'+path));checks[path]=200
    system=json.loads(get('/api/system'));assert system['dynamics_hash']==dynamics_hash()
    plan=dict(launch=[200,-100],landing=[240,-80],separation_altitude=300)
    request=urllib.request.Request('http://127.0.0.1:5180/api/simulate',data=json.dumps(dict(mission='combined',flight_plan=plan)).encode(),headers={'Content-Type':'application/json'},method='POST')
    with urllib.request.urlopen(request,timeout=60) as response:replay=Telemetry.model_validate_json(response.read())
    assert replay.run.outcome=='success' and replay.run.separation
    assert replay.run.dynamics_hash==dynamics_hash()
    assert replay.run.flight_plan==FlightPlan.model_validate(plan)
    saved=Telemetry.model_validate_json(get(f'/api/runs/{replay.run.id}/telemetry'))
    assert saved==replay
    checks['configured_flight']=replay.run.model_dump(mode='json')
    for name in ('demo.json','demo-runs.json'):
        value=json.loads(get('/'+name))
        for record in value if isinstance(value,list) else [value]:Telemetry.model_validate(record)
        checks[name]=200
    checks['browser_scope']='Separate manual browser record; this script does not measure FPS or inspect WebGL.'
    atomic_json(DATA/'live-validation-v2.json',checks)
    print(json.dumps(checks,indent=2))


if __name__=='__main__':main()
