"""Alternating, resumable mission training with an explicit total step budget.

Run locally: python -m rocket_lab.campaign --steps 100000000
Each task gets a bounded block before the next task. Plateau detection stops
unproductive training; only a new 10,000-seed batch can pass the mission gate.
"""
import argparse
import os
from pathlib import Path
import time
import traceback
import re
from .config import DATA,load_config
from .schemas import FlightPlan
from .missions import configure_flight
from .storage import atomic_json,read_json,checkpoints,dynamics_hash


def campaign_config(mission,plan):
    cfg,_=configure_flight(load_config(),plan,mission)
    cfg['training'].update(profile='flight-fidelity-v19',
        takeoff_goal_curriculum=True,takeoff_curriculum_altitude=5.,takeoff_curriculum_velocity=3.,
        ppo_n_steps=1024,ppo_batch_size=512,ppo_epochs=10,ppo_gamma=.999,ppo_gae_lambda=.995,
        ppo_entropy=.0005,ppo_target_kl=.02,learning_rate=.00015,checkpoint_interval=1000000,
        policy_architecture=[256,256,128],bounded_action_mean=True,policy_log_std=-1.5)
    cfg['reward'].update(success=1000.,terminal_speed=10.,terminal_position=12.,
                         potential_horizontal_speed=12.,time_cost=.5)
    return cfg


def run_campaign(identifier,steps=100000000,block_steps=1000000,plan=None,max_rounds_without_improvement=12,resume=False):
    from .train import train
    from .evaluate import evaluate,save_result
    plan=FlightPlan.model_validate(plan or {}).model_dump(mode='json')
    folder=DATA/'campaigns'/identifier;folder.mkdir(parents=True,exist_ok=True)
    state=dict(id=identifier,status='running',budget=steps,steps=0,started_at=time.time(),updated_at=time.time(),
               active_job=None,flight_plan=plan,pid=os.getpid(),dynamics_hash=dynamics_hash(),missions={m:dict(steps=0,best_successes=-1,plateau=0,qualified=False,checkpoint_id=None) for m in ('landing','takeoff','combined')})
    previous=read_json(folder/'status.json')
    dispatched=bool(previous and previous.get('status')=='starting' and previous.get('missions')=={} and previous.get('steps')==0)
    if dispatched and (previous.get('budget')!=steps or read_json(folder/'plan.json')!=plan):
        raise ValueError('Dispatched campaign plan or budget changed before worker startup')
    if previous and not dispatched:
        if not resume:raise ValueError('Campaign already exists; use --resume after it has stopped')
        if previous['status'] not in ('stopped','plateau','budget_exhausted','failed'):raise ValueError('Stop the campaign before resuming')
        if previous.get('dynamics_hash')!=dynamics_hash():raise ValueError('Dynamics changed; start a new campaign instead of resuming an obsolete optimizer')
        failed_job=previous.get('active_job') if previous['status']=='failed' else None
        if failed_job:
            candidates=[value for value in checkpoints() if value['job_id']==failed_job and value.get('dynamics_hash')==dynamics_hash()]
            if not candidates:raise ValueError('Failed campaign has no compatible checkpoint to recover')
            latest=max(candidates,key=lambda value:value['steps'])
            task=previous['missions'][latest['mission']]
            previous['steps']+=max(0,latest['steps']-task['steps'])
            task.update(steps=latest['steps'],latest_checkpoint_id=latest['id'])
            previous['recovery']=dict(failed_job=failed_job,checkpoint=latest['id'],restored_steps=latest['steps'],
                                      note='Optimizer/normalization recovered; environment and RNG restart from the recorded seed policy')
        state=previous;state.update(status='running',pid=os.getpid(),budget=steps,active_job=None,error=None)
        plan=state['flight_plan'];(folder/'stop').unlink(missing_ok=True)
        for task in state['missions'].values():
            match=re.search(r'-r(\d+)__',task.get('latest_checkpoint_id') or '')
            task['last_round']=int(match[1]) if match else -1
    def write():
        state['updated_at']=time.time();atomic_json(folder/'status.json',state)
    write()
    try:
        round_index=max((task.get('last_round',-1) for task in state['missions'].values()),default=-1)
        round_index=max(0,round_index)
        while state['steps']<steps:
            ran=False
            eligible=[task for task in state['missions'].values() if not task['qualified'] and task['plateau']<max_rounds_without_improvement]
            if eligible and all(task.get('last_round',-1)>=round_index for task in eligible):round_index+=1
            for mission,task in state['missions'].items():
                if dynamics_hash()!=state['dynamics_hash']:raise ValueError('Dynamics changed during campaign; stop and start a newly identified study')
                if (folder/'stop').exists():state['status']='stopped';write();return
                if task['qualified'] or task['plateau']>=max_rounds_without_improvement:continue
                if task.get('last_round',-1)>=round_index:continue
                remaining=steps-state['steps']
                if remaining<4096:break
                amount=min(block_steps,remaining)//4096*4096
                if amount<4096:break
                job=f'{identifier}-{mission}-r{round_index}'
                state['active_job']=job;write()
                cfg=campaign_config(mission,plan);path=folder/f'{mission}.json';atomic_json(path,cfg)
                # Resuming the latest snapshot preserves optimizer and normalizer.
                previous=task.get('latest_checkpoint_id')
                train(mission=mission,steps=amount,job_id=job,device='cpu',seed=42+round_index,
                      eval_episodes=20,resume=previous,config_path=path)
                candidates=[c for c in checkpoints(mission) if c['job_id']==job]
                latest=max(candidates,key=lambda c:(c['steps'],c.get('snapshot_phase')=='post-update final'))
                task['latest_checkpoint_id']=latest['id']
                inherited=task['steps'];used=latest['steps']-inherited
                task['steps']=latest['steps'];state['steps']+=used
                candidate=max(candidates,key=lambda c:(c.get('successes',0),c.get('mean_reward',-1e9)))
                result,rows=evaluate(mission,checkpoint_id=candidate['id'],episodes=256,start_seed=30000,config=cfg)
                result['evaluation_role']='development selection';save_result(result,rows)
                error=result['mean_pad_distance']/5+result['mean_tilt']/5
                error+=(abs(result['mean_touchdown_speed']-cfg['mission']['takeoff_velocity'])/8 if mission=='takeoff' else result['mean_touchdown_speed']/2)
                better_rate=result['successes']>task['best_successes']
                better_error=error<task.get('best_error',float('inf'))*.95
                advancing=latest.get('difficulty',0)>task.get('best_difficulty',0)+.02
                if better_rate or (result['successes']==task['best_successes'] and better_error):task['checkpoint_id']=candidate['id']
                task['plateau']=0 if better_rate or better_error or advancing else task['plateau']+1
                task['best_successes']=max(task['best_successes'],result['successes'])
                task['best_error']=min(task.get('best_error',error),error)
                task['best_difficulty']=max(task.get('best_difficulty',0),latest.get('difficulty',0))
                task['last_round']=round_index
                task['development']=result
                # Qualification seeds never participate in checkpoint selection.
                if result['successes']>=254:
                    held_out_start=100000+round_index*30000+list(state['missions']).index(mission)*10000
                    qualified,rows=evaluate(mission,checkpoint_id=candidate['id'],episodes=10000,start_seed=held_out_start,config=cfg,progress_id=f'{job}-qualification')
                    qualified['evaluation_role']='held-out qualification';save_result(qualified,rows)
                    task['qualification']=qualified
                    task['qualified']=qualified['confidence_interval'][0]>=.99
                write();ran=True
            if not ran:break
            round_index+=1
        state['active_job']=None
        state['status']='qualified' if all(t['qualified'] for t in state['missions'].values()) else ('budget_exhausted' if steps-state['steps']<4096 else 'plateau')
        write()
    except BaseException:
        state.update(status='failed',error=traceback.format_exc());write();raise


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--id',default=f'mission-campaign-{int(time.time())}')
    parser.add_argument('--steps',type=int,default=100000000);parser.add_argument('--block-steps',type=int,default=1000000);parser.add_argument('--plan',type=Path);parser.add_argument('--resume',action='store_true')
    args=parser.parse_args()
    if not args.id.replace('-','').isalnum():raise ValueError('Invalid campaign ID')
    if not 4096<=args.steps<=100000000 or not 4096<=args.block_steps<=10000000:raise ValueError('Invalid training budget')
    run_campaign(args.id,args.steps,args.block_steps,read_json(args.plan) if args.plan else None,resume=args.resume)
