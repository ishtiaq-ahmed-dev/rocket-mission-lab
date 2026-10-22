import {useMemo} from 'react';
import {useLab} from './store';
import type {Telemetry} from './types';

/** Events are derived from recorded dynamics, never a scripted flight sequence. */
export default function FlightEvents({telemetry}:{telemetry:Telemetry|null}){
  const events=useMemo(()=>{
    if(!telemetry)return [];
    const frames=telemetry.frames;
    const values=[{t:0,label:'Start'}];
    const ignition=frames.find(frame=>frame.throttle>.02);
    if(ignition)values.push({t:ignition.t,label:'Ignition'});
    if(telemetry.run.launch_release_time!=null)values.push({t:telemetry.run.launch_release_time,label:'Hold-down release'});
    for(const retarget of telemetry.run.retargets||[])values.push({t:retarget.t,label:`Target moved to ${retarget.landing[0].toFixed(0)}, ${retarget.landing[1].toFixed(0)} m`});
    if(telemetry.run.separation)values.push({t:telemetry.run.separation.t,label:'Stage separation'});
    const apogee=frames.find((frame,i)=>i>0&&frame.velocity[2]<=0&&frames[i-1].velocity[2]>0);
    if(apogee)values.push({t:apogee.t,label:'Apogee'});
    const coast=frames.find((frame,i)=>i>0&&frame.phase==='landing'&&frame.throttle===0&&frames[i-1].throttle>0);
    if(coast)values.push({t:coast.t,label:'Engine cutoff'});
    const relight=frames.find(frame=>coast&&frame.t>coast.t&&frame.throttle>0);
    if(relight)values.push({t:relight.t,label:'Relight'});
    values.push({t:telemetry.run.duration,label:telemetry.run.outcome==='success'?'Mission complete':'Final outcome'});
    return values.sort((a,b)=>a.t-b.t);
  },[telemetry]);
  if(!telemetry)return null;
  return <div className="flight-events" aria-label="Recorded flight events"><span>FLIGHT EVENTS</span>{events.map(event=><button key={`${event.label}-${event.t}`} onClick={()=>useLab.getState().set({time:event.t,playing:false})}>{event.label}<small>{event.t.toFixed(1)} s</small></button>)}{telemetry.run.separation&&<p>Released stage: {telemetry.frames.some(f=>f.upper_stage)?'independently integrated unpowered body.':'archived ideal ballistic preview.'}</p>}</div>;
}
