import {Quaternion,Vector3} from 'three';
import type {Frame} from './types';
import {physicsPosition,physicsRotation} from './coordinates';
import {ENGINE_PIVOT_Y,NOZZLE_LENGTH} from './vehicleDimensions';

const down=new Vector3(0,-1,0);
/** Same tan(gimbal) thrust axis as MuJoCo; render-local Y is physical Z. */
export function exhaustDirection(gimbal:number[],out=new Vector3()){
  return out.set(-Math.tan(gimbal[0]),-1,Math.tan(gimbal[1])).normalize();
}
export function nozzleRotation(gimbal:number[],out=new Quaternion()){
  return out.setFromUnitVectors(down,exhaustDirection(gimbal));
}
export function nozzleWorldPose(frame:Frame){
  const rotation=physicsRotation(frame.quaternion);
  const direction=exhaustDirection(frame.gimbal).applyQuaternion(rotation);
  const exit=new Vector3(0,ENGINE_PIVOT_Y,0).applyQuaternion(rotation)
    .add(new Vector3(...physicsPosition(frame.position))).addScaledVector(direction,NOZZLE_LENGTH);
  return {exit,direction};
}
/** Ray distance to the local flat prepared surface, measured from the exit. */
export function plumeLength(frame:Frame,surface:number,desired:number){
  const {exit,direction}=nozzleWorldPose(frame);
  if(direction.y>=-1e-8)return desired;
  return Math.max(0,Math.min(desired,(exit.y-surface-.04)/-direction.y));
}
