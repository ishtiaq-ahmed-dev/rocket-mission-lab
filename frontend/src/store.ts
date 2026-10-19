import {create} from 'zustand';
import type {Telemetry} from './types';
interface State {
  telemetry:Telemetry|null;
  ghost:Telemetry|null;
  time:number;
  playing:boolean;
  speed:number;
  camera:string;
  cameraRevision:number;
  quality:string;
  renderInfo:string;
  trail:'Off'|'Flown'|'Full';
  sound:boolean;
  volume:number;
  pad:string;
  recording:boolean;
  load:(telemetry:Telemetry)=>void;
  set:(state:Partial<State>)=>void;
  advance:(dt:number)=>void;
}

export const useLab=create<State>((set,get)=>({
  telemetry:null,ghost:null,time:0,playing:false,speed:1,
  camera:'Rocket',cameraRevision:0,quality:'Ultra',renderInfo:'',
  trail:'Off',sound:false,volume:.35,pad:'Coastal',recording:false,
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
