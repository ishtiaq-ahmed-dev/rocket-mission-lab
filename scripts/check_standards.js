#!/usr/bin/env node
/* Public-reference checks for the shipped browser flight model.
 *
 * This is deliberately not a certification test. It verifies that the page's
 * WGS-84 constants, ISO 2533/U.S. 1976 atmosphere, public Merlin/MVac anchors,
 * mass closure and default orbit/landing stay inside the documented envelope.
 */
'use strict';
const fs=require('fs');
const path=require('path');

const root=path.resolve(__dirname,'..');
/* the simulator block that ships in frontend/index.html, flown by the shipped policy weights */
const Flight=require('./flight_policy/sim').loadSim();
const referencePath=path.join(root,'data','reference','international-standard.json');
const reference=JSON.parse(fs.readFileSync(referencePath,'utf8'));

const checks=[];
function record(name,actual,expected,tolerance,unit){
  const ok=Number.isFinite(actual)&&Math.abs(actual-expected)<=tolerance;
  checks.push({name,actual,expected,tolerance,unit:unit||'',ok});
  if(!ok)console.error(`  x ${name}: ${actual}${unit||''} (reference ${expected}${unit||''}, tolerance ${tolerance})`);
}
function relative(name,actual,expected,fraction,unit){
  record(name,actual,expected,Math.abs(expected)*fraction,unit);
}
function close(name,actual,expected,tolerance,unit){
  record(name,actual,expected,tolerance,unit);
}

/* WGS-84 / SI anchors */
const earth=reference.earth;
relative('WGS-84 GM',Flight.MU,earth.gm_m3_s2,1e-9,' m3/s2');
relative('WGS-84 mean radius',Flight.RE,earth.mean_radius_m,1e-9,' m');
relative('WGS-84 rotation rate',Flight.OMEGA,earth.angular_velocity_rad_s,1e-9,' rad/s');
close('standard gravity',Flight.G0,earth.standard_gravity_m_s2,1e-12,' m/s2');

/* Public Falcon 9 anchors and model mass closure */
const V=Flight.V,pub=reference.vehicle.public;
relative('stage 1 propellant',V.s1Prop,pub.stage1_propellant_kg,0.01,' kg');
relative('stage 2 propellant',V.s2Prop,pub.stage2_propellant_kg,0.01,' kg');
relative('stage 1 vacuum thrust (9 engines)',9*V.merTvac,9*pub.stage1_thrust_vac_n,0.005,' N');
relative('stage 1 sea-level thrust (9 engines)',9*(V.merTvac-V.merAe*Flight.pressAt(0)),9*pub.stage1_thrust_sl_n,0.005,' N');
relative('Merlin 1D vacuum Isp',V.merTvac/(V.merMdot*Flight.G0),pub.stage1_isp_vac_s,0.01,' s');
relative('MVac vacuum thrust',V.mvacT,pub.stage2_thrust_vac_n,0.005,' N');
relative('MVac vacuum Isp',V.mvacT/(V.mvacMdot*Flight.G0),pub.stage2_isp_vac_s,0.01,' s');
relative('reference area from 3.7 m diameter',V.S,Math.PI*Math.pow(pub.diameter_m/2,2),0.03,' m2');
relative('model liftoff mass closure',V.s1Dry+V.s1Prop+V.s2Dry+V.s2Prop+V.fairing,pub.liftoff_mass_kg,0.01,' kg');

/* ISO 2533 / U.S. 1976 layer points, evaluated at geometric altitude */
for(const point of reference.atmosphere.checks){
  const H=point.geopotential_altitude_m;
  const h=Flight.RE*H/(Flight.RE-H);
  relative(`${H} m geopotential temperature`,Flight.tempAt(h),point.temperature_k,0.005,' K');
  relative(`${H} m geopotential pressure`,Flight.pressAt(h),point.pressure_pa,0.02,' Pa');
  relative(`${H} m geopotential density`,Flight.rhoAt(h),point.density_kg_m3,0.025,' kg/m3');
  if(point.speed_of_sound_m_s!==undefined){
    relative(`${H} m geopotential sound speed`,Flight.soundAt(h),point.speed_of_sound_m_s,0.01,' m/s');
  }
}

/* WGS-84 site coordinates */
const mission=reference.mission;
const r2d=180/Math.PI;
close('SLC-40 latitude',Flight.LAT_S*r2d,mission.launch_site.lat_deg,0.001,' deg');
close('LZ-1 latitude',Flight.LAT_L*r2d,mission.landing_zone.lat_deg,0.001,' deg');
close('LZ-1 longitude offset',Flight.DLON_L*r2d,mission.landing_zone.lon_deg-mission.launch_site.lon_deg,0.001,' deg');

/* Default mission regression, not a certification envelope */
const sim=Flight.run({});
const events=Object.fromEntries(sim.events.map(event=>[event.name,event]));
const expected=mission.model_output;
const meco=events.MECO;
if(meco){
  relative('MECO altitude',meco.alt,expected.meco_altitude_m,0.02,' m');
  relative('MECO speed',meco.v,expected.meco_speed_m_s,0.02,' m/s');
}else{
  record('MECO present',NaN,0,0,'');
}
const orbit=sim.stats.orbit;
if(orbit){
  relative('insertion perigee',(orbit.rp-Flight.RE)/1000,expected.insertion_perigee_km,0.03,' km');
  relative('insertion apogee',(orbit.ra-Flight.RE)/1000,expected.insertion_apogee_km,0.03,' km');
  close('insertion inclination',orbit.inc,expected.insertion_inclination_deg,0.5,' deg');
  close('insertion eccentricity',orbit.ecc,expected.insertion_eccentricity,0.01,'');
}else{
  record('insertion elements present',NaN,0,0,'');
}
const td=events.TOUCHDOWN;
if(td){
  close('touchdown vertical speed',td.vV,expected.touchdown_vertical_m_s,0.2,' m/s');
  close('touchdown horizontal speed',td.vH,expected.touchdown_horizontal_m_s,0.1,' m/s');
  close('touchdown tilt',td.tilt,expected.touchdown_tilt_deg,0.5,' deg');
  close('touchdown pad offset',td.err,expected.touchdown_offset_m,3.0,' m');
}else{
  record('touchdown present',NaN,0,0,'');
}

const failures=checks.filter(check=>!check.ok);
const report={
  schema:'rocket-lab.standards-validation/1',
  reference:'data/reference/international-standard.json',
  passed:failures.length===0,
  checks,
  model:{
    meco_altitude_m:meco?meco.alt:null,
    meco_speed_m_s:meco?meco.v:null,
    insertion_perigee_km:orbit?(orbit.rp-Flight.RE)/1000:null,
    insertion_apogee_km:orbit?(orbit.ra-Flight.RE)/1000:null,
    insertion_inclination_deg:orbit?orbit.inc:null,
    insertion_eccentricity:orbit?orbit.ecc:null,
    touchdown_vertical_m_s:td?td.vV:null,
    touchdown_horizontal_m_s:td?td.vH:null,
    touchdown_tilt_deg:td?td.tilt:null,
    touchdown_offset_m:td?td.err:null
  }
};
fs.writeFileSync(path.join(root,'data','standards-validation.json'),JSON.stringify(report,null,2)+'\n');
if(failures.length){
  console.error(`standards checks failed: ${failures.length} of ${checks.length}`);
  process.exit(1);
}
console.log(`standards checks passed: ${checks.length} anchors; WGS-84, ISO 2533/1976, public Merlin/MVac and mass closure; `+
  `orbit ${((orbit.rp-Flight.RE)/1000).toFixed(0)}x${((orbit.ra-Flight.RE)/1000).toFixed(0)} km at ${orbit.inc.toFixed(1)} deg, `+
  `touchdown ${td.vV.toFixed(2)} m/s, ${td.err.toFixed(1)} m`);
