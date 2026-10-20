import {describe,it,expect} from 'vitest';
import {largestClassicalSamples,resultSampleId} from './resultSamples';
import type {Result} from './types';

const sample=(values:Partial<Result>)=>({mission:'landing',method:'classical',level:4,scenario:'nominal',config_hash:'current',episodes:32,completed_at:0,...values}) as Result;
describe('evaluation batch identity',()=>{
 it('keeps one largest nominal batch per level under the chosen configuration',()=>{
  const values=[sample({episodes:20}),sample({episodes:10000,completed_at:1}),sample({episodes:10000,completed_at:2}),
   sample({level:1}),sample({config_hash:'archived',episodes:10000}),sample({scenario:'noise',episodes:10000}),sample({method:'rl',episodes:10000})];
  const chosen=largestClassicalSamples(values,'landing','current');
  expect(chosen.map(value=>[value.level,value.episodes,value.completed_at])).toEqual([[1,32,0],[4,10000,2]]);
  expect(largestClassicalSamples(values,'landing',undefined)).toEqual([]);
 });
 it('distinguishes repeated seeds and sample sizes without pooling their failures',()=>{
  const one=sample({episodes:20,seeds:[10000,10019],source_hash:'one',failures:{crash_speed:4}});
  const two=sample({episodes:256,seeds:[10000,10255],source_hash:'two',failures:{crash_speed:30}});
  expect(resultSampleId(one)).not.toBe(resultSampleId(two));
  expect(one.failures.crash_speed).toBe(4);expect(two.failures.crash_speed).toBe(30);
 });
});
