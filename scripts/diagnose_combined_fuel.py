"""Where does a combined-mission policy spend its propellant?

Rolls a learned actor on fixed seeds, samples state at 1 Hz, and records the
hold-down release, throttle command, and fuel state at the moment the episode
ends.  The classical controller is flown on the same seeds as a feasibility
control, so "the vehicle cannot do it" and "the policy does not do it" are
different answers in the same report.
"""
from pathlib import Path
import argparse
import sys
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from rocket_lab.config import DATA, load_config
from rocket_lab.envs import RocketEnv
from rocket_lab.missions import configure_flight
from rocket_lab.simulation import LearnedPolicy, simulate
from rocket_lab.storage import atomic_json, checkpoint_path, read_json


def rollout(policy,env,seed,sample_hz=1.):
    observation,_=env.reset(seed=seed)
    trace=[];next_sample=0.;actions=[];burn={};last_fuel=env.physics.fuel;last_phase=env.phase
    while True:
        state=env.physics.state()
        action=policy.action(observation)
        actions.append(float(action[0]))
        if state['t']>=next_sample:
            trace.append(dict(t=round(state['t'],2),altitude=round(state['altitude'],2),
                              vertical_speed=round(float(state['velocity'][2]),2),
                              speed=round(float(np.linalg.norm(state['velocity'])),2),
                              tilt=round(state['tilt'],2),fuel=round(state['fuel_mass'],1),
                              throttle=round(state['throttle'],3),action_throttle=round(float(action[0]),3),
                              on_pad=state['hold_down'],thrust=round(float(env.physics.thrust),0),
                              weight=round(float(state['mass']*env.cfg['world']['gravity']),0),
                              phase=env.phase,staging_pending=bool(env.staging_pending)))
            next_sample+=1./sample_hz
        observation,_,terminated,truncated,info=env.step(action)
        burn[last_phase]=burn.get(last_phase,0.)+max(0.,last_fuel-env.physics.fuel);last_fuel=env.physics.fuel;last_phase=env.phase
        if terminated or truncated:break
    final=env.physics.state();peak=max(trace,key=lambda row:row['altitude'])
    return dict(seed=seed,outcome=info['outcome'],phase=info['phase'],duration=round(final['t'],2),
                fuel_used=round(env.cfg['vehicle']['fuel_mass']*env.physics.mass_scale-final['fuel_mass'],1),
                released=env.physics.release_time is not None,
                release_time=None if env.physics.release_time is None else round(env.physics.release_time,2),
                max_altitude=peak['altitude'],max_altitude_time=peak['t'],
                final_speed=round(float(np.linalg.norm(final['velocity'])),2),final_tilt=round(final['tilt'],2),
                mean_action_throttle=round(float(np.mean(actions)),4),
                min_action_throttle=round(float(np.min(actions)),4),max_action_throttle=round(float(np.max(actions)),4),
                mean_throttle=round(float(np.mean([row['throttle'] for row in trace])),4),
                fuel_by_phase={key:round(value,1) for key,value in burn.items()},
                end_on_pad=final['hold_down'],trace=trace)


def main(checkpoint,seeds,difficulty,training=False):
    meta=read_json(checkpoint_path(checkpoint)/'checkpoint.json')
    cfg,_=configure_flight(load_config(DATA/'jobs'/meta['job_id']/'config.json'),mission='combined')
    policy=LearnedPolicy(checkpoint,observation_config=cfg)
    report=dict(checkpoint_id=checkpoint,difficulty=difficulty,training_curriculum=training,
                scope='Deterministic fixed-seed rollouts; deterministic actor, evaluation env settings; not a reliability result',
                hold_down_release_margin=cfg['vehicle']['hold_down_release_margin'],
                min_throttle=cfg['vehicle']['min_throttle'],dry_mass=cfg['vehicle']['dry_mass'],
                fuel_mass=cfg['vehicle']['fuel_mass'],episodes=[],classical=[])
    for seed in seeds:
        env=RocketEnv('combined',config=cfg,difficulty=difficulty,training=training)
        report['episodes'].append(rollout(policy,env,seed))
        env.close()
    for seed in seeds:
        telemetry=simulate('combined','classical',4,seed,save=False,config=cfg)
        report['classical'].append(dict(seed=seed,outcome=telemetry.run.outcome,fuel_used=round(telemetry.run.fuel_used,1),
                                        duration=round(telemetry.run.duration,2),pad_distance=round(telemetry.run.pad_distance,2),
                                        max_altitude=round(max(frame.position[2] for frame in telemetry.frames),1)))
    stem=f"combined-fuel-{checkpoint.rsplit('__',1)[-1]}-d{difficulty:.2f}-s{seeds[0]}"
    atomic_json(DATA/'diagnostics'/f'{stem}.json',report)
    for row in report['episodes']:
        print(f"RL  seed {row['seed']:>6}  {row['outcome']:>12}  phase {row['phase']:>7}  t={row['duration']:6.1f}s  "
              f"fuel={row['fuel_used']:7.1f}/{cfg['vehicle']['fuel_mass']:.0f}  released={row['released']}  "
              f"max_alt={row['max_altitude']:7.1f}m  mean_throttle={row['mean_throttle']:.3f}  on_pad_end={row['end_on_pad']}")
    for row in report['classical']:
        print(f"CL  seed {row['seed']:>6}  {row['outcome']:>12}  t={row['duration']:6.1f}s  fuel={row['fuel_used']:7.1f}  "
              f"max_alt={row['max_altitude']:7.1f}m  pad_dist={row['pad_distance']:.2f}m")
    print('report',DATA/'diagnostics'/f'{stem}.json')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('checkpoint');parser.add_argument('--seeds',default='20000,20001,20002')
    parser.add_argument('--difficulty',type=float,default=1.0);parser.add_argument('--training',action='store_true',help='apply the training curriculum, including the reduced goal and landing site')
    args=parser.parse_args()
    main(args.checkpoint,[int(value) for value in args.seeds.split(',')],args.difficulty,args.training)
