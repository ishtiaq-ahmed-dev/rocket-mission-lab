#!/usr/bin/env node
/* Flight-model invariants for the shipped replay page.
 *
 * The browser page embeds the simulation as a self-contained IIFE that also
 * exports through CommonJS. This check extracts exactly that block from
 * frontend/index.html so the tested code is the code that ships, then asserts
 * the trajectory is internally consistent.
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

const sim=Flight.run({});
const events=Object.fromEntries(sim.events.map(e=>[e.name,e]));
const B=sim.B.d,K=sim.B.K;
const frame=t=>Math.min(Math.max(Math.round((t-sim.t0)/sim.dt),0),sim.n-1);
const row=i=>{const o=i*K;return {x:B[o],y:B[o+1],z:B[o+2],alt:Math.hypot(B[o],B[o+1]+Flight.RE,B[o+2])-Flight.RE};};

/* --- shape and timeline --- */
check('frame count',sim.n>10000,sim.n);
check('sample period',approx(sim.dt,0.04,1e-9),sim.dt);
for(const name of ['LIFTOFF','MAX_Q','MECO','STAGE_SEP','S2_IGNITION','BOOSTBACK_START','FAIRING_SEP','APOGEE','ENTRY_BURN','LANDING_BURN','TOUCHDOWN','SECO','SAT_DEPLOY']){
  check('event '+name,!!events[name]);
}
const times=sim.events.map(e=>e.t);
check('events chronological',times.every((t,i)=>i===0||t>=times[i-1]-1e-9),times.join(','));

/* --- booster propellant --- */
let previous=Infinity,minimum=Infinity,peakThrottle=0;
for(let i=0;i<sim.n;i++){
  const o=i*K,prop=B[o+9],throttle=B[o+7];
  check('booster propellant monotonic at frame '+i,prop<=previous+1e-6,`${previous} -> ${prop}`);
  check('booster propellant non-negative at frame '+i,prop>=-1e-6,prop);
  check('booster throttle range at frame '+i,throttle>=-1e-6&&throttle<=1+1e-6,throttle);
  previous=prop;minimum=Math.min(minimum,prop);peakThrottle=Math.max(peakThrottle,throttle);
}
check('propellant consumed',Flight.V.s1Prop-minimum>300000,Flight.V.s1Prop-minimum);

/* --- stage 2 propellant --- */
const K2=sim.S2.K,d2=sim.S2.d;
previous=Infinity;
for(let i=0;i<sim.n;i++){
  const prop=d2[i*K2+9];
  check('stage 2 propellant monotonic at frame '+i,prop<=previous+1e-6,`${previous} -> ${prop}`);
  check('stage 2 propellant non-negative at frame '+i,prop>=-1e-6,prop);
  previous=prop;
}

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
check('touchdown before timeline end',td.t<sim.t0+(sim.n-1)*sim.dt,td.t);
const tdRow=row(frame(td.t));
check('contact altitude at leg span',tdRow.alt>1.5&&tdRow.alt<2.05,tdRow.alt);

/* --- global envelope --- */
let maxAlt=0,maxSpeed=0;
for(let i=0;i<sim.n;i++){
  const altitude=Math.hypot(B[i*K],B[i*K+1]+Flight.RE,B[i*K+2])-Flight.RE;
  const speed=Math.hypot(B[i*K+22],B[i*K+23],B[i*K+24]);
  maxAlt=Math.max(maxAlt,altitude);maxSpeed=Math.max(maxSpeed,speed);
}
check('booster altitude envelope',maxAlt>80000&&maxAlt<250000,maxAlt);
check('booster speed envelope',maxSpeed<2500,maxSpeed);

if(failures.length){
  console.error('flight invariants failed:');
  for(const failure of failures)console.error('  ✗ '+failure);
  process.exit(1);
}
console.log(`flight invariants passed: ${sim.n} frames, MECO ${meco.alt.toFixed(0)} m / ${meco.v.toFixed(0)} m/s, `+
  `orbit ${(orbit.rp-Flight.RE)/1000|0}×${(orbit.ra-Flight.RE)/1000|0} km at ${orbit.inc.toFixed(1)}°, `+
  `touchdown ${td.vV.toFixed(2)} m/s, ${td.tilt.toFixed(2)}°, ${td.err.toFixed(1)} m from centre`);
