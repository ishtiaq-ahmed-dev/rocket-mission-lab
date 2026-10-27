import {useEffect,useMemo,useRef} from 'react';
import {useFrame} from '@react-three/fiber';
import * as THREE from 'three';
import {useLab} from './store';
import {sample,restHeight} from './telemetry';
import {gearDeployment,legAngle,legFoot,LEG_HINGE,LEG_LENGTH} from './gearKinematics';
import type {Telemetry} from './types';

function Leg({telemetry,ghost}:{telemetry:Telemetry;ghost:boolean}){
  const arm=useRef<THREE.Group>(null),foot=useRef<THREE.Group>(null),outer=useRef<THREE.Mesh>(null),rod=useRef<THREE.Mesh>(null);
  const base=useMemo(()=>new THREE.Vector3(1.92,-10.5,0),[]),end=useMemo(()=>new THREE.Vector3(),[]),axis=useMemo(()=>new THREE.Vector3(0,1,0),[]),direction=useMemo(()=>new THREE.Vector3(),[]);
  const shell=useMemo(()=>{
    const shape=new THREE.Shape();shape.moveTo(-.22,0);shape.lineTo(.22,0);shape.lineTo(.54,LEG_LENGTH*.74);shape.lineTo(.35,LEG_LENGTH);shape.lineTo(-.35,LEG_LENGTH);shape.lineTo(-.54,LEG_LENGTH*.74);shape.closePath();
    const geometry=new THREE.ExtrudeGeometry(shape,{depth:.25,bevelEnabled:true,bevelSize:.035,bevelThickness:.035,bevelSegments:1});geometry.translate(0,0,-.125);return geometry;
  },[]);
  useEffect(()=>()=>shell.dispose(),[shell]);
  useFrame(()=>{
    const f=sample(telemetry.frames,useLab.getState().time),amount=gearDeployment(f.phase,f.position[2]-restHeight(telemetry));
    if(arm.current)arm.current.rotation.z=-legAngle(amount);
    end.set(...legFoot(amount));
    if(foot.current){foot.current.position.copy(end);foot.current.rotation.z=Math.PI/2*(1-amount);}
    // Two overlapping telescopic members between the body and foot hardpoints.
    direction.copy(end).sub(base);const length=direction.length();direction.normalize();
    for(const [mesh,start,extent] of [[outer.current,0,length*.58],[rod.current,length*.42,length*.58]] as const){
      if(mesh){mesh.position.copy(base).addScaledVector(direction,start+extent/2);mesh.quaternion.setFromUnitVectors(axis,direction);mesh.scale.y=extent;}
    }
  });
  const translucent={transparent:ghost,opacity:ghost?.22:1,depthWrite:!ghost};
  return <>
    <group position={LEG_HINGE} ref={arm}>
      <mesh geometry={shell} castShadow={!ghost} receiveShadow><meshPhysicalMaterial color="#c3c4b9" metalness={.3} roughness={.55} {...translucent}/></mesh>
      <mesh rotation={[Math.PI/2,0,0]}><cylinderGeometry args={[.25,.25,.65,16]}/><meshStandardMaterial color="#657275" metalness={.8} roughness={.28} {...translucent}/></mesh>
    </group>
    <mesh position={base} rotation={[Math.PI/2,0,0]}><cylinderGeometry args={[.22,.22,.55,16]}/><meshStandardMaterial color="#657275" metalness={.8} roughness={.28} {...translucent}/></mesh>
    <mesh ref={outer} castShadow={!ghost}><cylinderGeometry args={[.16,.16,1,12]}/><meshPhysicalMaterial color="#788487" metalness={.8} roughness={.28} {...translucent}/></mesh>
    <mesh ref={rod} castShadow={!ghost}><cylinderGeometry args={[.095,.095,1,12]}/><meshPhysicalMaterial color="#c1c8c6" metalness={.85} roughness={.2} {...translucent}/></mesh>
    <group ref={foot}>
      <mesh castShadow={!ghost}><cylinderGeometry args={[.7,.82,.3,24]}/><meshStandardMaterial color="#303738" metalness={.45} roughness={.7} {...translucent}/></mesh>
      <mesh position={[0,.22,0]}><sphereGeometry args={[.23,16,10]}/><meshPhysicalMaterial color="#8f9b9c" metalness={.8} roughness={.24} {...translucent}/></mesh>
    </group>
  </>;
}
export default function LandingGear({telemetry,ghost=false}:{telemetry:Telemetry;ghost?:boolean}){
  return <group>{[0,1,2,3].map(i=><group key={i} rotation={[0,i*Math.PI/2+Math.PI/4,0]}><Leg telemetry={telemetry} ghost={ghost}/></group>)}</group>;
}
