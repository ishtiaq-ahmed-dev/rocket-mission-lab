import {it,expect} from 'vitest';
import {startPlaybackClock} from './frameScheduler';
it('does no scheduled rendering while idle and respects the frame budget during playback',()=>{
 let time=0,id=0,active=false,elapsed=0,renders=0;const callbacks=new Map<number,(time:number)=>void>();
 const clock={now:()=>time,request:(callback:(time:number)=>void)=>{callbacks.set(++id,callback);return id;},cancel:(id:number)=>{callbacks.delete(id);},playing:()=>active,advance:(dt:number)=>{elapsed+=dt;},invalidate:()=>{renders++;}};
 startPlaybackClock(clock,60);expect(callbacks.size).toBe(0);expect(renders).toBe(0);
 active=true;const stop=startPlaybackClock(clock,60);
 for(let frame=1;frame<=144;frame++){time=frame*1000/144;const pending=[...callbacks.values()];callbacks.clear();pending.forEach(callback=>callback(time));}
 expect(renders).toBeGreaterThanOrEqual(59);expect(renders).toBeLessThanOrEqual(61);expect(elapsed).toBeCloseTo(1,1);
 stop();expect(callbacks.size).toBe(0);
});
