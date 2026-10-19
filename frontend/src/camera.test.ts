import {describe,it,expect} from 'vitest';
import {rocketFrameDistance,translateFollowFrame} from './camera';
import {Vector3} from 'three';
describe('full rocket camera framing',()=>{
  for(const aspect of [.5,.77,1,1.6,2.4])it(`retains full vehicle inside the frustum at aspect ${aspect}`,()=>{
    const distance=rocketFrameDistance(aspect);
    const halfV=40*Math.PI/360,halfH=Math.atan(Math.tan(halfV)*aspect);
    const angularRadius=Math.asin(25/distance);
    expect(angularRadius).toBeLessThan(Math.min(halfV,halfH));
    expect(distance).toBeGreaterThan(25);
  });
});
it('preserves the user orbit angle, distance and pan when the rocket moves or scrubs',()=>{
 const position=new Vector3(83,232,-62),target=new Vector3(4,202,7),previous=new Vector3(0,200,0);
 const offset=position.clone().sub(target),pan=target.clone().sub(previous);
 for(const anchor of [new Vector3(3,185,-4),new Vector3(200,600,-310),new Vector3(0,20,0)]){
  translateFollowFrame(position,target,previous,anchor);
  expect(position.clone().sub(target).distanceTo(offset)).toBeLessThan(1e-10);
  expect(target.clone().sub(anchor).distanceTo(pan)).toBeLessThan(1e-10);
 }
});
