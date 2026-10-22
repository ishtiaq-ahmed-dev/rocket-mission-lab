import {terrainHeight} from './terrain';
import type {FlightPlan} from './types';
export type Site=[number,number];
export const sceneryOffset=(pad:string)=>pad==='Ship'?-850:0;
/** Sites are render X/Z in the scenery's local frame. Physics remains Z-up. */
export function terrainSites(plan:FlightPlan|null|undefined,pad:string):Site[]{
  const offset=sceneryOffset(pad);
  const launch:Site=plan?.launch||[0,0],landing:Site=plan?.landing||[0,0];
  const points:Site[]=pad==='Ship'?(Math.hypot(launch[0]-landing[0],launch[1]-landing[1])>1?[launch]:[]):[launch,landing];
  return points.map(([x,y]):Site=>[x-offset,-y]);
}
export function sceneSurfaceHeight(x:number,z:number,plan:FlightPlan|null|undefined,pad:string){
  const landing=plan?.landing||[0,0];
  if(pad==='Ship'&&Math.hypot(x-landing[0],z+landing[1])<30)return 0;
  return Math.max(-1.3,terrainHeight(x-sceneryOffset(pad),z,terrainSites(plan,pad)));
}
