import {useEffect,useMemo,useRef} from 'react';
import {Canvas,useFrame} from '@react-three/fiber';
import * as THREE from 'three';
import World,{useVehicleTexture} from './World';
import {useLab} from './store';
import {sample} from './telemetry';
import CameraRig from './CameraRig';
import Trajectory from './Trajectory';
import Engine from './Engine';
import RenderOutput from './RenderOutput';
import FrameDriver from './FrameDriver';
import {physicsPosition,physicsRotation} from './coordinates';
import type {Telemetry} from './types';

function Strut({from,to,radius=.12}:{from:[number,number,number];to:[number,number,number];radius?:number}){
  const a=new THREE.Vector3(...from),b=new THREE.Vector3(...to),mid=a.clone().add(b).multiplyScalar(.5),q=new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0,1,0),b.clone().sub(a).normalize());
  return <mesh position={mid} quaternion={q}><cylinderGeometry args={[radius,radius,a.distanceTo(b),10]}/><meshStandardMaterial color="#85847f" metalness={.75} roughness={.38}/></mesh>;
}
function UpperStage(){return <>
  <mesh position={[0,3.3,0]}><cylinderGeometry args={[1.8,1.8,6.6,48]}/><meshStandardMaterial color="#e8e5da" metalness={.35} roughness={.4}/></mesh>
  <mesh position={[0,7.8,0]}><coneGeometry args={[1.8,2.4,48]}/><meshStandardMaterial color="#dedcd4" metalness={.45} roughness={.3}/></mesh>
  <mesh position={[0,.2,0]}><cylinderGeometry args={[1.81,1.81,.4,48]}/><meshStandardMaterial color="#393832" metalness={.7} roughness={.3}/></mesh>
</>;}
function Rocket({telemetry,ghost=false}:{telemetry:Telemetry;ghost?:boolean}){
  const root=useRef<THREE.Group>(null),legs=useRef<THREE.Group>(null),attached=useRef<THREE.Group>(null),released=useRef<THREE.Group>(null);
  const stageOffset=useMemo(()=>new THREE.Vector3(),[]);
  const map=useVehicleTexture();
  const material=useMemo(()=>new THREE.MeshStandardMaterial({map:ghost?null:map,color:ghost?'#72966e':'#ffffff',metalness:.35,roughness:.4,transparent:ghost,opacity:ghost?.25:1,depthWrite:!ghost}),[ghost,map]);
  useEffect(()=>()=>material.dispose(),[material]);
  useFrame(()=>{
    const {time}=useLab.getState(),f=sample(telemetry.frames,time);if(!root.current)return;
    root.current.position.set(...physicsPosition(f.position));physicsRotation(f.quaternion,root.current.quaternion);
    if(legs.current)legs.current.scale.setScalar(f.phase==='landing'?THREE.MathUtils.smoothstep(100-(f.position[2]-20),0,60):1-THREE.MathUtils.smoothstep(f.position[2]-20,2,20));
    const separation=telemetry.run.separation;
    if(attached.current)attached.current.visible=!separation||time<separation.t;
    if(released.current&&separation){
      const dt=Math.max(0,time-separation.t),p=separation.position,v=separation.velocity;
      physicsRotation(separation.quaternion,released.current.quaternion);
      stageOffset.set(0,20,0).applyQuaternion(released.current.quaternion);
      const height=p[2]+stageOffset.y+v[2]*dt-4.903325*dt*dt;
      released.current.visible=time>=separation.t&&height>0;
      released.current.position.set(p[0]+stageOffset.x+v[0]*dt,height,-p[1]+stageOffset.z-v[1]*dt);
    }
  });
  return <>
    <group ref={root}>
      <mesh material={material}><cylinderGeometry args={[1.8,1.8,35.6,64,1]}/></mesh>
      <mesh position={[0,18.8,0]} material={material}><cylinderGeometry args={[1.8,1.8,2,48]}/></mesh>
      <mesh position={[0,-18.2,0]}><cylinderGeometry args={[1.8,1.55,.8,48]}/><meshStandardMaterial color="#302f2b" metalness={.6} roughness={.4}/></mesh>
      {[-17.4,-11.5,9.5,17.8].map(y=><mesh key={y} position={[0,y,0]}><cylinderGeometry args={[1.815,1.815,.12,64]}/><meshStandardMaterial color="#6c6b65" metalness={.8} roughness={.3}/></mesh>)}
      {[0,1,2,3].map(i=><group key={i} rotation={[0,i*Math.PI/2+Math.PI/4,0]}>
        <mesh position={[1.84,-1,0]}><cylinderGeometry args={[.075,.075,26,10]}/><meshStandardMaterial color="#99988d" metalness={.7} roughness={.35}/></mesh>
        <mesh position={[2.6,13.5,0]}><boxGeometry args={[1.6,.2,2.4]}/><meshStandardMaterial color="#48473f" metalness={.7} roughness={.5}/></mesh>
        {[0,1,2,3,4].map(k=><mesh key={k} position={[2.6,13.65,(k-2)*.45]}><boxGeometry args={[1.5,.06,.05]}/><meshStandardMaterial color="#89867a" metalness={.7}/></mesh>)}
      </group>)}
      <group ref={legs}>{[0,1,2,3].map(i=><group key={i} rotation={[0,i*Math.PI/2+Math.PI/4,0]}>
        <Strut from={[1.75,-11,0]} to={[5.6,-19.75,0]} radius={.21}/>
        <Strut from={[1.78,-17,0]} to={[5.6,-19.75,0]}/>
        <mesh position={[5.6,-19.85,0]}><cylinderGeometry args={[.7,.8,.3,20]}/><meshStandardMaterial color="#373630" roughness={.8}/></mesh>
      </group>)}</group>
      {telemetry.run.mission==='combined'&&<group ref={attached} position={[0,20,0]}><UpperStage/></group>}
      {!ghost&&<Engine telemetry={telemetry}/>}
    </group>
    {telemetry.run.separation&&<group ref={released} visible={false}><UpperStage/></group>}
  </>;
}
function Exhaust({telemetry}:{telemetry:Telemetry}){
  const count=96;
  const geometry=useMemo(()=>{const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.Float32BufferAttribute(new Float32Array(count*3),3));g.setAttribute('alpha',new THREE.Float32BufferAttribute(new Float32Array(count),1));g.setAttribute('scale',new THREE.Float32BufferAttribute(new Float32Array(count),1));return g;},[]);
  const material=useMemo(()=>new THREE.ShaderMaterial({transparent:true,depthWrite:false,vertexShader:'attribute float alpha;attribute float scale;varying float opacity;void main(){vec4 mv=modelViewMatrix*vec4(position,1.);gl_Position=projectionMatrix*mv;gl_PointSize=clamp(scale*550./max(1.,-mv.z),1.,100.);opacity=alpha;}',fragmentShader:'varying float opacity;void main(){float r=length(gl_PointCoord-vec2(.5))*2.;gl_FragColor=vec4(vec3(.64,.61,.55),exp(-r*r*5.)*(1.-smoothstep(.6,1.,r))*opacity);\n#include <tonemapping_fragment>\n#include <colorspace_fragment>\n}'}),[]);
  const emission=useMemo(()=>new THREE.Vector3(),[]),direction=useMemo(()=>new THREE.Vector3(),[]),q=useMemo(()=>new THREE.Quaternion(),[]);
  useEffect(()=>()=>{geometry.dispose();material.dispose();},[geometry,material]);
  useFrame(()=>{
    const time=useLab.getState().time,p=geometry.attributes.position,a=geometry.attributes.alpha,scale=geometry.attributes.scale;
    for(let i=0;i<count;i++){
      const age=((time-i*.047)%4.5+4.5)%4.5,t=time-age;
      if(t<0){a.setX(i,0);continue;}
      const f=sample(telemetry.frames,t),angle=i*2.39996;
      q.set(f.quaternion[1],f.quaternion[2],f.quaternion[3],f.quaternion[0]);
      emission.set(0,0,-20).applyQuaternion(q);emission.x+=f.position[0];emission.y+=f.position[1];emission.z+=f.position[2];
      direction.set(-Math.tan(f.gimbal[0]),-Math.tan(f.gimbal[1]),-1).normalize().applyQuaternion(q);
      const spread=age*1.7,travel=age*18,height=emission.z+direction.z*travel,groundSpread=Math.max(0,-height)*.8;
      p.setXYZ(i,emission.x+direction.x*travel+Math.cos(angle)*(spread+groundSpread)+f.wind[0]*age,Math.max(.2,height)+age*.3,-emission.y-direction.y*travel+Math.sin(angle)*(spread+groundSpread)-f.wind[1]*age);
      scale.setX(i,1+age*3);a.setX(i,t<telemetry.run.duration?f.throttle*.16*(1-age/4.5):0);
    }
    p.needsUpdate=a.needsUpdate=scale.needsUpdate=true;
  });
  return <points geometry={geometry} material={material} frustumCulled={false}/>;
}
function FlightScene(){const telemetry=useLab(s=>s.telemetry),ghost=useLab(s=>s.ghost);return <><FrameDriver/><World/>{telemetry&&<><Rocket telemetry={telemetry}/><Exhaust telemetry={telemetry}/><Trajectory telemetry={telemetry}/></>}{ghost&&<><Rocket telemetry={ghost} ghost/><Trajectory telemetry={ghost} ghost/></>}<CameraRig/><RenderOutput/></>;}
export default function Scene(){return <Canvas frameloop="demand" camera={{position:[75,245,80],fov:40,near:.15,far:200000}} dpr={1} gl={{antialias:true,powerPreference:'high-performance',toneMapping:THREE.ACESFilmicToneMapping,toneMappingExposure:1,outputColorSpace:THREE.SRGBColorSpace}}><FlightScene/></Canvas>;}
