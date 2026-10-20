"""Freeze one candidate before a separate, journalled 10,000-seed batch."""
from pathlib import Path
import argparse
import csv
import hashlib
import sys
import time
import shutil
import traceback

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from rocket_lab.config import DATA,ROOT,load_config
from rocket_lab.evaluate import evaluate
from rocket_lab.probe import publish_probes
from rocket_lab.storage import atomic_json,checkpoint_path,config_hash,read_json


def run(mission,checkpoint,identifier):
    if not identifier.replace('-','').isalnum():raise ValueError('Invalid qualification ID')
    cfg=load_config()
    def candidate_hashes():
        if not checkpoint:return {}
        folder=checkpoint_path(checkpoint)
        return {name:hashlib.sha256((folder/name).read_bytes()).hexdigest() for name in ('model.zip','normalize.pkl','checkpoint.json')}
    manifest=dict(mission=mission,checkpoint_id=checkpoint,config_hash=config_hash(cfg),candidate_sha256=candidate_hashes(),
                  seeds=[10000,19999],episodes=10000,selection_scope='candidate fixed before observing this qualification batch; selected using separate development seeds',
                  physics_sha256=hashlib.sha256((ROOT/'rocket_lab'/'physics.py').read_bytes()).hexdigest())
    path=DATA/'qualifications'/f'{identifier}.manifest.json'
    previous=read_json(path)
    if previous and previous!=manifest:raise ValueError('Frozen candidate/source/config changed; use a new qualification ID')
    atomic_json(path,manifest)
    source_folder=DATA/'qualifications'/f'{identifier}.source';source_folder.mkdir(exist_ok=True)
    for name in ('physics.py','envs.py','controllers.py','simulation.py','schemas.py','config.py','storage.py','evaluate.py'):
        shutil.copyfile(ROOT/'rocket_lab'/name,source_folder/name)
    result,rows=evaluate(mission,episodes=10000,checkpoint_id=checkpoint,start_seed=10000,config=cfg,progress_id=identifier)
    assert candidate_hashes()==manifest['candidate_sha256'],'Candidate changed during qualification'
    result.update(evaluation_role='frozen-candidate nominal qualification',progress_id=identifier,manifest_file=path.name,
                  source_hash=read_json(DATA/'evaluations'/identifier/'identity.json')['source_hash'],completed_at=time.time())
    name=f"{mission}-{'rl' if checkpoint else 'classical'}-l4-{checkpoint or 'controller'}-qualification-{identifier}"
    folder=DATA/'results';atomic_json(folder/f'{name}.json',result)
    with (folder/f'{name}.csv').open('w',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    ci=result['confidence_interval']
    (folder/f'{name}.md').write_text(f"# {mission}: {checkpoint or 'classical L4'}\n\nObserved successes: {result['successes']}/{result['episodes']}. Wilson 95% interval: {ci[0]:.4%} to {ci[1]:.4%}.\n\nFailures: {result['failures']}.\n\nFrozen before this nominal batch; this does not qualify stress conditions, other checkpoints, combined flight or real vehicles.\n",encoding='utf-8')
    publish_probes()
    print({key:result[key] for key in ('mission','successes','episodes','confidence_interval','failures')},flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--mission',required=True,choices=['landing','takeoff'])
    parser.add_argument('--checkpoint');parser.add_argument('--id',required=True)
    args=parser.parse_args()
    try:run(args.mission,args.checkpoint,args.id)
    except Exception:
        if args.id.replace('-','').isalnum():
            path=DATA/'evaluations'/args.id/'status.json';status=read_json(path,{})
            status.update(id=args.id,status='failed',error=traceback.format_exc(),updated_at=time.time())
            try:atomic_json(path,status)
            except OSError:pass # the original disk/I/O error remains authoritative
        raise
