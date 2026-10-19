import {create} from 'zustand';
import type {Telemetry} from './types';
interface State{telemetry:Telemetry|null;ghost:Telemetry|null;time:number;playing:boolean;speed:number;camera:string;pad:string;recording:boolean;load:(t:Telemetry)=>void;set:(s:Partial<State>)=>void;advance:(dt:number)=>void}
export const useLab=create<State>((set,get)=>({telemetry:null,ghost:null,time:0,playing:false,speed:1,camera:'Cinematic',pad:'Coastal',recording:false,load:telemetry=>set({telemetry,time:0,playing:true}),set:s=>set(s),advance:dt=>{const s=get();if(!s.playing||!s.telemetry)return;const end=s.telemetry.frames.at(-1)!.t;const time=Math.min(end,s.time+dt*s.speed);set({time,playing:time<end});}}));
