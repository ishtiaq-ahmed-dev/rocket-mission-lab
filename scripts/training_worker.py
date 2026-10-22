"""Bounded, supervised job entrypoint with retained local diagnostics."""
from pathlib import Path
import argparse
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from rocket_lab.config import DATA

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument('job_id')
    parser.add_argument('--steps',type=int,default=1000000)
    parser.add_argument('--resume')
    parser.add_argument('--warm-start')
    parser.add_argument('--config')
    parser.add_argument('--adapt-optimizer-from')
    parser.add_argument('--eval-episodes',type=int,default=20)
    args=parser.parse_args()
    job_id=args.job_id
    if not job_id.replace('-','').isalnum():raise ValueError("Invalid job ID")
    if args.steps<1:raise ValueError("Steps must be positive")
    if not 1<=args.eval_episodes<=10000:raise ValueError('Evaluation episodes must be within [1,10000]')
    folder=DATA/"jobs"/job_id;folder.mkdir(parents=True,exist_ok=True)
    log=(folder/"output.log").open("a",buffering=1);sys.stdout=sys.stderr=log
    try:
        from rocket_lab.resources import configure_background_worker
        configure_background_worker()
        from rocket_lab.train import train
        train("landing","PPO",args.steps,42,"cpu",job_id,args.eval_episodes,resume=args.resume,warm_start=args.warm_start,config_path=args.config,adapt_optimizer_from=args.adapt_optimizer_from)
    except BaseException:
        import traceback
        from rocket_lab.storage import atomic_json,read_json
        value=read_json(folder/"status.json",dict(id=job_id,mission="landing",algorithm="PPO",steps=0,total_steps=args.steps,started_at=time.time(),curve=[],episodes=[],device="cpu"))
        value.update(status="failed",error=traceback.format_exc(),updated_at=time.time());atomic_json(folder/"status.json",value)
        raise
