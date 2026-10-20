import type {Result} from './types';

export function resultSampleId(value:Result){
 return [value.mission,value.method,value.checkpoint_id??value.level,value.scenario,value.config_hash,
  value.episodes,value.seeds?.join('-'),value.source_hash,value.progress_id].join('/');
}

export function largestClassicalSamples(values:Result[],mission:string,configHash:string|undefined){
 if(!configHash)return [];
 const chosen=new Map<number,Result>();
 for(const value of values){
  if(value.mission!==mission||value.method!=='classical'||value.scenario!=='nominal'||value.config_hash!==configHash)continue;
  const previous=chosen.get(value.level);
  if(!previous||value.episodes>previous.episodes||value.episodes===previous.episodes&&(value.completed_at??0)>(previous.completed_at??0))chosen.set(value.level,value);
 }
 return [...chosen.values()].sort((a,b)=>a.level-b.level);
}
