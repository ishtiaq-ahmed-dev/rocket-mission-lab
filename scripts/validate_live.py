"""Read-only localhost integration check; no browser automation."""
from pathlib import Path
import json
import sys
import urllib.request
import time
import hashlib
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from rocket_lab.schemas import Telemetry
from rocket_lab.storage import atomic_json,select_checkpoint
from rocket_lab.config import DATA,ROOT
from PIL import Image

def get(url):
    with urllib.request.urlopen(url,timeout=30) as response:
        return response.status,response.read()
def main():
    checks={'verified_at_unix':time.time(),'scope':'live localhost HTTP/schema/static-assets; no browser visual or GPU measurement',
            'source_hash':hashlib.sha256(b''.join((ROOT/'rocket_lab'/name).read_bytes() for name in ['physics.py','envs.py','controllers.py','simulation.py'])).hexdigest()}
    status,html=get("http://127.0.0.1:5180/")
    checks["frontend_http"]=status;checks["frontend_title"]=b"Rocket Mission Lab" in html
    checks["frontend_mode"]="production bundle" if b'/@vite/client' not in html and b'/assets/index-' in html else "development"
    for path in ["health","missions","runs","training","checkpoints","results/summary","results/failures","system","schema/telemetry"]:
        status,body=get(f"http://127.0.0.1:5180/api/{path}");json.loads(body);checks[f"proxy_{path}"]=status
        if path=='system':
            assert json.loads(body).get('config_hash'),'Running API must identify the current results configuration'
            checks['current_config_hash']=json.loads(body)['config_hash']
    _,body=get("http://127.0.0.1:5180/api/runs?mission=landing&method=classical&level=4&seed=42")
    metadata=json.loads(body)[0]
    status,body=get(f"http://127.0.0.1:5180/api/runs/{metadata['id']}/telemetry")
    telemetry=Telemetry.model_validate_json(body)
    checks["telemetry_http"]=status;checks["frame_count"]=len(telemetry.frames)
    checks["initial_hud_altitude"]=telemetry.frames[0].position[2]-telemetry.rocket_length/2
    checks["outcome"]=telemetry.run.outcome
    checks["touchdown_speed"]=telemetry.run.touchdown_speed
    _,body=get('http://127.0.0.1:5180/api/health')
    assert json.loads(body)['schema_version']=='1.1','Running API has not imported the new producer'
    checks['rl_default_selection']={}
    for mission in ('landing','takeoff'):
        request=urllib.request.Request('http://127.0.0.1:5180/api/simulate',
            data=json.dumps(dict(mission=mission,method='rl',level=4,seed=42)).encode(),headers={'Content-Type':'application/json'},method='POST')
        with urllib.request.urlopen(request,timeout=60) as response:
            assert response.status==200
            replay=Telemetry.model_validate_json(response.read())
        chosen=select_checkpoint(mission,4)
        assert replay.run.checkpoint_steps==chosen['steps'] and replay.run.checkpoint_id==chosen['id'] and replay.schema_version=='1.1'
        checks['rl_default_selection'][mission]=dict(checkpoint=chosen['id'],steps=replay.run.checkpoint_steps,
            outcome=replay.run.outcome,frames=len(replay.frames),speed=replay.run.touchdown_speed,tilt=replay.run.tilt,pad_distance=replay.run.pad_distance)
    checks['published_model_evidence']={}
    for filename in ('model-probes.json','model-evaluations.json','model-qualifications.json'):
        status,body=get(f'http://127.0.0.1:5180/{filename}');values=json.loads(body);assert isinstance(values,list)
        checks['published_model_evidence'][filename]=dict(http=status,entries=len(values))
        if filename=='model-qualifications.json':assert len(values)>=2 and all(value['episodes']==10000 for value in values)
    _,body=get('http://127.0.0.1:5180/model-evaluations.json')
    examples=[value for value in json.loads(body) if value.get('replay_url')]
    selected=max(examples,key=lambda value:value['success_rate'])
    _,body=get('http://127.0.0.1:5180'+selected['replay_url']);Telemetry.model_validate_json(body)
    checks['selected_example_http']=200
    checks["browser_visual_verification"]="Automation unavailable under browser tool policy; user confirmed live camera rotation. Latest terrain and 4K export need visual confirmation."
    checks["terrain_textures"]={}
    for kind in ["color","normal","roughness"]:
        filename=f"ground-{kind}-4k.jpg"
        image=Image.open(Path(__file__).resolve().parents[1]/"frontend"/"public"/"assets"/"terrain"/filename)
        request=urllib.request.Request(f"http://127.0.0.1:5180/assets/terrain/{filename}",method="HEAD")
        with urllib.request.urlopen(request,timeout=30) as response:
            assert response.status==200 and image.size==(4096,4096)
            checks["terrain_textures"][filename]=dict(http=response.status,width=image.width,height=image.height)
    atomic_json(DATA/"live-validation.json",checks)
    print(json.dumps(checks,indent=2))
if __name__=="__main__":main()
