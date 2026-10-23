import {memo} from 'react';

export interface NativeSample {t:number;clearance:number;verticalSpeed:number}

const Trend=memo(function Trend({samples,field,title,unit,color}:{samples:NativeSample[];field:'clearance'|'verticalSpeed';title:string;unit:string;color:string}){
 const values=samples.map(sample=>sample[field]);
 const low=Math.min(0,...values),high=Math.max(1,...values),range=high-low;
 const first=samples[0]?.t??0,last=samples.at(-1)?.t??0,span=Math.max(.1,last-first);
 const points=samples.map(sample=>[12+576*(sample.t-first)/span,12+128*(1-(sample[field]-low)/range)]);
 const line=points.map(point=>point.join(',')).join(' ');
 const area=points.length?`12,148 ${line} ${points.at(-1)![0]},148`:'';
 return <section className="panel native-trend"><div className="native-trend-title"><div><h3>{title}</h3><p>Recent physical telemetry · {unit}</p></div><strong>{values.length?`${values.at(-1)!.toFixed(1)} ${unit}`:'—'}</strong></div>
  <div className="native-trend-plot"><span className="native-axis-top">{high.toFixed(0)}</span><span className="native-axis-bottom">{low.toFixed(0)}</span><svg viewBox="0 0 600 160" preserveAspectRatio="none" role="img" aria-label={`${title} over simulation time`}>
   {[12,76,140].map(y=><line key={y} x1="12" x2="588" y1={y} y2={y} stroke="#eeeaf4" strokeDasharray="3 5"/>)}
   {points.length>1&&<><polygon points={area} fill={color} opacity=".07"/><polyline points={line} fill="none" stroke={color} strokeWidth="2.5" vectorEffect="non-scaling-stroke"/></>}
  </svg>{!samples.length&&<p className="native-trend-empty">Waiting for native telemetry</p>}</div><div className="native-trend-time"><span>{first.toFixed(1)} s</span><span>Simulation clock</span><span>{last.toFixed(1)} s</span></div>
 </section>;
});

export default function NativeHistory({samples}:{samples:NativeSample[]}){
 return <div className="native-trends"><Trend samples={samples} field="clearance" title="Ground clearance" unit="m" color="#7c5ce7"/><Trend samples={samples} field="verticalSpeed" title="Vertical velocity" unit="m/s" color="#d67986"/></div>;
}
