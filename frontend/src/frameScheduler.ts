interface Clock {
 now:()=>number;
 request:(callback:(time:number)=>void)=>number;
 cancel:(id:number)=>void;
 playing:()=>boolean;
 advance:(dt:number)=>void;
 invalidate:()=>void;
}
/** Schedule only active playback. Mouse controls independently invalidate. */
export function startPlaybackClock(clock:Clock,limit:number){
 if(!clock.playing())return()=>{};
 let request=0,previous=clock.now(),lastRender=previous;
 const interval=1000/limit;
 function tick(now:number){
  if(!clock.playing())return;
  if(now-lastRender>=interval-1e-6){
   clock.advance((now-previous)/1000);previous=now;
   lastRender+=Math.floor((now-lastRender+1e-6)/interval)*interval;clock.invalidate();
  }
  if(clock.playing())request=clock.request(tick);
 }
 request=clock.request(tick);return()=>clock.cancel(request);
}
