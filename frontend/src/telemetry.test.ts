import {describe,it,expect} from 'vitest';
import {parseTelemetry,sample,tilt} from './telemetry';
import type {Frame,Telemetry} from './types';
const frame:Frame={t:0,position:[0,0,220],velocity:[0,0,-10],quaternion:[1,0,0,0],angular_velocity:[0,0,0],fuel_mass:1000,mass:23000,wind:[0,0,0],throttle:.5,gimbal:[0,0],phase:'landing',reward:null};
const telemetry={schema_version:'1.0',rocket_length:40,initial_fuel:1000,run:{id:'test'},frames:[frame,{...frame,t:1,position:[10,0,210],quaternion:[Math.cos(.1),Math.sin(.1),0,0],fuel_mass:900}]} as Telemetry;
describe('versioned telemetry',()=>{
 it('accepts finite time-ordered frames',()=>expect(parseTelemetry(telemetry)).toBe(telemetry));
 it('rejects unsupported versions',()=>expect(()=>parseTelemetry({...telemetry,schema_version:'2.0'})).toThrow());
 it('rejects invalid quaternions',()=>expect(()=>parseTelemetry({...telemetry,frames:[{...frame,quaternion:[0,0,0,0]},telemetry.frames[1]]})).toThrow());
 it('rejects nonmonotonic timestamps',()=>expect(()=>parseTelemetry({...telemetry,frames:[frame,frame]})).toThrow());
 it('rejects nonfinite and wrong length vectors',()=>expect(()=>parseTelemetry({...telemetry,frames:[{...frame,position:[NaN,0,0]},telemetry.frames[1]]})).toThrow());
 it('interpolates physical state and fuel',()=>{const f=sample(telemetry.frames,.5);expect(f.position[0]).toBeCloseTo(5);expect(f.position[2]).toBeCloseTo(215);expect(f.fuel_mass).toBeCloseTo(950);expect(Math.hypot(...f.quaternion)).toBeCloseTo(1);expect(tilt(f)).toBeCloseTo(.1*180/Math.PI);});
 it('clamps to the first and last frames',()=>{expect(sample(telemetry.frames,-1)).toBe(frame);expect(sample(telemetry.frames,20)).toBe(telemetry.frames[1]);});
});
