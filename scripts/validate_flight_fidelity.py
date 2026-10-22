"""Source-frozen flight pilots, including target history and the 100 km study."""
from pathlib import Path
import argparse
from collections import Counter
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from rocket_lab.simulation import simulate
from rocket_lab.storage import atomic_json,dynamics_hash
from rocket_lab.config import ROOT
from rocket_lab.evaluate import wilson


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--episodes',type=int,default=100)
    parser.add_argument('--high-episodes',type=int,default=16)
    args=parser.parse_args()
    source=dynamics_hash();results=[]
    plans=[('same-pad',dict(launch=[0,0],landing=[0,0],separation_altitude=400)),
           ('separate-site',dict(launch=[200,-100],landing=[240,-80],separation_altitude=300)),
           ('default-transfer',dict(launch=[0,0],landing=[80,40],separation_altitude=400))]
    cases=[(name,mission,plan,None,args.episodes) for name,plan in plans for mission in ('landing','takeoff','combined')]
    cases += [('repeated-divert','landing',plans[-1][1],[dict(time=3,landing=[95,55]),dict(time=6,landing=[70,50])],args.episodes),
              ('100-km-suborbital','combined',dict(profile='suborbital',launch=[0,0],landing=[80,40],separation_altitude=100000),None,args.high_episodes)]
    for name,mission,plan,commands,count in cases:
        rows=[]
        for seed in range(51000,51000+count):
            if dynamics_hash()!=source:raise RuntimeError('Source changed during validation; rerun on the final revision')
            replay=simulate(mission,seed=seed,flight_plan=plan,retargets=commands,save=False)
            r=replay.run
            rows.append(dict(seed=seed,outcome=r.outcome,offset=r.pad_distance,speed=r.touchdown_speed,
                             tilt=r.tilt,fuel_used=r.fuel_used,duration=r.duration,
                             apogee=max(f.position[2]-replay.rocket_length/2 for f in replay.frames),
                             config_hash=replay.config_hash,dynamics_hash=r.dynamics_hash))
        successes=sum(row['outcome']=='success' for row in rows)
        result=dict(case=name,mission=mission,flight_plan=plan,commands=commands,episodes=count,
                    successes=successes,wilson_95=wilson(successes,count),
                    failures=dict(Counter(row['outcome'] for row in rows if row['outcome']!='success')),
                    max_offset=max(row['offset'] for row in rows),max_speed=max(row['speed'] for row in rows),rows=rows)
        results.append(result)
        atomic_json(ROOT/'docs/evidence/2026-10-21/fidelity-v19-pilots.json',dict(
            dynamics_hash=source,updated_at=time.time(),scope='Classical fixed-seed development pilots; not RL or real-vehicle qualification',results=results))
        print(f"{name} {mission}: {successes}/{count}; max offset={result['max_offset']:.3f} m; max speed={result['max_speed']:.3f} m/s; failures={result['failures']}",flush=True)


if __name__=='__main__':main()
