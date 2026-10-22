import {MapPin,ArrowUpRight} from 'lucide-react';
import {useLab} from './store';
import NumberField from './NumberField';

export default function FlightPlanEditor({mode='flight'}:{mode?:'flight'|'training'}){
  const plan=useLab(s=>s.flightPlan),set=useLab(s=>s.set);
  const update=(site:'launch'|'landing',axis:number,value:number)=>{
    const xy:[number,number]=[...plan[site]];xy[axis]=value;set({flightPlan:{...plan,[site]:xy}});
  };
  const distance=Math.hypot(plan.launch[0]-plan.landing[0],plan.launch[1]-plan.landing[1]);
  const suborbital=plan.profile==='suborbital';
  return <section className="flight-plan" aria-label="Flight coordinates">
    <div className="field-heading"><span className="field-label"><MapPin size={14}/>FLIGHT PLAN</span><span>{distance.toFixed(0)} m transfer</span></div>
    <label className="field-label">VEHICLE / FLIGHT ENVELOPE<select className="full-select" aria-label="Flight envelope" value={plan.profile||'research'} onChange={e=>set({flightPlan:{...plan,profile:e.target.value as 'research'|'suborbital',separation_altitude:e.target.value==='suborbital'?100000:400}})}><option value="research">Low-altitude research · 80–1,500 m</option><option value="suborbital">Suborbital study · 10–150 km</option></select></label>
    {(['launch','landing'] as const).map(site=><fieldset key={site}>
      <legend><i className={site}/>{site==='launch'?'Launch / descent start':'Landing target'}</legend>
      <div className="coordinate-pair">{['X · east','Y · north'].map((axis,i)=><label key={axis}>{axis}<span><NumberField label={`${site==='launch'?'Launch':'Landing'} ${i===0?'X':'Y'}`} value={plan[site][i]} min={-10000} max={10000} step={5} onCommit={value=>update(site,i,value)}/>m</span></label>)}</div>
    </fieldset>)}
    <label className="separation-field">Separation altitude<span><NumberField label="Separation altitude" value={plan.separation_altitude} min={suborbital?10000:80} max={suborbital?150000:1500} step={suborbital?1000:20} onCommit={value=>set({flightPlan:{...plan,separation_altitude:value}})}/>m</span></label>
    {suborbital&&<p className="subtle small">Separate generic 140 t propellant / 3.2 MN vehicle. Variable gravity, drag and independent unpowered stage; no orbit or thermal/structural qualification. Select Combined for launch and recovery.</p>}
    <div className="plan-presets"><button onClick={()=>set({flightPlan:{...plan,landing:[...plan.launch]}})}>Return to launch</button><button onClick={()=>set({flightPlan:{...plan,landing:[plan.launch[0]+80,plan.launch[1]+40]}})}>Separate site<ArrowUpRight size={12}/></button></div>
    <p className="subtle small">Local meters · surface Z = 0. {mode==='flight'?'Apply with Run flight.':'Saved when you start a new training job or campaign.'} Distant targets may exceed the vehicle’s fuel or control limits.</p>
  </section>;
}
