import type {Frame} from './types';

/** Optional procedural sonification of actual engine telemetry, not a recording. */
export class NativeEngineAudio{
 private context:AudioContext;
 private gain:GainNode;
 private filter:BiquadFilterNode;
 private source:AudioBufferSourceNode;
 private history:Frame[]=[];
 private revision=0;
 constructor(){
  const context=new AudioContext();this.context=context;
  this.gain=context.createGain();this.gain.gain.value=0;
  this.filter=context.createBiquadFilter();this.filter.type='lowpass';this.filter.frequency.value=450;
  const compressor=context.createDynamicsCompressor();compressor.threshold.value=-18;compressor.ratio.value=5;
  const buffer=context.createBuffer(1,context.sampleRate*2,context.sampleRate),data=buffer.getChannelData(0);
  let random=7,brown=0;
  for(let i=0;i<data.length;i++){random=(1664525*random+1013904223)>>>0;brown=(brown+((random/4294967296)*2-1)*.03)/1.02;data[i]=brown*4;}
  this.source=context.createBufferSource();this.source.buffer=buffer;this.source.loop=true;
  this.source.connect(this.filter);this.filter.connect(this.gain);this.gain.connect(compressor);compressor.connect(context.destination);this.source.start();
 }
 async update(frame:Frame|undefined,audible:boolean,volume:number){
  const revision=++this.revision;
  if(frame&&this.history.at(-1)?.t!==frame.t){if(frame.t<(this.history.at(-1)?.t??0))this.history=[];this.history=[...this.history.slice(-599),frame];}
  if(!audible||!frame){this.gain.gain.value=0;await this.context.suspend();return;}
  await this.context.resume();
  if(revision!==this.revision)return;
  const distance=Math.hypot(...frame.position),emissionTime=frame.t-distance/343;
  let emitted:Frame|undefined;
  for(let index=this.history.length-1;index>=0;index--){if(this.history[index].t<=emissionTime){emitted=this.history[index];break;}}
  const throttle=emitted?.throttle??0;
  const attenuation=Math.min(1,100/Math.max(100,distance));
  this.gain.gain.setTargetAtTime(Math.min(.2,volume)*throttle*attenuation,this.context.currentTime,.12);
  this.filter.frequency.setTargetAtTime(180+throttle*1300,this.context.currentTime,.12);
 }
 close(){this.revision++;this.source.stop();void this.context.close();this.history=[];}
}
