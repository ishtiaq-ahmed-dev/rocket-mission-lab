"""Read-only localhost integration check; no browser automation."""
from pathlib import Path
import json
import sys
import urllib.request
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from rocket_lab.schemas import Telemetry
from rocket_lab.storage import atomic_json
from rocket_lab.config import DATA
from PIL import Image

def get(url):
    with urllib.request.urlopen(url,timeout=30) as response:
        return response.status,response.read()
def main():
    checks={}
    status,html=get("http://127.0.0.1:5180/")
    checks["frontend_http"]=status;checks["frontend_title"]=b"Rocket Mission Lab" in html
    for path in ["health","missions","runs","training","checkpoints","results/summary","results/failures","system","schema/telemetry"]:
        status,body=get(f"http://127.0.0.1:5180/api/{path}");json.loads(body);checks[f"proxy_{path}"]=status
    _,body=get("http://127.0.0.1:5180/api/runs?mission=landing&method=classical&level=4&seed=42")
    metadata=json.loads(body)[0]
    status,body=get(f"http://127.0.0.1:5180/api/runs/{metadata['id']}/telemetry")
    telemetry=Telemetry.model_validate_json(body)
    checks["telemetry_http"]=status;checks["frame_count"]=len(telemetry.frames)
    checks["initial_hud_altitude"]=telemetry.frames[0].position[2]-telemetry.rocket_length/2
    checks["outcome"]=telemetry.run.outcome
    checks["touchdown_speed"]=telemetry.run.touchdown_speed
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
