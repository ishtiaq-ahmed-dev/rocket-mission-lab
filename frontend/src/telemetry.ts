import {Quaternion} from 'three';
import type {Frame,Telemetry,V3,Run} from './types';
export function parseTelemetry(input:unknown):Telemetry {
  if(!input || typeof input!=='object') throw new Error('Invalid telemetry document');
  const t=input as Telemetry;
  if(!['1.0','1.1'].includes(t.schema_version)||!t.run||!Array.isArray(t.frames)||t.frames.length<2||!Number.isFinite(t.rocket_length)||t.rocket_length<=0||!Number.isFinite(t.initial_fuel)||t.initial_fuel<=0) throw new Error('Unsupported or incomplete telemetry');
  let previous=-1;
  for(const f of t.frames){
    const vectors=[f.position,f.quaternion,f.velocity,f.angular_velocity,f.gimbal,f.wind];
    const sizes=[3,4,3,3,2,3];
    if(vectors.some((v,i)=>!Array.isArray(v)||v.length!==sizes[i]||!v.every(Number.isFinite))||!Number.isFinite(f.t)||f.t<=previous||f.throttle<0||f.throttle>1||!Number.isFinite(f.throttle)||!Number.isFinite(f.fuel_mass)||f.fuel_mass<0||!Number.isFinite(f.mass)||f.mass<=0||!['landing','takeoff'].includes(f.phase))throw new Error('Invalid telemetry frame');
    const norm=Math.hypot(...f.quaternion);if(Math.abs(norm-1)>.01)throw new Error('Quaternion must be normalized');
    previous=f.t;
  }
  return t;
}
const lerp=(a:number,b:number,t:number)=>a+(b-a)*t;
const sampleCache=new WeakMap<Frame[],Map<number,Frame>>();
export function sample(frames:Frame[],time:number):Frame {
  let cache=sampleCache.get(frames);
  if(!cache){cache=new Map();sampleCache.set(frames,cache);}
  const existing=cache.get(time);if(existing)return existing;
  const value=interpolate(frames,time);
  if(cache.size>=256)cache.delete(cache.keys().next().value!);
  cache.set(time,value);return value;
}
function interpolate(frames:Frame[],time:number):Frame {
  if(time<=frames[0].t)return frames[0]; if(time>=frames.at(-1)!.t)return frames.at(-1)!;
  let lo=0,hi=frames.length-1;
  while(hi-lo>1){const mid=(hi+lo)>>1;if(frames[mid].t<=time)lo=mid;else hi=mid;}
  const a=frames[lo],b=frames[hi],u=(time-a.t)/(b.t-a.t);
  const vec=(x:V3,y:V3):V3=>x.map((v,i)=>lerp(v,y[i],u)) as V3;
  const qa=new Quaternion(a.quaternion[1],a.quaternion[2],a.quaternion[3],a.quaternion[0]);
  const qb=new Quaternion(b.quaternion[1],b.quaternion[2],b.quaternion[3],b.quaternion[0]);qa.slerp(qb,u);
  const ignitionChanged=(a.throttle===0)!==(b.throttle===0);
  let stage=a.upper_stage;
  if(stage&&b.upper_stage&&!stage.impacted){
    const next=b.upper_stage,q=new Quaternion(stage.quaternion[1],stage.quaternion[2],stage.quaternion[3],stage.quaternion[0]);
    q.slerp(new Quaternion(next.quaternion[1],next.quaternion[2],next.quaternion[3],next.quaternion[0]),u);
    stage={...stage,position:vec(stage.position,next.position),velocity:vec(stage.velocity,next.velocity),quaternion:[q.w,q.x,q.y,q.z]};
  }
  return {...a,upper_stage:stage,clearance:a.clearance!=null&&b.clearance!=null?lerp(a.clearance,b.clearance,u):a.clearance,t:time,position:vec(a.position,b.position),velocity:vec(a.velocity,b.velocity),angular_velocity:vec(a.angular_velocity,b.angular_velocity),wind:vec(a.wind,b.wind),quaternion:[qa.w,qa.x,qa.y,qa.z],throttle:ignitionChanged?a.throttle:lerp(a.throttle,b.throttle,u),fuel_mass:lerp(a.fuel_mass,b.fuel_mass,u),mass:a.phase!==b.phase?a.mass:lerp(a.mass,b.mass,u),gimbal:[lerp(a.gimbal[0],b.gimbal[0],u),lerp(a.gimbal[1],b.gimbal[1],u)]};
}
/** A target command changes the future goal, never the earlier flight. */
export function landingAt(run:Run,time:number):[number,number]{
  let landing=run.initial_flight_plan?.landing||run.retargets?.[0]?.previous_landing||run.flight_plan?.landing||[0,0];
  for(const event of run.retargets||[])if(event.t<=time+1e-8)landing=event.landing;
  return landing;
}
export function tilt(f:Frame){const x=f.quaternion[1],y=f.quaternion[2];return Math.acos(Math.max(-1,Math.min(1,1-2*(x*x+y*y))))*180/Math.PI;}
export const compact=(v:number)=>v>=1e6?`${(v/1e6).toFixed(1)}M`:v>=1000?`${(v/1000).toFixed(v%1000?1:0)}k`:String(v);
/** Body-centre height on the launch stand. Altitude is measured from the stand top. */
export const restHeight=(t?:{rocket_length?:number;launch_stand_height?:number}|null)=>(t?.rocket_length??40)/2+(t?.launch_stand_height??0);
/** Physical values used by every HUD and chart, so labels cannot drift apart. */
export function frameMetrics(f:Frame,rest:number){
  const altitude=Math.max(0,f.clearance??f.position[2]-rest);
  const speed=Math.hypot(f.velocity[0],f.velocity[1],f.velocity[2]);
  const horizontalSpeed=Math.hypot(f.velocity[0],f.velocity[1]);
  const airVelocity=[f.velocity[0]-f.wind[0],f.velocity[1]-f.wind[1],f.velocity[2]-f.wind[2]];
  return {altitude,speed,horizontalSpeed,verticalSpeed:f.velocity[2],airspeed:Math.hypot(...airVelocity),tilt:tilt(f)};
}
export function decimatedFrames(frames:Frame[],count=220):Frame[]{
  if(frames.length<=count)return frames;
  const step=(frames.length-1)/(count-1);
  return Array.from({length:count},(_,i)=>frames[Math.round(i*step)]);
}
