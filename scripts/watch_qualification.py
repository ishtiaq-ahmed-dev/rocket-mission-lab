"""Publish progress for two current local batches; exit when their results exist."""
import sys
import time
import argparse
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from rocket_lab.config import ROOT,DATA
from rocket_lab.probe import publish_probes
from rocket_lab.storage import atomic_json,read_json

parser=argparse.ArgumentParser()
parser.add_argument('--ids',nargs='+',default=['takeoff-ppo-v13-frozen2761136-nominal10000','takeoff-classical-l4-native-nominal10000'])
args=parser.parse_args()
ids=args.ids
if any(not identifier.replace('-','').isalnum() for identifier in ids):raise ValueError('Invalid evaluation ID')
started=time.time()
while time.time()-started<3600:
    statuses=[value for identifier in ids if (value:=read_json(DATA/'evaluations'/identifier/'status.json',{})).get('id')==identifier]
    for status in statuses:
        if status.get('status')=='running' and time.time()-status.get('updated_at',0)>120:status['status']='stale'
    for folder in (ROOT/'frontend'/'public',ROOT/'frontend'/'dist'):
        if folder.exists():atomic_json(folder/'model-qualification-progress.json',statuses)
    results=[value for path in (DATA/'results').glob('*.json') if (value:=read_json(path,{})).get('progress_id') in ids and value.get('episodes')==10000]
    if results:publish_probes()
    if len({value['progress_id'] for value in results})==len(ids):
        print('Both frozen qualification results published.',flush=True)
        break
    if any(status.get('status') in ('failed','stale') for status in statuses):
        raise RuntimeError('Qualification stopped or heartbeat became stale; inspect its journal')
    time.sleep(5)
else:raise TimeoutError('Qualification progress publisher reached its one-hour bound')
