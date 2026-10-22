import {describe,it,expect} from 'vitest';
import {Euler,Quaternion,Vector3} from 'three';
import {exhaustDirection,nozzleRotation,nozzleWorldPose,plumeLength} from './engineKinematics';
import {physicsPosition} from './coordinates';
import type {Frame} from './types';

describe('rendered thrust geometry',()=>{
  it('aligns bell, flame and smoke opposite physical thrust for arbitrary attitudes and both gimbals',()=>{
    for(const angles of [[0,0,0],[.6,-.4,1.2],[-1,.7,-.3]])for(const gimbal of [[0,0],[.12,-.08],[-.1,.14]]){
      const q=new Quaternion().setFromEuler(new Euler(...angles as [number,number,number]));
      const frame={position:[30,-40,220],quaternion:[q.w,q.x,q.y,q.z],gimbal} as Frame;
      const body=new Vector3(-Math.tan(gimbal[0]),-Math.tan(gimbal[1]),-1).normalize();
      const expected=new Vector3(...physicsPosition(body.applyQuaternion(q).toArray()));
      const pose=nozzleWorldPose(frame);
      expect(pose.direction.distanceTo(expected)).toBeLessThan(1e-12);
      expect(new Vector3(0,-1,0).applyQuaternion(nozzleRotation(gimbal)).distanceTo(exhaustDirection(gimbal))).toBeLessThan(1e-12);
      const pivot=new Vector3(0,0,-17.9).applyQuaternion(q).add(new Vector3(...frame.position));
      const expectedExit=new Vector3(...physicsPosition(pivot.toArray())).addScaledVector(expected,1.5);
      expect(pose.exit.distanceTo(expectedExit)).toBeLessThan(1e-10);
    }
  });
  it('clips to the nozzle ray at tilted touchdown without rewriting its direction',()=>{
    const frame={position:[0,0,20],quaternion:[1,0,0,0],gimbal:[.1,-.1]} as Frame;
    const pose=nozzleWorldPose(frame),length=plumeLength(frame,0,30);
    expect(pose.exit.y+pose.direction.y*length).toBeCloseTo(.04,10);
    expect(plumeLength({...frame,position:[0,0,300]},0,30)).toBe(30);
  });
});
