import {it,expect,vi} from 'vitest';
import {useLab} from './store';
import type {Telemetry} from './types';
it('requires an explicit enable, follows throttle, and silences pause/mute',async()=>{
 const gains:{value:number;setTargetAtTime:ReturnType<typeof vi.fn>}[]=[];
 const param=()=>({value:0,setTargetAtTime:vi.fn()});
 class FakeContext{
  sampleRate=20;currentTime=0;destination={};resume=vi.fn().mockResolvedValue(undefined);
  createGain(){const gain=param();gains.push(gain);return {gain,connect:vi.fn()};}
  createDynamicsCompressor(){return {threshold:param(),ratio:param(),connect:vi.fn()};}
  createBuffer(){return {getChannelData:()=>new Float32Array(80)};}
  createBufferSource(){return {buffer:null,loop:false,connect:vi.fn(),start:vi.fn()};}
  createBiquadFilter(){return {type:'',frequency:param(),connect:vi.fn()};}
  createOscillator(){return {type:'',frequency:param(),connect:vi.fn(),start:vi.fn()};}
 }
 vi.stubGlobal('AudioContext',FakeContext);vi.stubGlobal('document',{hidden:false,addEventListener:vi.fn()});vi.useFakeTimers();
 const {missionAudio}=await import('./audio');expect(missionAudio.context).toBeNull();
 const f={t:0,position:[0,0,30],velocity:[0,0,-1],quaternion:[1,0,0,0],angular_velocity:[0,0,0],throttle:.6,gimbal:[0,0],fuel_mass:1000,mass:23000,wind:[0,0,0],phase:'landing',reward:null};
 useLab.getState().set({telemetry:{frames:[f,{...f,t:2}],run:{duration:2}} as Telemetry,playing:true,time:1,volume:.3});
 await missionAudio.enable();expect(gains[0].setTargetAtTime).toHaveBeenLastCalledWith(.165,0,.07);
 expect(gains[1].setTargetAtTime).toHaveBeenLastCalledWith(.54,0,.07);
 useLab.getState().set({playing:false});missionAudio.update();expect(gains[0].setTargetAtTime).toHaveBeenLastCalledWith(0,0,.07);
 missionAudio.mute();expect(useLab.getState().sound).toBe(false);vi.clearAllTimers();vi.useRealTimers();vi.unstubAllGlobals();
});
