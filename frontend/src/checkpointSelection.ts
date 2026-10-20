import type {Checkpoint,Mission,Result} from './types';
type PhysicalConfig={vehicle:unknown;world?:unknown;mission:unknown};
function canonical(value:unknown):string {
 if(Array.isArray(value))return `[${value.map(canonical).join(',')}]`;
 if(value&&typeof value==='object')return `{${Object.entries(value).sort(([a],[b])=>a.localeCompare(b)).map(([key,item])=>`${key}:${canonical(item)}`).join(',')}}`;
 return JSON.stringify(value)??'undefined';
}
export function compatibleCheckpoints(checkpoints:Checkpoint[],config:PhysicalConfig|undefined,mission:Mission){
 if(!config?.world||mission==='combined')return [];
 return checkpoints.filter(value=>value.mission===mission&&value.steps>0&&value.evaluation_episodes>0&&value.config&&
  ['vehicle','world','mission'].every(key=>canonical(value.config![key])===canonical(config[key as keyof PhysicalConfig])));
}
export function measuredCheckpoint(checkpoints:Checkpoint[],results:Result[],config:PhysicalConfig|undefined,mission:Mission,level:number){
 const eligible=compatibleCheckpoints(checkpoints,config,mission);
 const evidence=(checkpoint:Checkpoint)=>results.filter(value=>value.checkpoint_id===checkpoint.id&&value.scenario==='nominal'&&value.episodes>=checkpoint.evaluation_episodes)
  .sort((a,b)=>b.episodes-a.episodes)[0];
 const statistics=(checkpoint:Checkpoint)=>{
  const result=evidence(checkpoint);const measured=result&&Number.isFinite(result.successes);
  const episodes=measured?result.episodes:checkpoint.evaluation_episodes;
  const successes=measured?result.successes:checkpoint.successes??0;
  const rate=successes/episodes,z=1.95996398454,denominator=1+z*z/episodes;
  const lower=Math.max(0,(rate+z*z/(2*episodes)-z*Math.sqrt(rate*(1-rate)/episodes+z*z/(4*episodes*episodes)))/denominator);
  return {episodes,rate,lower};
 };
 const error=(checkpoint:Checkpoint)=>{
  // Historical ascent summaries contain speed magnitude, not target vertical
  // speed error. Treating a slow crashed ascent as a soft landing is invalid.
  if(mission!=='landing')return 0;
  const result=evidence(checkpoint);
  return result?result.mean_touchdown_speed/2+result.mean_tilt/5+result.mean_pad_distance/5:Number.POSITIVE_INFINITY;
 };
 // Raw reward is deliberately excluded: experiments use different objectives.
 const ranked=[...eligible].sort((a,b)=>{
  const left=statistics(a),right=statistics(b);
  return right.lower-left.lower||right.episodes-left.episodes||right.rate-left.rate||error(a)-error(b)||b.steps-a.steps;
 });
 const best=ranked[0];if(!best)return undefined;if(level===4)return best;
 const sequence=eligible.filter(value=>value.job_id===best.job_id&&value.steps<=best.steps).sort((a,b)=>a.steps-b.steps);
 return sequence[Math.round((sequence.length-1)*(Math.max(1,Math.min(4,level))-1)/3)];
}
