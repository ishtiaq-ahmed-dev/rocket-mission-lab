"""Read-only localhost integration check; no browser automation."""
from pathlib import Path
import json
import sys
import urllib.request
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from rocket_lab.schemas import Telemetry
from rocket_lab.storage import atomic_json
from rocket_lab.config import DATA

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
    checks["browser_visual_verification"]="UNVERIFIED - browser tool policy blocked observation"
    atomic_json(DATA/"live-validation.json",checks)
    print(json.dumps(checks,indent=2))
if __name__=="__main__":main()
