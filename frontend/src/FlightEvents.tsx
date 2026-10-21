import {useMemo} from 'react';
import {useLab} from './store';
import type {Telemetry} from './types';

/** Events are derived from recorded dynamics, never a scripted flight sequence. */
export default function FlightEvents({telemetry}:{telemetry:Telemetry|null}){
  const events=useMemo(()=>{
    if(!telemetry)return [];
    const frames=telemetry.frames;
    const values=[{t:0,label:'Start'}];
    if(telemetry.run.separation)values.push({t:telemetry.run.separation.t,label:'Stage separation'});
    const coast=frames.find((frame,i)=>i>0&&frame.phase==='landing'&&frame.throttle===0&&frames[i-1].throttle>0);
    if(coast)values.push({t:coast.t,label:'Engine cutoff'});
    const relight=frames.find(frame=>coast&&frame.t>coast.t&&frame.throttle>0);
    if(relight)values.push({t:relight.t,label:'Relight'});
    values.push({t:telemetry.run.duration,label:telemetry.run.outcome==='success'?'Mission complete':'Final outcome'});
    return values.sort((a,b)=>a.t-b.t);
  },[telemetry]);
  if(!telemetry)return null;
  return <div className="flight-events" aria-label="Recorded flight events"><span>FLIGHT EVENTS</span>{events.map(event=><button key={event.label} onClick={()=>useLab.getState().set({time:event.t,playing:false})}>{event.label}<small>{event.t.toFixed(1)} s</small></button>)}{telemetry.run.separation&&<p>Released stage: unpowered ballistic preview.</p>}</div>;
}
