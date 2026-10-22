import {useEffect,useMemo,useRef} from 'react';
import {useFrame,useThree} from '@react-three/fiber';
import {OrbitControls} from '@react-three/drei';
import {Vector3,TOUCH} from 'three';
import {useLab} from './store';
import {sample} from './telemetry';
import {sceneSurfaceHeight} from './surface';
import {rocketFrameDistance,translateFollowFrame,mouseButtonsForTool,keepCameraAboveGround,CAMERA_MAX_DISTANCE} from './camera';

/** Orbit presets initialize once; follow translates without erasing manual framing. */
export default function CameraRig(){
  const mode=useLab(s=>s.camera),revision=useLab(s=>s.cameraRevision),telemetry=useLab(s=>s.telemetry),tool=useLab(s=>s.cameraTool),follow=useLab(s=>s.followRocket),commandRevision=useLab(s=>s.commandRevision);
  const {camera,size,gl,invalidate}=useThree();const orbit=useRef<React.ComponentRef<typeof OrbitControls>>(null);
  const initialized=useRef(''),command=useRef(-1),previous=useRef(new Vector3()),keys=useRef(new Set<string>());
  const anchor=useMemo(()=>new Vector3(),[]),position=useMemo(()=>new Vector3(),[]),right=useMemo(()=>new Vector3(),[]),forward=useMemo(()=>new Vector3(),[]);
  useEffect(()=>{
    const canvas=gl.domElement;canvas.tabIndex=0;canvas.setAttribute('aria-label','Interactive flight camera');
    const focus=()=>canvas.focus({preventScroll:true});
    const down=(e:KeyboardEvent)=>{if(document.activeElement!==canvas||e.ctrlKey||e.metaKey)return;if(['KeyW','KeyA','KeyS','KeyD','KeyQ','KeyE','ShiftLeft','ShiftRight'].includes(e.code)){e.preventDefault();keys.current.add(e.code);invalidate();}};
    const up=(e:KeyboardEvent)=>keys.current.delete(e.code),clear=()=>keys.current.clear();
    canvas.addEventListener('pointerdown',focus);window.addEventListener('keydown',down);window.addEventListener('keyup',up);window.addEventListener('blur',clear);canvas.addEventListener('blur',clear);
    return()=>{canvas.removeEventListener('pointerdown',focus);window.removeEventListener('keydown',down);window.removeEventListener('keyup',up);window.removeEventListener('blur',clear);canvas.removeEventListener('blur',clear);};
  },[gl,invalidate]);
  useFrame((_,dt)=>{
    if(!telemetry||!orbit.current)return;
    const controls=orbit.current,f=sample(telemetry.frames,useLab.getState().time),[x,y,h]=f.position;
    anchor.set(x,h,-y);
    const key=`${telemetry.run.id}/${mode}/${revision}`,fresh=initialized.current!==key,d=rocketFrameDistance(size.width/size.height,40,telemetry.run.mission==='combined'?32:25);
    if(fresh){
      initialized.current=key;controls.target.copy(anchor);
      if(mode==='Ground')position.set(x+100,2,-y+130);
      else if(mode==='Top-down')position.set(x+.01,h+d,-y+.01);
      else if(mode==='Mission'){
        const plan=telemetry.run.flight_plan,a=plan?.launch||[x,y],b=plan?.landing||[x,y],height=Math.max(plan?.separation_altitude||400,...telemetry.frames.map(frame=>frame.position[2]));
        controls.target.set((a[0]+b[0])/2,height*.4,-(a[1]+b[1])/2);
        const wide=Math.max(height,Math.hypot(a[0]-b[0],a[1]-b[1]),120)*1.7;
        position.copy(controls.target).add(new Vector3(wide,wide*.5,wide));
      }else if(mode==='Chase')position.set(x+d*.5,h+d*.3,-y+d*.87);
      else position.set(x+d*.71,h+d*.16,-y+d*.71);
      camera.position.copy(position);previous.current.copy(anchor);controls.update();
    }else if(follow){
      if(mode==='Ground'){controls.target.add(anchor.clone().sub(previous.current));previous.current.copy(anchor);controls.update();}
      else translateFollowFrame(camera.position,controls.target,previous.current,anchor);
    }
    else previous.current.copy(anchor);
    if(command.current!==commandRevision){
      command.current=commandRevision;
      const action=useLab.getState().cameraCommand;
      if(action){const offset=camera.position.clone().sub(controls.target),next=Math.max(.5,Math.min(CAMERA_MAX_DISTANCE,offset.length()*(action==='In'?.7:1/.7)));camera.position.copy(controls.target).add(offset.setLength(next));controls.update();}
    }
    if(keys.current.size){
      camera.getWorldDirection(forward);right.crossVectors(forward,camera.up).normalize();
      const k=keys.current,step=Math.max(8,camera.position.distanceTo(controls.target)*.6)*Math.min(dt,.05)*(k.has('ShiftLeft')||k.has('ShiftRight')?4:1);
      position.set(0,0,0).addScaledVector(forward,(Number(k.has('KeyW'))-Number(k.has('KeyS')))*step).addScaledVector(right,(Number(k.has('KeyD'))-Number(k.has('KeyA')))*step);
      position.y+=(Number(k.has('KeyE'))-Number(k.has('KeyQ')))*step;
      camera.position.add(position);controls.target.add(position);controls.update();invalidate();
    }
    keepCameraAboveGround(camera.position,controls.target,sceneSurfaceHeight(camera.position.x,camera.position.z,telemetry.run.flight_plan,useLab.getState().pad));
    const distance=Math.round(camera.position.distanceTo(controls.target));
    if(useLab.getState().cameraDistance!==distance)useLab.getState().set({cameraDistance:distance});
  });
  return <OrbitControls ref={orbit} makeDefault enableRotate enableZoom enablePan enableDamping={false} screenSpacePanning zoomToCursor mouseButtons={mouseButtonsForTool(tool)} touches={{ONE:TOUCH.ROTATE,TWO:TOUCH.DOLLY_PAN}} rotateSpeed={.65} zoomSpeed={1.2} panSpeed={1.4} minDistance={.5} maxDistance={CAMERA_MAX_DISTANCE} minPolarAngle={.001} maxPolarAngle={Math.PI/2+.05}/>;
}
