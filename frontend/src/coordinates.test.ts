import {it,expect} from 'vitest';
import {Euler,Quaternion,Vector3} from 'three';
import {physicsPosition,physicsRotation} from './coordinates';
it('renders physical translation and the booster thrust axis in the same right-handed frame',()=>{
 expect(physicsPosition([3,-4,200])).toEqual([3,200,4]);
 for(const angles of [[0,0,0],[.3,-.2,.9],[-.8,.5,-1.3],[1.4,-.4,2.4]]){
  const q=new Quaternion().setFromEuler(new Euler(...angles as [number,number,number]));
  const axis=new Vector3(0,0,1).applyQuaternion(q),expected=new Vector3(...physicsPosition(axis.toArray()));
  const rendered=new Vector3(0,1,0).applyQuaternion(physicsRotation([q.w,q.x,q.y,q.z]));
  expect(rendered.distanceTo(expected)).toBeLessThan(1e-12);
 }
});
