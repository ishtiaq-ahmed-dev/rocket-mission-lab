"""Matched 32-seed stress pilots, kept separate from nominal qualification."""
from pathlib import Path
import argparse
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from rocket_lab.config import DATA
from rocket_lab.evaluate import evaluate,save_result
from rocket_lab.storage import atomic_json,config_hash,read_json


def run(mission,checkpoint):
    summaries=[]
    for selected in (None,checkpoint):
        for scenario in ('gusts','noise','thrust_loss','extreme_starts'):
            identifier=f'{mission}-{selected or "classical-l4"}-{scenario}-native-pilot32'
            result,rows=evaluate(mission,episodes=32,checkpoint_id=selected,scenario=scenario,progress_id=identifier)
            identity=read_json(DATA/'evaluations'/identifier/'identity.json')
            result.update(evaluation_role='32-seed stress pilot; not full stress qualification',progress_id=identifier,
                          source_hash=identity['source_hash'],effective_config_hash=config_hash(identity['config']))
            save_result(result,rows);summaries.append(result)
            print(f"STRESS {mission} {'rl' if selected else 'classical'} {scenario}: {result['successes']}/32 {result['failures']}",flush=True)
    atomic_json(DATA/'stress'/f'{mission}-{checkpoint}.json',dict(scope='matched 32-seed stress pilots, not 10000-seed stress qualification',results=summaries))
    return summaries


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--mission',required=True,choices=['landing','takeoff'])
    parser.add_argument('--checkpoint',required=True);args=parser.parse_args();run(args.mission,args.checkpoint)
