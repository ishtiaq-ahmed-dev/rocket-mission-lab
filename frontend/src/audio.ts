import {useLab} from './store';
import {sample} from './telemetry';

/** Locally synthesized sound design. Not a recording of an actual rocket. */
class MissionAudio{
  context:AudioContext|null=null;
  master:GainNode|null=null;engine:GainNode|null=null;wind:GainNode|null=null;
  rumble:OscillatorNode|null=null;filter:BiquadFilterNode|null=null;
  timer:ReturnType<typeof setInterval>|null=null;
  async enable(){
    if(!this.context){
      const ctx=new AudioContext();this.context=ctx;
      const master=ctx.createGain();master.gain.value=0;this.master=master;
      const compressor=ctx.createDynamicsCompressor();compressor.threshold.value=-14;compressor.ratio.value=5;master.connect(compressor);compressor.connect(ctx.destination);
      const buffer=ctx.createBuffer(1,ctx.sampleRate*4,ctx.sampleRate),data=buffer.getChannelData(0);let brown=0;
      for(let i=0;i<data.length;i++){brown=(brown+(Math.random()*2-1)*.03)/1.02;data[i]=brown*4;}
      const noise=ctx.createBufferSource();noise.buffer=buffer;noise.loop=true;
      const filter=ctx.createBiquadFilter();filter.type='lowpass';filter.frequency.value=750;this.filter=filter;
      const engine=ctx.createGain();engine.gain.value=0;this.engine=engine;noise.connect(filter);filter.connect(engine);engine.connect(master);noise.start();
      const rumble=ctx.createOscillator();rumble.type='sine';rumble.frequency.value=36;this.rumble=rumble;const sub=ctx.createGain();sub.gain.value=.16;rumble.connect(sub);sub.connect(engine);rumble.start();
      const windSource=ctx.createBufferSource();windSource.buffer=buffer;windSource.loop=true;const high=ctx.createBiquadFilter();high.type='highpass';high.frequency.value=800;
      const wind=ctx.createGain();wind.gain.value=0;this.wind=wind;windSource.connect(high);high.connect(wind);wind.connect(master);windSource.start();
      this.timer=setInterval(()=>this.update(),40);
      document.addEventListener('visibilitychange',()=>this.update());
    }
    await this.context.resume();
    useLab.getState().set({sound:true});this.update();
  }
  update(){
    const ctx=this.context,s=useLab.getState();if(!ctx||!this.master)return;
    const audible=s.sound&&s.playing&&!document.hidden&&s.telemetry!==null;
    this.master.gain.setTargetAtTime(audible?s.volume*.55:0,ctx.currentTime,.07);
    if(!s.telemetry)return;
    const f=sample(s.telemetry.frames,s.time),throttle=s.time<s.telemetry.run.duration?f.throttle:0;
    this.engine?.gain.setTargetAtTime(throttle*.9,ctx.currentTime,.07);
    this.filter?.frequency.setTargetAtTime(220+throttle*1200,ctx.currentTime,.1);
    this.rumble?.frequency.setTargetAtTime(30+throttle*22,ctx.currentTime,.1);
    this.wind?.gain.setTargetAtTime(.04+Math.min(.1,Math.hypot(...f.velocity)*.001),ctx.currentTime,.2);
  }
  mute(){useLab.getState().set({sound:false});this.update();}
}
export const missionAudio=new MissionAudio();
