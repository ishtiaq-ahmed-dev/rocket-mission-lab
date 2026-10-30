"""Measure real loopback payloads; never reports browser FPS as measured."""
from pathlib import Path
import gzip
import json
import statistics
import sys
import time
import urllib.request
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from rocket_lab.config import ROOT,DATA
from rocket_lab.storage import atomic_json,read_json


def request(path,compressed=True):
    headers={'Accept-Encoding':'gzip'} if compressed else {}
    started=time.perf_counter()
    with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:5180'+path,headers=headers),timeout=60) as response:
        payload=response.read();encoding=response.headers.get('Content-Encoding')
    elapsed=time.perf_counter()-started
    decoded=gzip.decompress(payload) if encoding=='gzip' else payload
    return json.loads(decoded),dict(wire_bytes=len(payload),decoded_bytes=len(decoded),seconds=elapsed,encoding=encoding)


def main():
    evidence=dict(observed_at_unix=time.time(),scope='Loopback HTTP payloads and request latency; no browser FPS measurement',views={})
    for view in ('flight','training','results'):
        measurements=[]
        for _ in range(5):value,measurement=request('/api/dashboard?view='+view);measurements.append(measurement)
        evidence['views'][view]=dict(**measurements[-1],median_seconds=statistics.median(item['seconds'] for item in measurements),keys=list(value))
    flight,_=request('/api/dashboard?view=flight')
    checkpoints,_=request('/api/checkpoints')
    assert {value['id'] for value in flight['checkpoints']}=={value['id'] for value in checkpoints}
    assert all('config' not in value for value in flight['checkpoints'])
    jobs,_=request('/api/dashboard?view=training')
    assert all(not value['curve'] and not value['episodes'] for value in jobs['jobs'])
    selected,selected_measure=request('/api/training/'+jobs['jobs'][0]['id'])
    evidence['selected_job']=dict(id=selected['id'],history_preserved=bool(selected['episodes']),**selected_measure)
    campaigns,_=request('/api/campaigns')
    assert not any(value['status'] in ('running','starting') for value in campaigns)
    system,_=request('/api/system');assert system['source_is_current']
    evidence.update(dynamics_hash=system['dynamics_hash'],campaigns_stopped=True,services=read_json(ROOT/'logs/services.json'))
    before=read_json(ROOT/'docs/evidence/2026-10-21/performance-before.json')
    previous=sum(value['bytes'] for key,value in before.items() if key.startswith('/api/') and key!='/api/system')*20
    current=evidence['views']['flight']['wire_bytes']
    evidence['flight_polling']=dict(before_bytes_per_minute=previous,after_bytes_per_minute=current,reduction_percent=100*(1-current/previous))
    atomic_json(ROOT/'docs/evidence/2026-10-21/performance-after.json',evidence)
    print(json.dumps(evidence,indent=2))


if __name__=='__main__':main()
