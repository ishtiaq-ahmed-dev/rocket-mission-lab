import {useMemo,useRef} from 'react';
import {useFrame,useThree} from '@react-three/fiber';
import {OrbitControls} from '@react-three/drei';
import {Vector3} from 'three';
import {useLab} from './store';
import {sample} from './telemetry';
import {rocketFrameDistance,translateFollowFrame} from './camera';
import {terrainHeight} from './terrain';

/** Presets set the initial composition; gestures keep control until Reset view.
 * Following translates camera AND orbit target equally, preserving the user's
 * azimuth, elevation, zoom and pan instead of overwriting them each frame. */
export default function CameraRig(){
  const mode=useLab(s=>s.camera),revision=useLab(s=>s.cameraRevision),telemetry=useLab(s=>s.telemetry);
  const {camera,size}=useThree();const orbit=useRef<React.ComponentRef<typeof OrbitControls>>(null);
  const initialized=useRef(''),manual=useRef(false),previous=useRef(new Vector3());
  const anchor=useMemo(()=>new Vector3(),[]),position=useMemo(()=>new Vector3(),[]);
  useFrame(()=>{
    if(!telemetry||!orbit.current)return;
    const f=sample(telemetry.frames,useLab.getState().time),[x,z,h]=f.position;
    anchor.set(x,h-3,-z);
    const key=`${telemetry.run.id}/${mode}/${revision}/${size.width}/${size.height}`;
    const fresh=initialized.current!==key,d=rocketFrameDistance(size.width/size.height);
    if(fresh){
      manual.current=false;initialized.current=key;
      if(mode==='Ground')position.set(x+95,8,-z+110);
      else if(mode==='Top-down')position.set(x+.01,h+d,-z+.01);
      else if(mode==='Cinematic')position.set(x+d*.85,h+d*.3,-z+d*.65);
      else if(mode==='Chase')position.set(x+d*.5,h+d*.3,-z+d*.87);
      else position.set(x+d*.71,h+d*.16,-z+d*.71);
      camera.position.copy(position);orbit.current.target.copy(anchor);previous.current.copy(anchor);orbit.current.update();
    }else if(mode!=='Free orbit'){
      translateFollowFrame(camera.position,orbit.current.target,previous.current,anchor);
      // Cinematic motion yields immediately to any user gesture.
      if(mode==='Cinematic'&&!manual.current&&useLab.getState().playing){
        const offset=camera.position.clone().sub(orbit.current.target);offset.applyAxisAngle(new Vector3(0,1,0),.00025);camera.position.copy(orbit.current.target).add(offset);
      }
    }
    const landX=camera.position.x+(useLab.getState().pad==='Ship'?850:0);
    camera.position.y=Math.max(.5,terrainHeight(landX,camera.position.z)+1.5,camera.position.y);
  });
  return <OrbitControls ref={orbit} makeDefault enabled enableRotate enableZoom enablePan enableDamping dampingFactor={.12} rotateSpeed={.6} zoomSpeed={.75} panSpeed={.65} minDistance={9} maxDistance={2200} minPolarAngle={.015} maxPolarAngle={Math.PI-.015} onStart={()=>{manual.current=true;}}/>;
}
