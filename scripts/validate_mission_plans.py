"""Measured custom-target controller pilots with exact config/code/seed identity."""
from pathlib import Path
import argparse
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from rocket_lab.config import DATA,load_config
from rocket_lab.missions import configure_flight
from rocket_lab.evaluate import evaluate,save_result
from rocket_lab.storage import atomic_json,dynamics_hash


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--episodes',type=int,default=100);args=parser.parse_args()
    cases=[('same-pad',dict(launch=[0,0],landing=[0,0],separation_altitude=400)),
           ('separate-site',dict(launch=[200,-100],landing=[240,-80],separation_altitude=300)),
           ('default-transfer',dict(launch=[0,0],landing=[80,40],separation_altitude=400))]
    values=[]
    frozen_source=dynamics_hash()
    for name,plan in cases:
        for mission in ('landing','takeoff','combined'):
            cfg,_=configure_flight(load_config(),plan,mission)
            result,rows=evaluate(mission,episodes=args.episodes,start_seed=50000,config=cfg)
            if result['dynamics_hash']!=frozen_source:raise RuntimeError('Dynamics source changed during validation; start a new pilot')
            result.update(flight_plan=plan,evaluation_role='custom-plan development pilot',case=name)
            save_result(result,rows);values.append(result)
            print(f"{name} {mission}: {result['successes']}/{result['episodes']}; failures={result['failures']}",flush=True)
    if dynamics_hash()!=frozen_source:raise RuntimeError('Dynamics source changed during validation')
    atomic_json(DATA/'mission-plan-validation-2026-10-21.json',dict(dynamics_hash=frozen_source,scope='fixed-seed development pilots, not 10,000-flight qualification',results=values))


if __name__=='__main__':main()
