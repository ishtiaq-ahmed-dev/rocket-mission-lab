import {MapPin,ArrowUpRight} from 'lucide-react';
import {useLab} from './store';

export default function FlightPlanEditor({mode='flight'}:{mode?:'flight'|'training'}){
  const plan=useLab(s=>s.flightPlan),set=useLab(s=>s.set);
  const update=(site:'launch'|'landing',axis:number,value:number)=>{
    const xy:[number,number]=[...plan[site]];xy[axis]=value;set({flightPlan:{...plan,[site]:xy}});
  };
  const distance=Math.hypot(plan.launch[0]-plan.landing[0],plan.launch[1]-plan.landing[1]);
  return <section className="flight-plan" aria-label="Flight coordinates">
    <div className="field-heading"><span className="field-label"><MapPin size={14}/>FLIGHT PLAN</span><span>{distance.toFixed(0)} m transfer</span></div>
    {(['launch','landing'] as const).map(site=><fieldset key={site}>
      <legend><i className={site}/>{site==='launch'?'Launch / descent start':'Landing target'}</legend>
      <div className="coordinate-pair">{['X · east','Y · north'].map((axis,i)=><label key={axis}>{axis}<span><input aria-label={`${site==='launch'?'Launch':'Landing'} ${i===0?'X':'Y'}`} type="number" min={-10000} max={10000} step={5} value={plan[site][i]} onChange={e=>update(site,i,+e.target.value)}/>m</span></label>)}</div>
    </fieldset>)}
    <label className="separation-field">Separation altitude<span><input aria-label="Separation altitude" type="number" min={80} max={1500} step={20} value={plan.separation_altitude} onChange={e=>set({flightPlan:{...plan,separation_altitude:+e.target.value}})}/>m</span></label>
    <div className="plan-presets"><button onClick={()=>set({flightPlan:{...plan,landing:[...plan.launch]}})}>Return to launch</button><button onClick={()=>set({flightPlan:{...plan,landing:[plan.launch[0]+80,plan.launch[1]+40]}})}>Separate site<ArrowUpRight size={12}/></button></div>
    <p className="subtle small">Local meters · surface Z = 0. {mode==='flight'?'Apply with Run flight.':'Saved when you start a new training job or campaign.'} Distant targets may exceed the vehicle’s fuel or control limits.</p>
  </section>;
}
