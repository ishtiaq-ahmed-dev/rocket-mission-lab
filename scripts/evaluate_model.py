"""Publish a larger development sample and an explicitly selected example."""
from pathlib import Path
import argparse
import csv
import sys
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from rocket_lab.config import DATA,ROOT,load_config
from rocket_lab.evaluate import evaluate
from rocket_lab.probe import publish_probes
from rocket_lab.simulation import simulate
from rocket_lab.storage import atomic_json,read_json,checkpoint_path

def publish_example(result_path):
    result=read_json(result_path)
    with result_path.with_suffix('.csv').open(newline='') as stream:rows=list(csv.DictReader(stream))
    first=next((row for row in rows if row['outcome']=='success'),None)
    if first is None:return result
    checkpoint=result['checkpoint_id'];seed=int(first['seed'])
    # Physical evaluation config is recorded separately from the policy's reward.
    cfg=read_json(DATA/'evaluations'/result['progress_id']/'identity.json')['config']
    replay=simulate(result['mission'],'rl',4,seed,checkpoint,save=False,config=cfg)
    assert replay.run.outcome=='success'
    for key in ('touchdown_speed','tilt','pad_distance','fuel_used'):
        assert np.isclose(getattr(replay.run,key),float(first[key]),atol=1e-6,rtol=0)
    replay.run.source=f"MuJoCo development replay; selected successful example from {result['successes']} of {result['episodes']} episodes"
    filename=f"{checkpoint}-dev{result['episodes']}-s{seed}-successful-example.json"
    for folder in (ROOT/'frontend'/'public',ROOT/'frontend'/'dist'):
        if folder.exists():atomic_json(folder/'model-replays'/filename,replay.model_dump())
    result.update(replay_url=f'/model-replays/{filename}',replay_seed=seed,replay_outcome='success',
                  selection_note=f"First successful seed in this sample, selected by outcome; {result['successes']} successes in all {result['episodes']} episodes.")
    atomic_json(result_path,result);publish_probes()
    return result

def run(checkpoint,config_path,progress_id,episodes=256,start_seed=22000,successful_example=False):
    config=load_config(config_path)
    mission=read_json(checkpoint_path(checkpoint)/'checkpoint.json')['mission']
    result,rows=evaluate(mission,episodes=episodes,checkpoint_id=checkpoint,start_seed=start_seed,config=config,progress_id=progress_id)
    result.update(evaluation_role='additional development sample; not 10000-seed qualification',progress_id=progress_id)
    name=f'{mission}-rl-l4-{checkpoint}-development-s{start_seed}-n{episodes}'
    result_path=DATA/'results'/f'{name}.json';atomic_json(result_path,result)
    with result_path.with_suffix('.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    if successful_example:result=publish_example(result_path)
    publish_probes()
    print({key:result[key] for key in ('successes','episodes','mean_touchdown_speed','mean_tilt','mean_pad_distance','confidence_interval')})
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('checkpoint');parser.add_argument('--config',required=True)
    parser.add_argument('--progress-id',required=True);parser.add_argument('--episodes',type=int,default=256)
    parser.add_argument('--start-seed',type=int,default=22000);parser.add_argument('--successful-example',action='store_true')
    parser.add_argument('--publish-existing-example',action='store_true')
    args=parser.parse_args()
    if args.publish_existing_example:
        mission=read_json(checkpoint_path(args.checkpoint)/'checkpoint.json')['mission']
        path=DATA/'results'/f'{mission}-rl-l4-{args.checkpoint}-development-s{args.start_seed}-n{args.episodes}.json'
        result=read_json(path)
        if not result:raise ValueError('No existing development evaluation')
        result['progress_id']=args.progress_id;atomic_json(path,result);publish_example(path)
    else:run(args.checkpoint,args.config,args.progress_id,args.episodes,args.start_seed,args.successful_example)
