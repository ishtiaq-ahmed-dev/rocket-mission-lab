import {create} from 'zustand';
import type {Telemetry,FlightPlan} from './types';
interface State {
  telemetry:Telemetry|null;
  ghost:Telemetry|null;
  time:number;
  playing:boolean;
  speed:number;
  camera:string;
  cameraRevision:number;
  cameraTool:'Rotate'|'Pan';
  followRocket:boolean;
  cameraCommand:'In'|'Out'|null;
  commandRevision:number;
  cameraDistance:number;
  flightPlan:FlightPlan;
  frameLimit:number;
  quality:string;
  renderInfo:string;
  trail:'Off'|'Flown'|'Full';
  sound:boolean;
  volume:number;
  audioPerspective:'Exterior'|'Onboard';
  pad:string;
  recording:boolean;
  load:(telemetry:Telemetry)=>void;
  set:(state:Partial<State>)=>void;
  advance:(dt:number)=>void;
}

export const useLab=create<State>((set,get)=>({
  telemetry:null,ghost:null,time:0,playing:false,speed:1,
  camera:'Rocket',cameraRevision:0,cameraTool:'Rotate',followRocket:true,cameraCommand:null,commandRevision:0,cameraDistance:0,
  flightPlan:{launch:[0,0],landing:[80,40],separation_altitude:400},frameLimit:30,quality:'Performance',renderInfo:'',
  trail:'Off',sound:false,volume:.35,audioPerspective:'Exterior',pad:'Coastal',recording:false,
  load:telemetry=>set({telemetry,time:0,playing:true}),
  set:state=>set(state),
  advance:dt=>{
    const state=get();
    if(!state.playing||!state.telemetry)return;
    const end=state.telemetry.frames.at(-1)!.t;
    const time=Math.min(end,state.time+dt*state.speed);
    set({time,playing:time<end});
  },
}));

/** Instruments update at 10 Hz; rendering and paused scrubbing retain exact time. */
export const useInstrumentTime=()=>useLab(s=>s.playing?Math.floor(s.time*10)/10:s.time);
