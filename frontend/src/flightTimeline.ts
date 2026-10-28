import type {Telemetry} from './types';

/** Only recorded state transitions are events; there are no animation offsets. */
export function recordedTimeline(data:Telemetry){
 const frames=data.frames,mission=data.run.mission,end=frames.at(-1)!.t;
 const release=frames.find(frame=>frame.hold_down===false);
 const liftoff=mission==='landing'?null:data.run.launch_release_time??release?.release_time??release?.t??null;
 const separation=data.run.separation?.t??null;
 const cutoff=frames.find((frame,index)=>index>0&&frame.throttle<=1e-8&&frames[index-1].throttle>1e-8);
 const relight=frames.find(frame=>separation!==null&&frame.t>separation&&frame.throttle>1e-8);
 // Initial contact while held on the stand is not a landing.
 const touchdown=mission==='takeoff'?null:frames.find((frame,index)=>index>0&&frame.phase==='landing'&&
  frame.clearance!==undefined&&frame.clearance!==null&&frame.clearance<=1e-7&&
  frames[index-1].clearance!==undefined&&frames[index-1].clearance!>1e-7)?.t??null;
 const ascent=liftoff===null?null:(separation??(mission==='takeoff'?end:null));
 return {liftoff,separation,cutoff:cutoff?.t??null,relight:relight?.t??null,touchdown,end,
  ascentSeconds:ascent===null||liftoff===null?null:ascent-liftoff,
  recoverySeconds:mission==='landing'?(touchdown??end)-frames[0].t:separation===null?null:(touchdown??end)-separation};
}
