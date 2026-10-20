import {useEffect,useState} from 'react';
import {ResponsiveContainer,BarChart,Bar,ErrorBar,CartesianGrid,XAxis,YAxis,Tooltip} from 'recharts';

interface Evaluation {

 checkpoint_id:string;mission:string;algorithm?:string;steps:number;episodes:number;successes:number;seeds:[number,number];

 confidence_interval:[number,number];mean_touchdown_speed:number;mean_tilt:number;mean_pad_distance:number;

 replay_url?:string;replay_seed?:number;selection_note?:string;

}
interface Qualification {mission:string;method:string;checkpoint_id:string|null;successes:number;episodes:number;confidence_interval:[number,number];failures:Record<string,number>;config_hash:string;seeds:[number,number]}
interface QualificationProgress {id:string;mission:string;method:string;status:string;completed:number;total:number;successes:number;updated_at:number}
function FrozenChecks({values}:{values:Qualification[]}){
 if(!values.length)return null;
 return <div><div className="panel-title"><span>FROZEN CANDIDATE CHECKS</span><span className="micro">10,000 NOMINAL SEEDS</span></div><div className="table-scroll"><table><thead><tr><th>EXACT CANDIDATE</th><th>SUCCESSES</th><th>95% WILSON INTERVAL</th><th>FAILURES</th></tr></thead><tbody>{values.map(value=><tr key={`${value.mission}/${value.checkpoint_id||'classical'}`}><td><strong>{value.mission} / {value.method}</strong><span className="table-muted"> · {value.checkpoint_id||'classical L4'}</span></td><td>{value.successes.toLocaleString()} / {value.episodes.toLocaleString()}</td><td>{(value.confidence_interval[0]*100).toFixed(3)}–{(value.confidence_interval[1]*100).toFixed(3)}%</td><td>{Object.entries(value.failures).map(([reason,count])=>`${reason}: ${count}`).join(' · ')||'No failures observed'}</td></tr>)}</tbody></table></div><p className="qualification">Candidates were fixed before this separate nominal seed batch. Results apply to these exact snapshots and configuration; stress conditions, other checkpoints, combined flight and real vehicles need separate qualification.</p></div>;
}

export default function FullTaskChecks({onWatch}:{onWatch:(url:string)=>void}){

 const [evaluations,setEvaluations]=useState<Evaluation[]>([]);
 const [qualifications,setQualifications]=useState<Qualification[]>([]);
 const [qualificationProgress,setQualificationProgress]=useState<QualificationProgress[]>([]);

 useEffect(()=>{

  let active=true;

  const refresh=()=>{
   void fetch('/model-evaluations.json').then(response=>response.ok?response.json():[]).then(value=>{if(active&&Array.isArray(value))setEvaluations(value);}).catch(()=>{});
   void fetch('/model-qualifications.json').then(response=>response.ok?response.json():[]).then(value=>{if(active&&Array.isArray(value))setQualifications(value);}).catch(()=>{});
   void fetch('/model-qualification-progress.json').then(response=>response.ok?response.json():[]).then(value=>{if(active&&Array.isArray(value))setQualificationProgress(value.filter(item=>typeof item?.id==='string'&&Number.isFinite(item.completed)&&Number.isFinite(item.total)&&Number.isFinite(item.successes)));}).catch(()=>{});
  };

  void refresh();const timer=setInterval(()=>void refresh(),15000);return()=>{active=false;clearInterval(timer);};

 },[]);

 if(!evaluations.length&&!qualifications.length&&!qualificationProgress.length)return null;
 const charts=[...new Set(evaluations.map(value=>value.mission))].map(mission=>({mission,data:[...evaluations].filter(value=>value.mission===mission).sort((a,b)=>a.steps-b.steps).map(value=>({
  label:`${value.algorithm||'PPO'} v${value.checkpoint_id.match(/-v(\d+)-/)?.[1]||'?'} ${value.checkpoint_id.split('__')[0].split('-').at(-1)} / ${(value.steps/1e6).toFixed(2)}M`,
  rate:value.successes/value.episodes*100,
  interval:[(value.successes/value.episodes-value.confidence_interval[0])*100,(value.confidence_interval[1]-value.successes/value.episodes)*100],
 }))}));

 return <section className="panel checkpoint-table">{qualificationProgress.filter(value=>value.status!=='completed').map(value=><p className="qualification" key={value.id}><span>{value.mission} / {value.method} · frozen nominal batch · {value.status==='running'&&Date.now()/1000-value.updated_at>120?'stale':value.status} · {value.completed.toLocaleString()} / {value.total.toLocaleString()} evaluated · {value.successes.toLocaleString()} successes so far. Updated {new Date(value.updated_at*1000).toLocaleTimeString()}.</span><progress value={value.completed} max={value.total} aria-label={`${value.mission} ${value.method} qualification progress`}/></p>)}<FrozenChecks values={qualifications}/><div className="panel-title"><span>FULL-TASK DEVELOPMENT CHECKS</span><span className="micro">LARGER FIXED SAMPLES</span></div>{charts.map(({mission,data})=><div key={mission} style={{height:220,padding:"16px 24px 0"}} aria-label={`${mission} full-task development success rates, with Wilson intervals`}><span className="micro">{mission.toUpperCase()} SUCCESS RATE</span><ResponsiveContainer width="100%" height={180}><BarChart data={data} margin={{top:12,right:10,bottom:2,left:-12}}><CartesianGrid stroke="#283238" vertical={false} strokeDasharray="2 5"/><XAxis dataKey="label" tick={{fill:"#9aa7af",fontSize:10}} axisLine={false} tickLine={false}/><YAxis domain={[0,100]} tickFormatter={value=>`${value}%`} tick={{fill:"#7d8c95",fontSize:10}} axisLine={false} tickLine={false}/><Tooltip contentStyle={{background:"#121d24",border:"1px solid #34444d",fontSize:11}} formatter={value=>[`${Number(value).toFixed(2)}%`,"Observed success"]}/><Bar dataKey="rate" fill="#dba976" maxBarSize={58} isAnimationActive={false}><ErrorBar dataKey="interval" width={7} stroke="#e7d4bd" isAnimationActive={false}/></Bar></BarChart></ResponsiveContainer></div>)}<div className="table-scroll"><table><thead><tr><th>POLICY</th><th>SUCCESSES</th><th>95% WILSON INTERVAL</th><th>TERMINAL SPEED</th><th>TILT</th><th>PAD OFFSET</th><th>SEEDS</th></tr></thead><tbody>{evaluations.map(value=><tr key={`${value.checkpoint_id}/${value.seeds[0]}`}><td><strong>{value.mission} / {value.algorithm||'PPO'} · v{value.checkpoint_id.match(/-v(\d+)-/)?.[1]||"?"}</strong><span className="table-muted"><br/>{value.checkpoint_id.split('__')[0]} · {value.steps.toLocaleString()} steps</span></td><td>{value.successes} / {value.episodes}</td><td>{(value.confidence_interval[0]*100).toFixed(2)}–{(value.confidence_interval[1]*100).toFixed(2)}%</td><td>{value.mean_touchdown_speed.toFixed(2)} m/s</td><td>{value.mean_tilt.toFixed(2)}°</td><td>{value.mean_pad_distance.toFixed(2)} m</td><td>{value.seeds.join('–')}</td></tr>)}</tbody></table></div>{evaluations.filter(value=>value.replay_url).map(value=><p className="qualification" key={value.checkpoint_id}><button className="watch-button" onClick={()=>onWatch(value.replay_url!)}>Watch selected success · seed {value.replay_seed}</button><span>{value.selection_note}</span></p>)}<p className="qualification">Full mission difficulty with separate development seeds. These samples are distinct from the smaller checkpoint and stage checks. Wilson intervals describe each sample; they do not correct for repeated model selection on these development seeds. Nominal qualification is reported separately for exact frozen candidates; stress scenarios and other checkpoints require their own evaluations.</p></section>;

}

