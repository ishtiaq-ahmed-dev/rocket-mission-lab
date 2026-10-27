import {useLab} from './store';
import {sample,restHeight} from './telemetry';

export function exteriorSoundGain(altitude:number,distance:number){
  return Math.exp(-Math.max(0,altitude)/17000)*Math.min(1,100/Math.max(100,distance));
}

/** Locally synthesized sound design. Not a recording of an actual rocket. */
class MissionAudio{
  context:AudioContext|null=null;
  master:GainNode|null=null;engine:GainNode|null=null;wind:GainNode|null=null;
  rumble:OscillatorNode|null=null;filter:BiquadFilterNode|null=null;
  whine:OscillatorNode|null=null;whineGain:GainNode|null=null;
  crackle:GainNode|null=null;
  timer:ReturnType<typeof setInterval>|null=null;
  lastThrottle=0;lastActive=false;lastTime=0;lastPlaying=false;
  private noiseBuffer:AudioBuffer|null=null;
  private syncActivity=()=>{
    const state=useLab.getState(),active=state.sound&&state.playing&&!document.hidden;
    if(active){
      if(!this.timer)this.timer=setInterval(()=>this.update(),50);
      if(this.context?.state==='suspended')void this.context.resume();
    }else{
      if(this.timer)clearInterval(this.timer);this.timer=null;
      this.update();void this.context?.suspend?.();
    }
  };
  async enable(){
    if(!this.context){
      const ctx=new AudioContext();this.context=ctx;
      const master=ctx.createGain();master.gain.value=0;this.master=master;
      const compressor=ctx.createDynamicsCompressor();compressor.threshold.value=-14;compressor.ratio.value=5;master.connect(compressor);compressor.connect(ctx.destination);
      const buffer=ctx.createBuffer(1,ctx.sampleRate*4,ctx.sampleRate),data=buffer.getChannelData(0);let brown=0;
      for(let i=0;i<data.length;i++){brown=(brown+(Math.random()*2-1)*.03)/1.02;data[i]=brown*4;}
      this.noiseBuffer=buffer;
      const noise=ctx.createBufferSource();noise.buffer=buffer;noise.loop=true;
      const filter=ctx.createBiquadFilter();filter.type='lowpass';filter.frequency.value=750;this.filter=filter;
      const engine=ctx.createGain();engine.gain.value=0;this.engine=engine;noise.connect(filter);filter.connect(engine);engine.connect(master);noise.start();
      // Combustion crackle: band-limited noise that only opens under thrust.
      const crackleSource=ctx.createBufferSource();crackleSource.buffer=buffer;crackleSource.loop=true;if(crackleSource.playbackRate)crackleSource.playbackRate.value=1.7;
      const crackleFilter=ctx.createBiquadFilter();crackleFilter.type='bandpass';crackleFilter.frequency.value=1450;if(crackleFilter.Q)crackleFilter.Q.value=.7;
      const crackle=ctx.createGain();crackle.gain.value=0;this.crackle=crackle;crackleSource.connect(crackleFilter);crackleFilter.connect(crackle);crackle.connect(master);crackleSource.start();
      const rumble=ctx.createOscillator();rumble.type='sine';rumble.frequency.value=36;this.rumble=rumble;const sub=ctx.createGain();sub.gain.value=.16;rumble.connect(sub);sub.connect(engine);rumble.start();
      // Turbopump whine rises with throttle; it is intentionally quiet and generic.
      const whine=ctx.createOscillator();whine.type='sawtooth';whine.frequency.value=110;this.whine=whine;const whineFilter=ctx.createBiquadFilter();whineFilter.type='bandpass';whineFilter.frequency.value=900;if(whineFilter.Q)whineFilter.Q.value=4;
      const whineGain=ctx.createGain();whineGain.gain.value=0;this.whineGain=whineGain;whine.connect(whineFilter);whineFilter.connect(whineGain);whineGain.connect(master);whine.start();
      const windSource=ctx.createBufferSource();windSource.buffer=buffer;windSource.loop=true;const high=ctx.createBiquadFilter();high.type='highpass';high.frequency.value=800;
      const wind=ctx.createGain();wind.gain.value=0;this.wind=wind;windSource.connect(high);high.connect(wind);wind.connect(master);windSource.start();
      document.addEventListener('visibilitychange',this.syncActivity);
      useLab.subscribe((next,previous)=>{if(next.playing!==previous.playing||next.sound!==previous.sound)this.syncActivity();});
    }
    await this.context.resume();
    useLab.getState().set({sound:true});this.syncActivity();this.update();
  }
  private burst(duration:number,frequency:number,level:number,type:BiquadFilterType='lowpass'){
    const ctx=this.context;if(!ctx||!this.master||!this.noiseBuffer)return;
    const source=ctx.createBufferSource();source.buffer=this.noiseBuffer;
    const filter=ctx.createBiquadFilter();filter.type=type;filter.frequency.value=frequency;filter.Q.value=type==='bandpass'?1.2:.6;
    const gain=ctx.createGain(),now=ctx.currentTime;
    gain.gain.setValueAtTime(0,now);gain.gain.linearRampToValueAtTime(level,now+.012);gain.gain.exponentialRampToValueAtTime(.0001,now+duration);
    source.connect(filter);filter.connect(gain);gain.connect(this.master);source.start(now);source.stop(now+duration+.05);
    source.onended=()=>{source.disconnect();filter.disconnect();gain.disconnect();};
  }
  update(){
    const ctx=this.context,s=useLab.getState();if(!ctx||!this.master)return;
    const audible=s.sound&&s.playing&&!document.hidden&&s.telemetry!==null;
    const current=s.telemetry?sample(s.telemetry.frames,s.time):null;
    const attenuation=s.audioPerspective==='Exterior'&&current?exteriorSoundGain(current.position[2]-(s.telemetry?restHeight(s.telemetry):40/2),s.cameraDistance):1;
    this.master.gain.setTargetAtTime(audible?s.volume*.55*attenuation:0,ctx.currentTime,.07);
    if(!s.telemetry){this.lastActive=false;this.lastPlaying=s.playing;return;}
    const heardTime=s.time-(s.audioPerspective==='Exterior'?s.cameraDistance/343:0);
    const f=sample(s.telemetry.frames,heardTime),active=heardTime>=0&&s.time<s.telemetry.run.duration;
    const throttle=active?f.throttle:0;
    const horizontalSpeed=Math.hypot(f.velocity[0],f.velocity[1]);
    this.engine?.gain.setTargetAtTime(Math.min(1,throttle*.9),ctx.currentTime,.07);
    this.filter?.frequency.setTargetAtTime(180+throttle*1450,ctx.currentTime,.1);
    this.rumble?.frequency.setTargetAtTime(28+throttle*26,ctx.currentTime,.12);
    this.whine?.frequency.setTargetAtTime(78+throttle*265,ctx.currentTime,.16);
    this.whineGain?.gain.setTargetAtTime(active?throttle*.045:0,ctx.currentTime,.12);
    this.crackle?.gain.setTargetAtTime(active?throttle*throttle*.11:0,ctx.currentTime,.08);
    this.wind?.gain.setTargetAtTime(.035+Math.min(.12,horizontalSpeed*.0012)+Math.min(.05,Math.max(0,f.position[2]-180)*.00008),ctx.currentTime,.2);
    if(audible){
      // Detect actuator events on the playback clock, not on wall time, so
      // scrubbing to an ignition or cutoff still produces the right transient.
      const advanced=s.time>=this.lastTime&&s.time-this.lastTime<.6;
      if(advanced&&this.lastPlaying){
        if(this.lastThrottle<=.02&&throttle>.2)this.burst(.45,420,.30);
        else if(this.lastThrottle>.2&&throttle<=.02)this.burst(.16,1800,.20,'bandpass');
        if(f.phase==='takeoff'&&this.lastTime<.08&&s.time>=.08)this.burst(.6,160,.24);
      }
      const duration=s.telemetry.run.duration;
      if(this.lastTime<duration&&s.time>=duration)this.burst(.5,s.telemetry.run.outcome==='success'?120:90,.26);
    }
    this.lastThrottle=throttle;this.lastTime=s.time;this.lastActive=!!active;this.lastPlaying=s.playing;
  }
  mute(){useLab.getState().set({sound:false});this.update();}
}
export const missionAudio=new MissionAudio();
