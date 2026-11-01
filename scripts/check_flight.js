#!/usr/bin/env node
/* Flight-model invariants for the shipped replay page.
 *
 * The browser page embeds the simulation as a self-contained IIFE that also
 * exports through CommonJS. This check extracts exactly that block from
 * frontend/index.html so the tested code is the code that ships, then asserts
 * every recorded frame and the interpolated 60 Hz playback are consistent.
 */
'use strict';
const fs=require('fs');
const path=require('path');

const root=path.resolve(__dirname,'..');
const html=fs.readFileSync(path.join(root,'frontend','index.html'),'utf8');
const start=html.indexOf('(function (root) {');
const endMarker="})(typeof window !== 'undefined' ? window : globalThis);";
const end=html.indexOf(endMarker,start);
if(start<0||end<0){console.error('flight model block not found in frontend/index.html');process.exit(1);}

const module_={exports:{}};
new Function('module','exports',html.slice(start,end+endMarker.length))(module_,module_.exports);
const Flight=module_.exports;

const failures=[];
const check=(name,condition,detail)=>{
  if(condition)return;
  failures.push(name+(detail===undefined?'':` — ${detail}`));
};
const approx=(a,b,tol)=>Math.abs(a-b)<=tol;
const finite=value=>typeof value==='number'&&Number.isFinite(value);
const phaseName=phase=>['PAD','ASCENT','SEPARATION','FLIP','BOOSTBACK','COAST','ENTRY','AERO','LANDING','LANDED'][phase]||`phase ${phase}`;

let frameErrors=0,firstFrameError='';
const perFrame=(condition,message)=>{
  if(condition)return;
  frameErrors++;
  if(!firstFrameError)firstFrameError=message;
};

const sim=Flight.run({});
const events=Object.fromEntries(sim.events.map(e=>[e.name,e]));
const B=sim.B.d,K=sim.B.K;
const S2=sim.S2.d,K2=sim.S2.K;
const bodies=[sim.FA,sim.FB,sim.SAT];
const lastT=sim.t0+(sim.n-1)*sim.dt;
const frame=t=>Math.min(Math.max(Math.round((t-sim.t0)/sim.dt),0),sim.n-1);
const row=i=>{
  const o=i*K;
  return {x:B[o],y:B[o+1],z:B[o+2],alt:Math.hypot(B[o],B[o+1]+Flight.RE,B[o+2])-Flight.RE};
};

/* --- shape and timeline --- */
check('frame count',sim.n>10000,sim.n);
check('sample period',approx(sim.dt,0.04,1e-9),sim.dt);
check('timeline ends at 660 s',approx(lastT,660,1e-6),lastT);
for(const name of ['LIFTOFF','MAX_Q','MECO','STAGE_SEP','S2_IGNITION','BOOSTBACK_START','FAIRING_SEP','APOGEE','ENTRY_BURN','ENTRY_END','LANDING_BURN','TOUCHDOWN','SECO','SAT_DEPLOY']){
  check('event '+name,!!events[name]);
}
const times=sim.events.map(e=>e.t);
check('events chronological',times.every((t,i)=>i===0||t>=times[i-1]-1e-9),times.join(','));
for(const name of ['MECO','STAGE_SEP','S2_IGNITION','FAIRING_SEP','BB_END','APOGEE','ENTRY_BURN','ENTRY_END','LANDING_BURN','TOUCHDOWN','SECO','SAT_DEPLOY']){
  const e=events[name];
  if(e)check(name+' inside timeline',e.t>=sim.t0-1e-9&&e.t<=lastT+1e-9,e.t);
}

/* --- every recorded frame --- */
let previousProp=Infinity,minProp=Infinity,peakThrottle=0;
let previousS2Prop=Infinity,lastPhase=-1,lastSeco=0,lastLanded=0;
let previousPosition=null,maxAltitude=0,maxSpeed=0,maxFrameJump=0;

for(let i=0;i<sim.n;i++){
  const o=i*K;
  const x=B[o],y=B[o+1],z=B[o+2];
  const altitude=Math.hypot(x,y+Flight.RE,z)-Flight.RE;
  const speed=Math.hypot(B[o+22],B[o+23],B[o+24]);
  const prop=B[o+9],throttle=B[o+7],nEng=B[o+8],phase=B[o+25],landed=B[o+28];
  const fins=B[o+15],legs=B[o+19],heat=B[o+20],mach=B[o+21],q=B[o+11],g=B[o+26],alpha=B[o+27];
  const axis=[B[o+3],B[o+4],B[o+5]],roll=[B[o+30],B[o+31],B[o+32]];

  maxAltitude=Math.max(maxAltitude,altitude);maxSpeed=Math.max(maxSpeed,speed);
  minProp=Math.min(minProp,prop);
  peakThrottle=Math.max(peakThrottle,throttle);

  for(let k=0;k<K;k++)if(!finite(B[o+k])){perFrame(false,`booster frame ${i} field ${k} is not finite`);break;}
  perFrame(finite(altitude),`booster frame ${i} altitude is not finite`);
  perFrame(altitude>=-0.5,`booster frame ${i} is below ground (${altitude.toFixed(3)} m)`);
  perFrame(finite(prop)&&prop>=-1e-6,`booster frame ${i} propellant ${prop}`);
  perFrame(prop<=previousProp+1e-6,`booster frame ${i} propellant increased ${previousProp} -> ${prop}`);
  perFrame(finite(throttle)&&throttle>=-1e-6&&throttle<=1+1e-6,`booster frame ${i} throttle ${throttle}`);
  perFrame(nEng===0||nEng===1||nEng===3||nEng===9,`booster frame ${i} engine count ${nEng}`);
  perFrame(nEng!==0||Math.abs(throttle)<=1e-9,`booster frame ${i} throttle ${throttle} with engines off`);
  perFrame(nEng===0||(throttle>=-1e-9&&throttle<=1+1e-9),`booster frame ${i} throttle ${throttle} with ${nEng} engines`);
  perFrame(Number.isInteger(phase)&&phase>=0&&phase<=9,`booster frame ${i} invalid phase ${phase}`);
  perFrame(landed===0||landed===1,`booster frame ${i} landed flag ${landed}`);
  perFrame(phase<lastPhase?false:true,`booster frame ${i} phase regression ${phaseName(lastPhase)} -> ${phaseName(phase)}`);
  perFrame(phase===9?landed===1:landed===0,`booster frame ${i} phase/landed mismatch ${phaseName(phase)}/${landed}`);
  perFrame(landed===0||phase===9,`booster frame ${i} landed before landing phase`);
  perFrame(phase!==9||(nEng===0&&Math.abs(throttle)<=1e-9),`booster frame ${i} engine still on after landing`);
  perFrame(phase!==5&&phase!==7||(nEng===0&&Math.abs(throttle)<=1e-9),`booster frame ${i} engine on during ${phaseName(phase)}`);
  perFrame(phase!==8||nEng===0||nEng===1,`booster frame ${i} ${nEng} engines during landing burn`);
  perFrame(phase!==4&&phase!==6||nEng===0||nEng===3,`booster frame ${i} ${nEng} engines during powered descent`);
  perFrame(phase!==0&&phase!==1||nEng===0||nEng===9,`booster frame ${i} ${nEng} engines during ascent`);
  perFrame(phase!==2&&phase!==3||nEng===0,`booster frame ${i} ${nEng} engines during separation/flip`);
  perFrame(Math.abs(Math.hypot(...axis)-1)<=2e-5,`booster frame ${i} axis norm ${Math.hypot(...axis)}`);
  perFrame(Math.abs(Math.hypot(...roll)-1)<=2e-5,`booster frame ${i} roll reference norm ${Math.hypot(...roll)}`);
  perFrame(fins>=0&&fins<=1,`booster frame ${i} fin deployment ${fins}`);
  perFrame(legs>=0&&legs<=1,`booster frame ${i} leg deployment ${legs}`);
  perFrame(heat>=0&&heat<=1.4,`booster frame ${i} heat ${heat}`);
  perFrame(mach>=0,`booster frame ${i} Mach ${mach}`);
  perFrame(q>=-1e-6,`booster frame ${i} dynamic pressure ${q}`);
  perFrame(g>=0,`booster frame ${i} load ${g}`);
  perFrame(alpha>=0&&alpha<=180,`booster frame ${i} angle of attack ${alpha}`);
  perFrame(B[o+10]>0,`booster frame ${i} mass ${B[o+10]}`);

  previousProp=prop;lastPhase=phase;lastLanded=landed;

  const o2=i*K2;
  for(let k=0;k<K2;k++)if(!finite(S2[o2+k])){perFrame(false,`stage 2 frame ${i} field ${k} is not finite`);break;}
  const s2Prop=S2[o2+9],s2Thr=S2[o2+7],s2On=S2[o2+8],s2Sep=S2[o2+16],s2Seco=S2[o2+19];
  const s2Axis=[S2[o2+3],S2[o2+4],S2[o2+5]];
  perFrame(S2[o2+15]>=-0.5,`stage 2 frame ${i} below ground (${S2[o2+15]} m)`);
  perFrame(finite(s2Prop)&&s2Prop>=-1e-6,`stage 2 frame ${i} propellant ${s2Prop}`);
  perFrame(s2Prop<=previousS2Prop+1e-6,`stage 2 frame ${i} propellant increased ${previousS2Prop} -> ${s2Prop}`);
  perFrame(finite(s2Thr)&&s2Thr>=-1e-6&&s2Thr<=1+1e-6,`stage 2 frame ${i} throttle ${s2Thr}`);
  perFrame(s2On===0||s2On===1,`stage 2 frame ${i} engine flag ${s2On}`);
  perFrame(s2Sep===0||s2Sep===1,`stage 2 frame ${i} separation flag ${s2Sep}`);
  perFrame(s2Seco===0||s2Seco===1,`stage 2 frame ${i} SECO flag ${s2Seco}`);
  perFrame(s2Seco===0||s2On===0,`stage 2 frame ${i} engine on after SECO`);
  perFrame(s2Seco===0||Math.abs(s2Thr)<=1e-9,`stage 2 frame ${i} throttle ${s2Thr} after SECO`);
  perFrame(s2Seco>=lastSeco,`stage 2 frame ${i} SECO flag regressed`);
  perFrame(Math.abs(Math.hypot(...s2Axis)-1)<=2e-5,`stage 2 frame ${i} axis norm ${Math.hypot(...s2Axis)}`);
  perFrame(S2[o2+10]>0,`stage 2 frame ${i} mass ${S2[o2+10]}`);
  previousS2Prop=s2Prop;lastSeco=s2Seco;

  if(previousPosition){
    const jump=Math.hypot(x-previousPosition[0],y-previousPosition[1],z-previousPosition[2]);
    maxFrameJump=Math.max(maxFrameJump,jump);
    perFrame(jump<=speed*sim.dt+0.75,`booster frame ${i} position jump ${jump.toFixed(2)} m at ${speed.toFixed(2)} m/s`);
  }
  previousPosition=[x,y,z];
}
check('propellant consumed',Flight.V.s1Prop-minProp>300000,Flight.V.s1Prop-minProp);
check('stage 2 propellant remains',events.SECO&&events.SECO.prop>0,events.SECO&&events.SECO.prop);

for(const tr of bodies){
  check('body track shape',tr.n===sim.n&&tr.K===15,`${tr.n}/${tr.K}`);
  for(let i=0;i<tr.n;i++){
    const o=i*tr.K;
    for(let k=0;k<tr.K;k++)if(!finite(tr.d[o+k])){perFrame(false,`body frame ${i} field ${k} is not finite`);break;}
    perFrame(tr.d[o+7]===0||tr.d[o+7]===1,`body frame ${i} active flag ${tr.d[o+7]}`);
  }
}

/* --- interpolation used by the 60 Hz renderer: never blend discrete states --- */
const STEP_B=[8,25,28],STEP_S2=[8,16,19],STEP_BODY=[7];
function sample(tr,t,out,step){
  let f=(t-sim.t0)/sim.dt;
  f=Math.min(Math.max(f,0),tr.n-1);
  const i=Math.min(Math.floor(f),tr.n-2),u=f-i,Ks=tr.K,o=i*Ks,o2=o+Ks,d=tr.d;
  for(let k=0;k<Ks;k++)out[k]=d[o+k]*(1-u)+d[o2+k]*u;
  for(let k=0;k<step.length;k++)out[step[k]]=d[o+step[k]];
  return out;
}
const bSample=new Float64Array(K),sSample=new Float64Array(K2);
let lastSamplePosition=null,lastSamplePhase=-1,lastSampleLanded=0;
for(let t=sim.t0;t<=lastT+1e-9;t+=1/60){
  sample(sim.B,t,bSample,STEP_B);
  for(let k=0;k<K;k++)if(!finite(bSample[k])){perFrame(false,`interpolated booster at ${t.toFixed(3)} s field ${k} is not finite`);break;}
  const iAlt=Math.hypot(bSample[0],bSample[1]+Flight.RE,bSample[2])-Flight.RE;
  perFrame(iAlt>=-0.5,`interpolated booster at ${t.toFixed(3)} s below ground (${iAlt.toFixed(3)} m)`);
  perFrame(Number.isInteger(bSample[8])&&bSample[8]>=0,`interpolated engine count ${bSample[8]} at ${t.toFixed(3)} s`);
  perFrame(Number.isInteger(bSample[25])&&bSample[25]>=0,`interpolated phase ${bSample[25]} at ${t.toFixed(3)} s`);
  perFrame(bSample[28]===0||bSample[28]===1,`interpolated landed ${bSample[28]} at ${t.toFixed(3)} s`);
  perFrame(bSample[25]>=lastSamplePhase,`interpolated phase regressed at ${t.toFixed(3)} s`);
  perFrame(bSample[25]===9?bSample[28]===1:bSample[28]===0,`interpolated phase/landed mismatch at ${t.toFixed(3)} s`);
  if(lastSamplePosition){
    const jump=Math.hypot(bSample[0]-lastSamplePosition[0],bSample[1]-lastSamplePosition[1],bSample[2]-lastSamplePosition[2]);
    const speed=Math.hypot(bSample[22],bSample[23],bSample[24]);
    perFrame(jump<=speed*(1/60)+0.75,`interpolated position jump ${jump.toFixed(2)} m at ${t.toFixed(3)} s / ${speed.toFixed(2)} m/s`);
  }
  lastSamplePosition=[bSample[0],bSample[1],bSample[2]];lastSamplePhase=bSample[25];lastSampleLanded=bSample[28];

  sample(sim.S2,t,sSample,STEP_S2);
  for(let k=0;k<K2;k++)if(!finite(sSample[k])){perFrame(false,`interpolated stage 2 at ${t.toFixed(3)} s field ${k} is not finite`);break;}
  perFrame(Number.isInteger(sSample[8])&&sSample[8]>=0,`interpolated stage 2 engine flag ${sSample[8]} at ${t.toFixed(3)} s`);
  perFrame(Number.isInteger(sSample[16])&&sSample[16]>=0,`interpolated stage 2 separation flag ${sSample[16]} at ${t.toFixed(3)} s`);
  perFrame(Number.isInteger(sSample[19])&&sSample[19]>=0,`interpolated stage 2 SECO flag ${sSample[19]} at ${t.toFixed(3)} s`);
  perFrame(sSample[19]===0||Math.abs(sSample[7])<=1e-9,`interpolated throttle ${sSample[7]} after SECO at ${t.toFixed(3)} s`);
}
const finalSample=new Float64Array(K);
sample(sim.B,lastT,finalSample,STEP_B);
const finalRow=row(sim.n-1);
check('final frame is sampled exactly',finalSample[0]===finalRow.x&&finalSample[1]===finalRow.y&&finalSample[2]===finalRow.z,
  `${finalSample[0]},${finalSample[1]},${finalSample[2]} vs ${finalRow.x},${finalRow.y},${finalRow.z}`);

if(frameErrors)failures.push(`every-frame checks: ${frameErrors} failure(s); first: ${firstFrameError}`);

/* --- ascent --- */
const meco=events.MECO,sep=events.STAGE_SEP,seco=events.SECO,td=events.TOUCHDOWN;
check('MECO after liftoff',meco.t>60,meco.t);
check('MECO altitude',meco.alt>40000&&meco.alt<120000,meco.alt);
check('MECO speed',meco.v>1200&&meco.v<3000,meco.v);
check('stage separation follows MECO',sep.t>meco.t&&sep.t-meco.t<10,sep.t-meco.t);
check('stage separation above MECO',sep.alt>=meco.alt,sep.alt);

/* --- orbital insertion (vis-viva must match the integrated state) --- */
const orbit=sim.stats.orbit;
check('insertion elements present',!!orbit);
if(orbit){
  const radius=Flight.RE+seco.alt;
  const expected=Math.sqrt(Flight.MU*(2/radius-1/orbit.a));
  check('vis-viva speed at SECO',approx(expected,seco.v,0.5),`${expected} vs ${seco.v}`);
  check('perigee above atmosphere',(orbit.rp-Flight.RE)/1000>150,(orbit.rp-Flight.RE)/1000);
  check('bounded eccentricity',orbit.ecc>=0&&orbit.ecc<0.05,orbit.ecc);
  check('inclination',orbit.inc>0&&orbit.inc<70,orbit.inc);
  check('stage 2 propellant remains',seco.prop>0,seco.prop);
}

/* --- landing --- */
check('touchdown exists',!!td);
check('touchdown vertical speed',td.vV>-2.1&&td.vV<0,td.vV);
check('touchdown horizontal speed',Math.abs(td.vH)<0.5,td.vH);
check('touchdown tilt',td.tilt<5,td.tilt);
check('touchdown inside pad',td.err<=43,td.err);
check('touchdown before timeline end',td.t<lastT,td.t);
const tdRow=row(frame(td.t));
check('contact altitude at leg span',tdRow.alt>1.5&&tdRow.alt<2.05,tdRow.alt);

/* --- global envelope --- */
check('booster altitude envelope',maxAltitude>80000&&maxAltitude<250000,maxAltitude);
check('booster speed envelope',maxSpeed<2500,maxSpeed);
check('peak throttle',peakThrottle<=1+1e-6,peakThrottle);

if(failures.length){
  console.error('flight invariants failed:');
  for(const failure of failures)console.error('  ✗ '+failure);
  process.exit(1);
}
console.log(`flight invariants passed: ${sim.n} frames + 60 Hz interpolation, `+
  `MECO ${meco.alt.toFixed(0)} m / ${meco.v.toFixed(0)} m/s, `+
  `orbit ${(orbit.rp-Flight.RE)/1000|0}×${(orbit.ra-Flight.RE)/1000|0} km at ${orbit.inc.toFixed(1)}°, `+
  `touchdown ${td.vV.toFixed(2)} m/s, ${td.tilt.toFixed(2)}°, ${td.err.toFixed(1)} m from centre, `+
  `max frame step ${maxFrameJump.toFixed(1)} m`);
