/** Frame the entire 40 m vehicle, including deployed legs, at every attitude. */
export const CAMERA_MAX_DISTANCE=100000;
export function rocketFrameDistance(aspect:number,fov=40,radius=25){
  const vertical=fov*Math.PI/360;
  const horizontal=Math.atan(Math.tan(vertical)*Math.max(.25,aspect));
  return radius/Math.sin(Math.min(vertical,horizontal))*1.28;
}

import type {Vector3} from 'three';
import {MOUSE} from 'three';
export const mouseButtonsForTool=(tool:'Rotate'|'Pan')=>({LEFT:tool==='Pan'?MOUSE.PAN:MOUSE.ROTATE,MIDDLE:MOUSE.DOLLY,RIGHT:tool==='Pan'?MOUSE.ROTATE:MOUSE.PAN});
export function keepCameraAboveGround(camera:Vector3,target:Vector3,ground:number){
  const correction=Math.max(0,Math.max(.5,ground+1.5)-camera.y);
  camera.y+=correction;target.y+=correction;
}
export function translateFollowFrame(camera:Vector3,target:Vector3,previous:Vector3,current:Vector3){
  const delta=current.clone().sub(previous);camera.add(delta);target.add(delta);previous.copy(current);
}
