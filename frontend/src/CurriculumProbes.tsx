import {useCallback,useState} from 'react';
import {useVisiblePoll} from './useVisiblePoll';
interface Probe {
 checkpoint_id:string;steps:number;mission:string;profile:string;training_profile?:string;practice?:boolean;algorithm?:string;
 stages:{difficulty:number;episodes:number;successes:number;mean_speed:number;mean_tilt:number;mean_offset:number;replay_url?:string;replay_seed?:number;replay_outcome?:string;target_altitude?:number;target_velocity?:number}[];
}
function policyName(probe:Probe){
 if(probe.training_profile==='terminal-speed-v17')return 'Terminal speed cost';
 if(probe.training_profile==='near-ground-speed-v16')return 'Ground speed cost';
 if(probe.training_profile==='precision-updates-v15')return 'Precision updates';
 if(probe.training_profile==='sac-full-v14')return 'SAC full task';
 if(probe.training_profile==='ascent-horizon-v13')return 'Ascent longer horizon';
 if(probe.training_profile==='balanced-touchdown-v12')return 'Balanced touchdown';
 if(probe.training_profile==='pad-accuracy-v10')return 'Pad accuracy';
 if(probe.training_profile==='takeoff-goals-v11')return 'Ascent curriculum';
 if(probe.training_profile==='long-horizon-v9')return 'Longer horizon';
 if(probe.training_profile==='full-task-v8')return 'Full difficulty';
 if(probe.training_profile==='throttle-exploration-v7')return 'Wider exploration';
 if(probe.training_profile==='bounded-mean-v6')return 'Bounded output';
 if(probe.training_profile==='mixed-starts-v5')return 'Mixed starts';
 return probe.profile.endsWith('v4')?'Revised model':'Previous model';
}
export default function CurriculumProbes({onWatch}:{onWatch:(url:string)=>void}){
 const [probes,setProbes]=useState<Probe[]>([]);
 const refresh=useCallback(()=>fetch('/model-probes.json').then(response=>response.ok?response.json():[]).then(value=>{if(Array.isArray(value))setProbes(value);}).catch(()=>{}),[]);
 useVisiblePoll(refresh,60000);
 if(!probes.length)return null;
 return <section className="panel checkpoint-table"><div className="panel-title"><span>DIFFICULTY CHECKS</span><span className="micro">MEASURED DEVELOPMENT EPISODES</span></div><div className="table-scroll"><table><thead><tr><th>POLICY</th><th>DIFFICULTY</th><th>SUCCESSES</th><th>TERMINAL SPEED</th><th>TILT</th><th>PAD OFFSET</th><th>FIXED-SEED REPLAY</th></tr></thead><tbody>{probes.flatMap(probe=>probe.stages.map(stage=><tr key={`${probe.checkpoint_id}/${probe.practice?"practice":"evaluation"}/${stage.difficulty}`}><td><strong>{probe.mission} · {policyName(probe)}</strong><span className="table-muted"> · {probe.steps.toLocaleString()} steps</span></td><td>{Math.round(stage.difficulty*100)} / 100{probe.practice?` · Practice goal ${stage.target_altitude?.toFixed(1)} m / ${stage.target_velocity?.toFixed(1)} m/s`:stage.difficulty===1?' · Full task':''}</td><td>{stage.successes} / {stage.episodes}</td><td>{stage.mean_speed.toFixed(2)} m/s</td><td>{stage.mean_tilt.toFixed(2)}°</td><td>{stage.mean_offset.toFixed(2)} m</td><td>{stage.replay_url&&<button className="watch-button" onClick={()=>onWatch(stage.replay_url!)}>Watch seed {stage.replay_seed}</button>}<span className="table-muted"> {stage.replay_outcome?.replaceAll('_',' ')}</span></td></tr>))}</tbody></table></div><p className="qualification">Each stage uses the same development seeds. Replays show the first seed at every stage, including failures. Lower difficulties have easier starts and weaker disturbances. Training-only short ascent goals are explicitly labelled; their successes do not count as full-task outcomes. These samples do not establish full-task reliability.</p></section>;
}
