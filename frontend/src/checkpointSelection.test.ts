import {describe,it,expect} from 'vitest';
import {measuredCheckpoint} from './checkpointSelection';
import type {Checkpoint,Result} from './types';
const physical={vehicle:{mass:1},world:{gravity:9.8},mission:{pad:5}};
const checkpoint=(id:string,successes:number,reward:number,steps=100,job=id):Checkpoint=>({id,job_id:job,mission:'landing',algorithm:'PPO',steps,successes,evaluation_episodes:20,success_rate:successes/20,mean_reward:reward,qualification:'pilot',config:physical});
describe('measured automatic checkpoint selection',()=>{
 it('selects measured success across objectives instead of highest reward or newest step',()=>{
  const values=[checkpoint('latest',0,10000,500),checkpoint('best',3,-100,300),checkpoint('other-objective',1,20000,400)];
  expect(measuredCheckpoint(values,[],physical,'landing',4)?.id).toBe('best');
 });
 it('rejects changed physics and pending evaluations',()=>{
  const incompatible={...checkpoint('different-physics',20,100),config:{...physical,vehicle:{mass:2}}};
  const pending={...checkpoint('pending',20,100),evaluation_episodes:0};
  expect(measuredCheckpoint([incompatible,pending,checkpoint('valid',1,0)],[],physical,'landing',4)?.id).toBe('valid');
 });
 it('uses physical error rather than incomparable reward when successes tie',()=>{
  const values=[checkpoint('rough',0,10000),checkpoint('gentle',0,-10000)];
  const results=[{checkpoint_id:'rough',scenario:'nominal',episodes:20,mean_touchdown_speed:10,mean_tilt:10,mean_pad_distance:15},{checkpoint_id:'gentle',scenario:'nominal',episodes:20,mean_touchdown_speed:2,mean_tilt:3,mean_pad_distance:8}] as Result[];
  expect(measuredCheckpoint(values,results,physical,'landing',4)?.id).toBe('gentle');
 });
 it('keeps earlier slots within the selected job and preserves best for slot four',()=>{
  const values=[checkpoint('early',0,-10,100,'chosen'),checkpoint('middle',0,-5,200,'chosen'),checkpoint('best',3,0,300,'chosen'),checkpoint('regressed',0,10,400,'chosen')];
  expect(measuredCheckpoint(values,[],physical,'landing',1)?.id).toBe('early');
  expect(measuredCheckpoint(values,[],physical,'landing',4)?.id).toBe('best');
 });
 it('does not mistake low terminal ascent speed for a good landing metric',()=>{
  const values=[{...checkpoint('slow-crash',0,1000,100),mission:'takeoff' as const},{...checkpoint('newer',0,-1000,200),mission:'takeoff' as const}];
  const results=[{checkpoint_id:'slow-crash',scenario:'nominal',episodes:20,mean_touchdown_speed:1,mean_tilt:1,mean_pad_distance:1},{checkpoint_id:'newer',scenario:'nominal',episodes:20,mean_touchdown_speed:25,mean_tilt:4,mean_pad_distance:4}] as Result[];
  expect(measuredCheckpoint(values,results,physical,'takeoff',4)?.id).toBe('newer');
 });
 it('uses the larger sample and its uncertainty instead of a lucky small checkpoint batch',()=>{
  const values=[checkpoint('pad',5,0,600),checkpoint('balanced',6,100,700),checkpoint('small-new',4,1000,800)];
  const results=[{checkpoint_id:'pad',scenario:'nominal',episodes:256,successes:45,mean_touchdown_speed:2.6,mean_tilt:4,mean_pad_distance:6.9},{checkpoint_id:'balanced',scenario:'nominal',episodes:256,successes:29,mean_touchdown_speed:2.3,mean_tilt:4.8,mean_pad_distance:8.9}] as Result[];
  expect(measuredCheckpoint(values,results,physical,'landing',4)?.id).toBe('pad');
 });
});
