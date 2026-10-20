import {it,expect} from 'vitest';
import {PerspectiveCamera,Vector3} from 'three';
import {OrbitControls} from 'three-stdlib';
import {mouseButtonsForTool,keepCameraAboveGround} from './camera';

class Surface extends EventTarget{
 style={touchAction:''};clientWidth=1000;clientHeight=600;ownerDocument=new EventTarget();
 releasePointerCapture(){}
 getBoundingClientRect(){return {left:0,top:0,width:1000,height:600};}
}
function event(type:string,values:Record<string,number|string>){
 return Object.assign(new Event(type,{cancelable:true}),{pointerId:1,pointerType:'mouse',button:0,clientX:500,clientY:300,...values});
}
it('left-drag pans up/down/sideways after zoom and preserves the zoomed viewing angle',()=>{
 const surface=new Surface(),camera=new PerspectiveCamera(40,1000/600,1,12000);camera.position.set(80,60,80);
 const controls=new OrbitControls(camera,surface as unknown as HTMLElement);controls.target.set(0,40,0);controls.enableDamping=false;controls.zoomToCursor=true;controls.screenSpacePanning=true;controls.mouseButtons=mouseButtonsForTool('Pan');controls.update();camera.updateMatrixWorld();
 const originalDistance=camera.position.distanceTo(controls.target);
 for(let i=0;i<8;i++){surface.dispatchEvent(event('wheel',{deltaY:-100}));camera.updateMatrixWorld();}
 expect(camera.position.distanceTo(controls.target)).toBeLessThan(originalDistance);
 const before=camera.position.clone(),target=controls.target.clone(),offset=before.clone().sub(target);
 surface.dispatchEvent(event('pointerdown',{}));surface.ownerDocument.dispatchEvent(event('pointermove',{clientX:640,clientY:210}));surface.ownerDocument.dispatchEvent(event('pointerup',{clientX:640,clientY:210}));
 expect(camera.position.distanceTo(before)).toBeGreaterThan(1);
 expect(Math.abs(camera.position.y-before.y)).toBeGreaterThan(.5);
 expect(camera.position.clone().sub(controls.target).distanceTo(offset)).toBeLessThan(1e-9);
 expect(camera.position.clone().sub(before).distanceTo(controls.target.clone().sub(target))).toBeLessThan(1e-9);
 controls.dispose();
});
it('ground safety translates camera and target together instead of fighting the orbit angle',()=>{
 const camera=new Vector3(12,-3,7),target=new Vector3(0,20,0),offset=camera.clone().sub(target);
 keepCameraAboveGround(camera,target,2);
 expect(camera.y).toBe(3.5);expect(camera.clone().sub(target).distanceTo(offset)).toBe(0);
});
