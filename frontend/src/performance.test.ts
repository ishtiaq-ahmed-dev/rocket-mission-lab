import {expect,it} from 'vitest';
import {createTerrainMesh} from './TerrainMesh';
import {pixelRatioForQuality} from './capture';
import {useLab} from './store';
import {startPlaybackClock} from './frameScheduler';

it('defaults to a bounded buffer and 30 fps without changing playback speed',()=>{
 expect(useLab.getState().quality).toBe('Performance');expect(useLab.getState().frameLimit).toBe(30);
 expect(pixelRatioForQuality('Performance',1920,1080)**2*1920*1080).toBeCloseTo(1280*720);
 let now=0,elapsed=0,draws=0;let next:((t:number)=>void)|undefined;
 const stop=startPlaybackClock({now:()=>now,request:fn=>{next=fn;return 1;},cancel:()=>{next=undefined;},playing:()=>true,advance:dt=>{elapsed+=dt;},invalidate:()=>{draws++;}},30);
 for(let i=1;i<=144;i++){now=i*1000/144;const callback=next;next=undefined;callback?.(now);}
 expect(draws).toBe(30);expect(elapsed).toBeCloseTo(1,5);stop();
});

it('reduces terrain geometry while preserving upward, nondegenerate triangles',()=>{
 const light=createTerrainMesh('Performance'),normal=createTerrainMesh('Balanced');
 expect(light.index!.count).toBeLessThan(normal.index!.count);
 const positions=light.attributes.position,index=light.index!;
 for(let i=0;i<index.count;i+=3){
  const a=index.getX(i),b=index.getX(i+1),c=index.getX(i+2);
  const up=(positions.getZ(b)-positions.getZ(a))*(positions.getX(c)-positions.getX(a))-(positions.getX(b)-positions.getX(a))*(positions.getZ(c)-positions.getZ(a));
  if(up<=0)throw new Error(`Invalid performance terrain triangle ${i/3}`);
 }
 light.dispose();normal.dispose();
});
