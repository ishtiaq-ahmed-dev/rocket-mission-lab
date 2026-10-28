import {expect,it} from 'vitest';
import {recordedTimeline} from './flightTimeline';
import type {Telemetry} from './types';

it('uses physical release/separation/contact times and excludes launch contact',()=>{
 const data={run:{mission:'combined',separation:{t:22.4}},frames:[
  {t:0,phase:'takeoff',hold_down:true,clearance:0,throttle:0},
  {t:.5,phase:'takeoff',hold_down:false,release_time:.475,clearance:.02,throttle:.5},
  {t:22.4,phase:'landing',clearance:1500,throttle:0},
  {t:63.2,phase:'landing',clearance:30,throttle:.5},
  {t:81.1,phase:'landing',clearance:.01,throttle:.4},
  {t:81.2,phase:'landing',clearance:0,throttle:.4},
 ]} as unknown as Telemetry;
 const timeline=recordedTimeline(data);
 expect(timeline.liftoff).toBe(.475);expect(timeline.touchdown).toBe(81.2);
 expect(timeline.separation).toBe(22.4);expect(timeline.cutoff).toBe(22.4);
 expect(timeline.relight).toBe(63.2);expect(timeline.ascentSeconds).toBeCloseTo(21.925);
 expect(timeline.recoverySeconds).toBeCloseTo(58.8);
});

it('does not invent touchdown or liftoff for an airborne failed run',()=>{
 const data={run:{mission:'landing'},frames:[{t:0,phase:'landing',clearance:200,throttle:0},
  {t:90,phase:'landing',clearance:12,throttle:.4}]} as unknown as Telemetry;
 const result=recordedTimeline(data);expect(result.touchdown).toBeNull();expect(result.liftoff).toBeNull();
 expect(result.recoverySeconds).toBe(90);
});
