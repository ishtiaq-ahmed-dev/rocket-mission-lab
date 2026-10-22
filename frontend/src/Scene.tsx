import {useEffect,useMemo,useRef} from 'react';
import {Canvas,useFrame} from '@react-three/fiber';
import * as THREE from 'three';
import World,{useVehicleTexture} from './World';
import {useLab} from './store';
import {sample} from './telemetry';
import CameraRig from './CameraRig';
import Trajectory from './Trajectory';
import Engine from './Engine';
import LandingGear from './LandingGear';
import {sceneSurfaceHeight} from './surface';
import {nozzleWorldPose} from './engineKinematics';
import RenderOutput from './RenderOutput';
import FrameDriver from './FrameDriver';
import {physicsPosition,physicsRotation} from './coordinates';
import type {Telemetry} from './types';
import {depthVertex,depthFragment} from './shaderDepth';

function UpperStage(){return <>
  <mesh position={[0,3.3,0]}><cylinderGeometry args={[1.8,1.8,6.6,48]}/><meshStandardMaterial color="#e8e5da" metalness={.35} roughness={.4}/></mesh>
  <mesh position={[0,7.8,0]}><coneGeometry args={[1.8,2.4,48]}/><meshStandardMaterial color="#dedcd4" metalness={.45} roughness={.3}/></mesh>
  <mesh position={[0,.2,0]}><cylinderGeometry args={[1.81,1.81,.4,48]}/><meshStandardMaterial color="#393832" metalness={.7} roughness={.3}/></mesh>
</>;}
function Rocket({telemetry,ghost=false}:{telemetry:Telemetry;ghost?:boolean}){
  const root=useRef<THREE.Group>(null),attached=useRef<THREE.Group>(null),released=useRef<THREE.Group>(null);
  const stageOffset=useMemo(()=>new THREE.Vector3(),[]);
  const map=useVehicleTexture(!ghost);
  const material=useMemo(()=>new THREE.MeshPhysicalMaterial({map:ghost?null:map,color:ghost?'#79d5df':'#ffffff',metalness:ghost?.1:.2,roughness:.33,clearcoat:.22,clearcoatRoughness:.35,transparent:ghost,opacity:ghost?.22:1,depthWrite:!ghost}),[ghost,map]);
  useEffect(()=>()=>material.dispose(),[material]);
  useFrame(()=>{
    const {time}=useLab.getState(),f=sample(telemetry.frames,time);if(!root.current)return;
    root.current.position.set(...physicsPosition(f.position));physicsRotation(f.quaternion,root.current.quaternion);
    const separation=telemetry.run.separation;
    if(attached.current)attached.current.visible=!separation||time<separation.t;
    if(released.current&&separation){
      const stage=f.upper_stage;
      if(stage){
        physicsRotation(stage.quaternion,released.current.quaternion);
        stageOffset.set(0,-4.5,0).applyQuaternion(released.current.quaternion);
        released.current.position.set(...physicsPosition(stage.position)).add(stageOffset);
        released.current.visible=time>=separation.t&&!stage.impacted;
        return;
      }
      // Archived flights lack independent stage telemetry. Their explicitly
      // labelled ideal-ballistic preview remains readable for comparison.
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
      <mesh material={material} castShadow={!ghost} receiveShadow><cylinderGeometry args={[1.8,1.8,34,96,16]}/></mesh>
      {telemetry.run.mission!=='combined'?<>
        <mesh position={[0,18,0]} material={material} castShadow={!ghost}><cylinderGeometry args={[1.15,1.8,2,64]}/></mesh>
        <mesh position={[0,19.3,0]} material={material} castShadow={!ghost}><sphereGeometry args={[1.15,48,24,0,Math.PI*2,0,Math.PI/2]}/></mesh>
      </>:<mesh position={[0,18.5,0]} castShadow={!ghost}><cylinderGeometry args={[1.8,1.8,3,64]}/><meshPhysicalMaterial color="#333637" metalness={.5} roughness={.42} transparent={ghost} opacity={ghost?.22:1}/></mesh>}
      <mesh position={[0,-17.6,0]} castShadow={!ghost}><cylinderGeometry args={[1.8,1.5,1.4,64]}/><meshPhysicalMaterial color={ghost?'#71dae6':'#333637'} metalness={.65} roughness={.42} transparent={ghost} opacity={ghost?.22:1}/></mesh>
      {[-16.7,-12.5,8,15.3].map(y=><mesh key={y} position={[0,y,0]}><cylinderGeometry args={[1.812,1.812,.07,96]}/><meshPhysicalMaterial color="#7f8781" metalness={.7} roughness={.3} transparent={ghost} opacity={ghost?.2:1}/></mesh>)}
      {[0,1,2,3].map(i=><group key={i} rotation={[0,i*Math.PI/2+Math.PI/4,0]}>
        <mesh position={[1.81,-1,0]}><cylinderGeometry args={[.065,.065,20,12]}/><meshPhysicalMaterial color="#b6beb8" metalness={.6} roughness={.4} transparent={ghost} opacity={ghost?.22:1}/></mesh>
      </group>)}
      <LandingGear telemetry={telemetry} ghost={ghost}/>
      {telemetry.run.mission==='combined'&&<group ref={attached} position={[0,20,0]}><UpperStage/></group>}
      {!ghost&&<Engine telemetry={telemetry}/>}
    </group>
    {telemetry.run.separation&&<group ref={released} visible={false}><UpperStage/></group>}
  </>;
}
function Exhaust({telemetry}:{telemetry:Telemetry}){
  const quality=useLab(s=>s.quality),count=quality==='Performance'?48:96;
  const geometry=useMemo(()=>{const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.Float32BufferAttribute(new Float32Array(count*3),3));g.setAttribute('alpha',new THREE.Float32BufferAttribute(new Float32Array(count),1));g.setAttribute('scale',new THREE.Float32BufferAttribute(new Float32Array(count),1));g.setAttribute('heat',new THREE.Float32BufferAttribute(new Float32Array(count),1));return g;},[count]);
  const material=useMemo(()=>new THREE.ShaderMaterial({transparent:true,depthWrite:false,vertexShader:depthVertex('attribute float alpha;attribute float scale;attribute float heat;varying float opacity;varying float vHeat;void main(){vec4 mv=modelViewMatrix*vec4(position,1.);gl_Position=projectionMatrix*mv;gl_PointSize=clamp(scale*620./max(1.,-mv.z),1.,130.);opacity=alpha;vHeat=heat;}'),fragmentShader:depthFragment('varying float opacity;varying float vHeat;void main(){float r=length(gl_PointCoord-vec2(.5))*2.;vec3 smoke=vec3(.62,.59,.54);vec3 ember=mix(vec3(1.,.3,.04),vec3(1.,.73,.28),vHeat);vec3 color=mix(smoke,ember,pow(vHeat,2.2)*.85);float core=exp(-r*r*5.)*(1.-smoothstep(.6,1.,r));gl_FragColor=vec4(color,core*opacity);\n#include <tonemapping_fragment>\n#include <colorspace_fragment>\n}') }),[]);
  useEffect(()=>()=>{geometry.dispose();material.dispose();},[geometry,material]);
  useFrame(()=>{
    const time=useLab.getState().time,p=geometry.attributes.position,a=geometry.attributes.alpha,scale=geometry.attributes.scale,heat=geometry.attributes.heat;
    for(let i=0;i<count;i++){
      const emissionOffset=i*4.5/count,t=emissionOffset+Math.floor((time-emissionOffset)/4.5)*4.5,age=time-t;
      if(t<0){a.setX(i,0);continue;}
      const f=sample(telemetry.frames,t),angle=i*2.39996;
      const {exit:emission,direction}=nozzleWorldPose(f);
      const spread=age*1.7,travel=age*18,height=emission.y+direction.y*travel,groundSpread=Math.max(0,-height)*.8;
      const x=emission.x+direction.x*travel+Math.cos(angle)*(spread+groundSpread)+f.wind[0]*age;
      const z=emission.z+direction.z*travel+Math.sin(angle)*(spread+groundSpread)-f.wind[1]*age;
      p.setXYZ(i,x,Math.max(sceneSurfaceHeight(x,z,telemetry.run.flight_plan,useLab.getState().pad)+.2,height)+age*.3,z);
      const ambient=Math.exp(-Math.max(0,f.position[2]-20)/8500);
      scale.setX(i,1+age*3);heat.setX(i,Math.max(0,1-age/1.7));a.setX(i,t<telemetry.run.duration?f.throttle*.16*(1-age/4.5)*ambient:0);
    }
    p.needsUpdate=a.needsUpdate=scale.needsUpdate=heat.needsUpdate=true;
  });
  return <points geometry={geometry} material={material} frustumCulled={false}/>;
}
function FlightScene(){const telemetry=useLab(s=>s.telemetry),ghost=useLab(s=>s.ghost);return <><FrameDriver/><World/>{telemetry&&<><Rocket telemetry={telemetry}/><Exhaust telemetry={telemetry}/><Trajectory telemetry={telemetry}/></>}{ghost&&<><Rocket telemetry={ghost} ghost/><Trajectory telemetry={ghost} ghost/></>}<CameraRig/><RenderOutput/></>;}
export default function Scene(){const quality=useLab(s=>s.quality);return <Canvas frameloop="demand" shadows={quality!=='Performance'} camera={{position:[75,245,80],fov:40,near:.15,far:3000000}} dpr={1} gl={{antialias:true,logarithmicDepthBuffer:true,powerPreference:'default',toneMapping:THREE.ACESFilmicToneMapping,toneMappingExposure:1.05,outputColorSpace:THREE.SRGBColorSpace}}><FlightScene/></Canvas>;}
