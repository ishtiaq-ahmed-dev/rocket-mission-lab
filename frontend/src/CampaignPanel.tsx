import {useCallback,useEffect,useState} from 'react';
import {Rocket,Play,Square} from 'lucide-react';
import {useLab} from './store';
import {compact} from './telemetry';

interface Campaign {id:string;status:string;budget:number;steps:number;active_job:string|null;flight_plan:{launch:number[];landing:number[];separation_altitude:number};missions:Record<string,{steps:number;qualified:boolean;best_successes:number;checkpoint_id:string|null}>}
export default function CampaignPanel({online,onError}:{online:boolean;onError:(s:string)=>void}){
  const [campaign,setCampaign]=useState<Campaign|null>(null),[budget,setBudget]=useState(100000000),[busy,setBusy]=useState(false);
  const refresh=useCallback(async()=>{try{const response=await fetch('/api/campaigns');if(response.ok){const values=await response.json() as Campaign[];setCampaign(values[0]||null);}}catch{/* the local connection indicator covers connection loss */}},[]);
  useEffect(()=>{void refresh();const timer=setInterval(()=>void refresh(),3000);return()=>clearInterval(timer);},[refresh]);
  const action=async(stop=false)=>{
    setBusy(true);
    try{const response=await fetch(stop?`/api/campaigns/${campaign!.id}/stop`:'/api/campaigns',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(stop?{}:{steps:budget,algorithm:'PPO',device:'cpu',flight_plan:useLab.getState().flightPlan})});const result=await response.json();if(!response.ok)throw new Error(typeof result.detail==='string'?result.detail:'Check the mission coordinates and training budget.');await refresh();}catch(e){onError((e as Error).message);}finally{setBusy(false);}
  };
  return <section className="panel campaign-panel">
    <div className="panel-title"><span><Rocket size={16}/>THREE-MISSION TRAINING</span><span className="tag">{campaign?.status.replaceAll('_',' ')||'READY TO START'}</span></div>
    <div className="campaign-body"><div><h2>Learn the whole flight.</h2><p>Alternates landing, takeoff, and combined launch & return. Saves checkpoints, evaluates fixed seeds, and stops on a plateau. The budget is shared across all three missions.</p><p className="small subtle">New campaigns use the flight coordinates below. PPO runs on CPU; this small policy does not benefit from forcing GPU training. Qualification requires a separate 10,000-flight batch. A step budget does not guarantee success.</p>{campaign&&<p>Saved campaign plan: launch [{campaign.flight_plan.launch.join(', ')}] → land [{campaign.flight_plan.landing.join(', ')}] · separation {campaign.flight_plan.separation_altitude} m.</p>}</div><div className="campaign-actions"><label>New campaign environment step budget<select aria-label="Campaign step budget" value={budget} onChange={e=>setBudget(+e.target.value)}>{[1000000,10000000,50000000,100000000].map(n=><option key={n} value={n}>{n.toLocaleString()}</option>)}</select></label>{campaign?.status==='running'?<button className="quiet full" disabled={busy} onClick={()=>void action(true)}><Square size={13}/>Stop campaign & save</button>:<button className="primary full" disabled={!online||busy} onClick={()=>void action()}><Play size={13}/>Train all three missions</button>}</div></div>
    {campaign&&<><div className="campaign-missions">{Object.entries(campaign.missions).map(([mission,task])=><div key={mission}><span>{mission}</span><strong>{compact(task.steps)} steps</strong><small>{task.qualified?'Qualified on held-out seeds':task.best_successes>=0?`${task.best_successes} / 256 development successes`:'Waiting for a measured checkpoint'}</small></div>)}</div><p className="qualification">{compact(campaign.steps)} / {compact(campaign.budget)} total steps · {campaign.active_job?`Active: ${campaign.active_job}`:'No active block'}</p></>}
  </section>;
}
