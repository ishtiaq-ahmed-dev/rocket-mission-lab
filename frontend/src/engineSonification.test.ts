import {expect,it,vi} from 'vitest';
import {NativeEngineAudio} from './engineSonification';
import type {Frame} from './types';

it('uses delayed native throttle and releases audio processing on pause and close',async()=>{
 const gain={value:0,setTargetAtTime:vi.fn()},frequency={value:0,setTargetAtTime:vi.fn()};
 const source={buffer:null,loop:false,connect:vi.fn(),start:vi.fn(),stop:vi.fn()};
 const suspend=vi.fn().mockResolvedValue(undefined),close=vi.fn().mockResolvedValue(undefined);
 class FakeContext{
  sampleRate=20;currentTime=0;destination={};suspend=suspend;close=close;resume=vi.fn().mockResolvedValue(undefined);
  createGain(){return {gain,connect:vi.fn()};}createBiquadFilter(){return {type:'',frequency,connect:vi.fn()};}
  createDynamicsCompressor(){return {threshold:{value:0},ratio:{value:0},connect:vi.fn()};}
  createBuffer(){return {getChannelData:()=>new Float32Array(40)};}createBufferSource(){return source;}
 }
 vi.stubGlobal('AudioContext',FakeContext);
 try{
  const audio=new NativeEngineAudio(),frame={t:0,position:[0,0,10],throttle:.6} as Frame;
  await audio.update(frame,true,.12);expect(gain.setTargetAtTime).toHaveBeenLastCalledWith(0,0,.12);
  await audio.update({...frame,t:.2,throttle:0},true,.12);expect(gain.setTargetAtTime).toHaveBeenLastCalledWith(.072,0,.12);
  await audio.update(frame,false,.12);expect(suspend).toHaveBeenCalled();expect(gain.value).toBe(0);
  audio.close();expect(source.stop).toHaveBeenCalled();expect(close).toHaveBeenCalled();
 }finally{vi.unstubAllGlobals();}
});
