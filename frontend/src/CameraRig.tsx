import {useEffect,useMemo,useRef} from 'react';
import {useFrame,useThree} from '@react-three/fiber';
import {OrbitControls} from '@react-three/drei';
import {Vector3,TOUCH} from 'three';
import {useLab} from './store';
import {sample} from './telemetry';
import {sceneSurfaceHeight} from './surface';
import {rocketFrameDistance,translateFollowFrame,mouseButtonsForTool,keepCameraAboveGround,CAMERA_MAX_DISTANCE} from './camera';

/**
 * Professional Aerospace Multi-Angle Camera Rig
 * 
 * Features:
 * - 6 Dedicated Camera Modes: Orbit, Chase, Launch Tower, Onboard Nozzle, Landing Zone, Mission Corridor
 * - Smooth physical damping (dampens jitter and snapping)
 * - Dynamic velocity-aligned chase camera with aerodynamic lag
 * - Instant hotkeys (1-6 for cameras, Space for play/pause, F to focus, R to reset)
 * - Ground collision avoidance with surface height queries
 */
export default function CameraRig(){
  const mode=useLab(s=>s.camera),revision=useLab(s=>s.cameraRevision),telemetry=useLab(s=>s.telemetry),tool=useLab(s=>s.cameraTool),follow=useLab(s=>s.followRocket),commandRevision=useLab(s=>s.commandRevision);
  const {camera,size,gl,invalidate}=useThree();
  const orbit=useRef<React.ComponentRef<typeof OrbitControls>>(null);
  const initialized=useRef('');
  const command=useRef(-1);
  const previous=useRef(new Vector3());
  const keys=useRef(new Set<string>());
  
  const anchor=useMemo(()=>new Vector3(),[]);
  const position=useMemo(()=>new Vector3(),[]);
  const right=useMemo(()=>new Vector3(),[]);
  const forward=useMemo(()=>new Vector3(),[]);
  const chaseTarget=useMemo(()=>new Vector3(),[]);
  const chaseCamPos=useMemo(()=>new Vector3(),[]);

  useEffect(()=>{
    const canvas=gl.domElement;
    canvas.tabIndex=0;
    canvas.setAttribute('aria-label','Interactive flight camera');
    const focus=()=>canvas.focus({preventScroll:true});
    
    const down=(e:KeyboardEvent)=>{
      if((e.target as HTMLElement).matches('input,select,textarea')||e.ctrlKey||e.metaKey) return;
      
      // Numeric quick camera switching: 1-6
      if(e.code==='Digit1'||e.code==='Numpad1'){
        e.preventDefault();
        useLab.getState().set({camera:'Rocket',cameraRevision:useLab.getState().cameraRevision+1,followRocket:true});
        invalidate();
      }else if(e.code==='Digit2'||e.code==='Numpad2'){
        e.preventDefault();
        useLab.getState().set({camera:'Chase',cameraRevision:useLab.getState().cameraRevision+1,followRocket:true});
        invalidate();
      }else if(e.code==='Digit3'||e.code==='Numpad3'){
        e.preventDefault();
        useLab.getState().set({camera:'Tower',cameraRevision:useLab.getState().cameraRevision+1,followRocket:true});
        invalidate();
      }else if(e.code==='Digit4'||e.code==='Numpad4'){
        e.preventDefault();
        useLab.getState().set({camera:'Onboard',cameraRevision:useLab.getState().cameraRevision+1,followRocket:true});
        invalidate();
      }else if(e.code==='Digit5'||e.code==='Numpad5'){
        e.preventDefault();
        useLab.getState().set({camera:'Pad',cameraRevision:useLab.getState().cameraRevision+1,followRocket:true});
        invalidate();
      }else if(e.code==='Digit6'||e.code==='Numpad6'){
        e.preventDefault();
        useLab.getState().set({camera:'Mission',cameraRevision:useLab.getState().cameraRevision+1,followRocket:false});
        invalidate();
      }else if(e.code==='KeyT'){
        e.preventDefault();
        useLab.getState().set({camera:'Top-down',cameraRevision:useLab.getState().cameraRevision+1,followRocket:true});
        invalidate();
      }else if(e.code==='KeyF'){
        e.preventDefault();
        useLab.getState().set({cameraRevision:useLab.getState().cameraRevision+1,followRocket:true});
        invalidate();
      }else if(e.code==='KeyR'){
        e.preventDefault();
        useLab.getState().set({camera:'Rocket',cameraRevision:useLab.getState().cameraRevision+1,followRocket:true});
        invalidate();
      }else if(e.code==='Space'){
        e.preventDefault();
        useLab.getState().set({playing:!useLab.getState().playing});
        invalidate();
      }else if(['KeyW','KeyA','KeyS','KeyD','KeyQ','KeyE','ShiftLeft','ShiftRight'].includes(e.code)){
        e.preventDefault();
        keys.current.add(e.code);
        invalidate();
      }
    };
    
    const up=(e:KeyboardEvent)=>keys.current.delete(e.code);
    const clear=()=>keys.current.clear();
    
    canvas.addEventListener('pointerdown',focus);
    window.addEventListener('keydown',down);
    window.addEventListener('keyup',up);
    window.addEventListener('blur',clear);
    canvas.addEventListener('blur',clear);
    return()=>{
      canvas.removeEventListener('pointerdown',focus);
      window.removeEventListener('keydown',down);
      window.removeEventListener('keyup',up);
      window.removeEventListener('blur',clear);
      canvas.removeEventListener('blur',clear);
    };
  },[gl,invalidate]);

  useFrame((_,dt)=>{
    if(!telemetry||!orbit.current) return;
    const controls=orbit.current;
    const f=sample(telemetry.frames,useLab.getState().time);
    const [x,y,h]=f.position;
    anchor.set(x,h,-y);

    const key=`${telemetry.run.id}/${mode}/${revision}`;
    const fresh=initialized.current!==key;
    const d=rocketFrameDistance(size.width/size.height,40,telemetry.run.mission==='combined'?32:25);
    const plan=telemetry.run.flight_plan;
    const launchPos=plan?.launch||[0,0];
    const landingPos=plan?.landing||[1200,400];

    if(fresh){
      initialized.current=key;
      controls.target.copy(anchor);

      if(mode==='Tower'){
        // Launch tower camera looking at rocket
        position.set(launchPos[0]+15,28,-launchPos[1]+10);
      }else if(mode==='Pad'){
        // Landing zone camera looking at incoming booster
        position.set(landingPos[0]+42,3.5,-landingPos[1]+42);
      }else if(mode==='Onboard'){
        // Onboard camera mounted on interstage looking down toward engine nozzle
        position.set(x+1.8,h-4,-y+1.8);
        controls.target.set(x,h-24,-y);
      }else if(mode==='Chase'){
        // Aerodynamic chase cam behind vehicle
        const vx=f.velocity[0], vz=-f.velocity[1];
        const vLen=Math.hypot(vx,vz);
        const dirX=vLen>0.5?vx/vLen:0.71;
        const dirZ=vLen>0.5?vz/vLen:0.71;
        position.set(x-dirX*d*0.75, h+d*0.35, -y-dirZ*d*0.75);
      }else if(mode==='Ground'){
        position.set(x+100,2,-y+130);
      }else if(mode==='Top-down'){
        position.set(x+0.01,h+d,-y+0.01);
      }else if(mode==='Mission'){
        const a=launchPos, b=landingPos;
        const maxHeight=Math.max(plan?.separation_altitude||400,...telemetry.frames.map(frame=>frame.position[2]));
        controls.target.set((a[0]+b[0])/2,maxHeight*0.38,-(a[1]+b[1])/2);
        const wide=Math.max(maxHeight,Math.hypot(a[0]-b[0],a[1]-b[1]),120)*1.6;
        position.copy(controls.target).add(new Vector3(wide,wide*0.48,wide));
      }else{
        // Default Rocket Orbit view
        position.set(x+d*0.71,h+d*0.16,-y+d*0.71);
      }

      camera.position.copy(position);
      previous.current.copy(anchor);
      controls.update();
    }else if(follow){
      if(mode==='Tower'){
        // Fixed tower position, tracking rocket in flight
        position.set(launchPos[0]+15,28,-launchPos[1]+10);
        camera.position.copy(position);
        controls.target.lerp(anchor,Math.min(1,dt*10));
        controls.update();
      }else if(mode==='Pad'){
        // Fixed landing zone position, tracking incoming rocket
        position.set(landingPos[0]+42,3.5,-landingPos[1]+42);
        camera.position.copy(position);
        controls.target.lerp(anchor,Math.min(1,dt*10));
        controls.update();
      }else if(mode==='Onboard'){
        // Lock camera to rocket body looking down
        camera.position.set(x+1.8,h-4,-y+1.8);
        controls.target.set(x,h-24,-y);
        controls.update();
      }else if(mode==='Chase'){
        // Smoothly interpolate behind the rocket's motion
        const vx=f.velocity[0], vz=-f.velocity[1];
        const vLen=Math.hypot(vx,vz);
        const dirX=vLen>0.5?vx/vLen:0.71;
        const dirZ=vLen>0.5?vz/vLen:0.71;
        chaseCamPos.set(x-dirX*d*0.75, h+d*0.35, -y-dirZ*d*0.75);
        camera.position.lerp(chaseCamPos,Math.min(1,dt*6));
        chaseTarget.set(x+dirX*8, h+2, -y+dirZ*8);
        controls.target.lerp(chaseTarget,Math.min(1,dt*8));
        controls.update();
      }else if(mode==='Ground'){
        controls.target.add(anchor.clone().sub(previous.current));
        previous.current.copy(anchor);
        controls.update();
      }else{
        // Standard OrbitControls follow logic (preserves manual framing)
        translateFollowFrame(camera.position,controls.target,previous.current,anchor);
      }
    }else{
      previous.current.copy(anchor);
    }

    if(command.current!==commandRevision){
      command.current=commandRevision;
      const action=useLab.getState().cameraCommand;
      if(action){
        const offset=camera.position.clone().sub(controls.target);
        const next=Math.max(0.5,Math.min(CAMERA_MAX_DISTANCE,offset.length()*(action==='In'?0.7:1/0.7)));
        camera.position.copy(controls.target).add(offset.setLength(next));
        controls.update();
      }
    }

    if(keys.current.size){
      camera.getWorldDirection(forward);
      right.crossVectors(forward,camera.up).normalize();
      const k=keys.current;
      const step=Math.max(8,camera.position.distanceTo(controls.target)*0.6)*Math.min(dt,0.05)*(k.has('ShiftLeft')||k.has('ShiftRight')?4:1);
      position.set(0,0,0)
        .addScaledVector(forward,(Number(k.has('KeyW'))-Number(k.has('KeyS')))*step)
        .addScaledVector(right,(Number(k.has('KeyD'))-Number(k.has('KeyA')))*step);
      position.y+=(Number(k.has('KeyE'))-Number(k.has('KeyQ')))*step;
      camera.position.add(position);
      controls.target.add(position);
      controls.update();
      invalidate();
    }

    keepCameraAboveGround(camera.position,controls.target,sceneSurfaceHeight(camera.position.x,camera.position.z,telemetry.run.flight_plan,useLab.getState().pad));
    const distance=Math.round(camera.position.distanceTo(controls.target));
    if(useLab.getState().cameraDistance!==distance) useLab.getState().set({cameraDistance:distance});
  });

  return (
    <OrbitControls
      ref={orbit}
      makeDefault
      enableRotate={mode!=='Onboard'}
      enableZoom={mode!=='Onboard'}
      enablePan={mode!=='Onboard'}
      enableDamping={true}
      dampingFactor={0.08}
      screenSpacePanning
      zoomToCursor
      mouseButtons={mouseButtonsForTool(tool)}
      touches={{ONE:TOUCH.ROTATE,TWO:TOUCH.DOLLY_PAN}}
      rotateSpeed={0.7}
      zoomSpeed={1.2}
      panSpeed={1.2}
      minDistance={0.5}
      maxDistance={CAMERA_MAX_DISTANCE}
      minPolarAngle={0.001}
      maxPolarAngle={Math.PI/2+0.05}
    />
  );
}
