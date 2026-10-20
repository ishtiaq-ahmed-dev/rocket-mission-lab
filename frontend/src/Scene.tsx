import {useLayoutEffect,useMemo,useRef} from 'react';
import {Canvas,useFrame,useThree} from '@react-three/fiber';
import * as THREE from 'three';
import {mergeGeometries} from 'three/addons/utils/BufferGeometryUtils.js';
import World,{useVehicleTexture} from './World';
import {useLab} from './store';
import {sample} from './telemetry';
import {terrainHeight} from './terrain';
import CameraRig from './CameraRig';
import Trajectory from './Trajectory';
import Engine from './Engine';
import RenderOutput from './RenderOutput';
import FrameDriver from './FrameDriver';
import {physicsPosition,physicsRotation} from './coordinates';
import type {Telemetry} from './types';

function Strut({from,to,radius=.12,color='#8b9698'}:{from:[number,number,number];to:[number,number,number];radius?:number;color?:string}){
  const a=new THREE.Vector3(...from),b=new THREE.Vector3(...to),mid=a.clone().add(b).multiplyScalar(.5),q=new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0,1,0),b.clone().sub(a).normalize());
  return <mesh position={mid} quaternion={q} castShadow><cylinderGeometry args={[radius,radius,a.distanceTo(b),16]}/><meshPhysicalMaterial color={color} metalness={.8} roughness={.24}/></mesh>;
}
function Rocket({telemetry,ghost=false}:{telemetry:Telemetry;ghost?:boolean}){
  const root=useRef<THREE.Group>(null);const map=useVehicleTexture();
  const fin=useMemo(()=>{
    const parts:THREE.BufferGeometry[]=[];
    for(let k=0;k<7;k++){parts.push(new THREE.BoxGeometry(2.15,.13,.045).translate(0,0,(k-3)*.3));parts.push(new THREE.BoxGeometry(.045,.15,1.95).translate((k-3)*.32,0,0));}
    for(const n of [-1,1])parts.push(new THREE.BoxGeometry(.08,.24,2.08).translate(n*1.08,0,0));
    const geometry=mergeGeometries(parts);parts.forEach(part=>part.dispose());return geometry;
  },[]);
  const legShell=useMemo(()=>{const shape=new THREE.Shape();shape.moveTo(1.73,-11);shape.lineTo(2.28,-11.5);shape.lineTo(6.2,-19.6);shape.lineTo(5.5,-19.5);shape.lineTo(2,-14.1);shape.closePath();const geometry=new THREE.ExtrudeGeometry(shape,{depth:.42,bevelEnabled:true,bevelThickness:.04,bevelSize:.04,bevelSegments:2,steps:1});geometry.translate(0,0,-.21);return geometry;},[]);
  const material=useMemo(()=>new THREE.MeshPhysicalMaterial({map:ghost?null:map,color:ghost?'#79d5df':'#ffffff',metalness:ghost?.1:.2,roughness:.33,clearcoat:.22,clearcoatRoughness:.35,transparent:ghost,opacity:ghost?.22:1,depthWrite:!ghost}),[ghost,map]);
  useFrame(()=>{
    const {time}=useLab.getState(),f=sample(telemetry.frames,time);if(!root.current)return;
    root.current.position.set(...physicsPosition(f.position));physicsRotation(f.quaternion,root.current.quaternion);
  });
  return <group ref={root}>
    <mesh material={material} castShadow={!ghost} receiveShadow><cylinderGeometry args={[1.8,1.8,34,96,16]}/></mesh>
    <mesh position={[0,18,0]} material={material} castShadow><cylinderGeometry args={[1.15,1.8,2,64]}/></mesh>
    <mesh position={[0,19.3,0]} material={material} castShadow><sphereGeometry args={[1.15,48,24,0,Math.PI*2,0,Math.PI/2]}/></mesh>
    <mesh position={[0,-17.6,0]} castShadow><cylinderGeometry args={[1.8,1.5,1.4,64]}/><meshPhysicalMaterial color={ghost?'#71dae6':'#333637'} metalness={.65} roughness={.42} transparent={ghost} opacity={ghost?.22:1}/></mesh>
    {[-16.7,-12.5,8,15.3].map(y=><mesh key={y} position={[0,y,0]}><cylinderGeometry args={[1.812,1.812,.07,96]}/><meshPhysicalMaterial color="#7f8781" metalness={.7} roughness={.3} transparent={ghost} opacity={ghost?.2:1}/></mesh>)}
    {[0,1,2,3].map(i=><group key={i} rotation={[0,i*Math.PI/2+Math.PI/4,0]}>
      <mesh geometry={legShell} castShadow receiveShadow><meshPhysicalMaterial color="#c3c4b9" metalness={.3} roughness={.55}/></mesh>
      <Strut from={[1.78,-16.6,0]} to={[6.2,-19.65,0]} radius={.1} color="#9ca8aa"/>
      <Strut from={[2.8,-13.4,0]} to={[5.2,-17.6,0]} radius={.085} color="#c1c8c6"/>
      <mesh position={[1.85,-11.3,0]} castShadow><sphereGeometry args={[.25,20,16]}/><meshPhysicalMaterial color="#68777a" metalness={.8} roughness={.25}/></mesh>
      <mesh position={[6.2,-19.85,0]} castShadow><cylinderGeometry args={[.72,.82,.3,32]}/><meshPhysicalMaterial color="#2f3637" metalness={.5} roughness={.65}/></mesh>
      <mesh position={[2.65,12,0]} geometry={fin} castShadow><meshPhysicalMaterial color="#59676c" metalness={.8} roughness={.24}/></mesh>
      <mesh position={[1.81,-1,0]}><cylinderGeometry args={[.065,.065,20,12]}/><meshPhysicalMaterial color="#b6beb8" metalness={.6} roughness={.4}/></mesh>
    </group>)}
    {!ghost&&<Engine telemetry={telemetry}/>}
  </group>;
}
function Exhaust({telemetry}:{telemetry:Telemetry}){
  const count=150;const {size,camera,gl}=useThree();
  const geometry=useMemo(()=>{const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.Float32BufferAttribute(new Float32Array(count*3),3));g.setAttribute('alpha',new THREE.Float32BufferAttribute(new Float32Array(count),1));g.setAttribute('scale',new THREE.Float32BufferAttribute(new Float32Array(count),1));return g;},[]);
  const material=useMemo(()=>new THREE.ShaderMaterial({transparent:true,depthWrite:false,uniforms:{pixelScale:{value:500}},vertexShader:'attribute float alpha; attribute float scale; varying float opacity; uniform float pixelScale; void main(){vec4 mv=modelViewMatrix*vec4(position,1.0); gl_Position=projectionMatrix*mv; gl_PointSize=clamp(scale*pixelScale/max(1.0,-mv.z),1.0,170.0);opacity=alpha;}',fragmentShader:'varying float opacity; void main(){float r=length(gl_PointCoord-vec2(0.5))*2.0; float a=exp(-r*r*4.0)*(1.0-smoothstep(0.7,1.0,r))*opacity;gl_FragColor=vec4(vec3(0.69,0.69,0.64),a);\n#include <tonemapping_fragment>\n#include <colorspace_fragment>\n}'}),[]);
  const emission=useMemo(()=>new THREE.Vector3(),[]),direction=useMemo(()=>new THREE.Vector3(),[]),quaternion=useMemo(()=>new THREE.Quaternion(),[]);
  useLayoutEffect(()=>{material.uniforms.pixelScale.value=size.height*gl.getPixelRatio()/(2*Math.tan((camera as THREE.PerspectiveCamera).fov*Math.PI/360));},[size,camera,gl,material]);
  useFrame(()=>{
    const t=useLab.getState().time,now=sample(telemetry.frames,t),position=geometry.attributes.position,alpha=geometry.attributes.alpha,scale=geometry.attributes.scale;
    for(let i=0;i<count;i++){
      const age=(i/count*4.2+t*.07)%4.2,emitted=sample(telemetry.frames,Math.max(0,t-age)),a=i*2.39996,width=.4+age*2.6;
      const throttle=emitted.throttle*(t>=age?1:0)*(t<telemetry.run.duration+age?1:0);
      quaternion.set(emitted.quaternion[1],emitted.quaternion[2],emitted.quaternion[3],emitted.quaternion[0]);
      emission.set(0,0,-telemetry.rocket_length/2+.5).applyQuaternion(quaternion).add(new THREE.Vector3(...emitted.position));
      direction.set(-Math.tan(emitted.gimbal[0]),-Math.tan(emitted.gimbal[1]),-1).normalize().applyQuaternion(quaternion);
      const x=emission.x+direction.x*age*12+Math.cos(a)*width+emitted.wind[0]*age*.5,z=-emission.y-direction.y*age*12+Math.sin(a)*width-emitted.wind[1]*age*.5,y=emission.z+direction.z*age*12;
      const ground=useLab.getState().pad==='Ship'?-1.2:terrainHeight(x,z);
      position.setXYZ(i,x,Math.max(ground+.35,y),z);scale.setX(i,1.5+age*4);alpha.setX(i,throttle*.22*(1-age/4.2));
      if(i>100&&now.phase==='landing'&&now.position[2]<35&&now.throttle>.1){const dustAge=(i-100)/50;position.setXYZ(i,now.position[0]+Math.cos(a)*dustAge*30,.3+dustAge*2,-now.position[1]+Math.sin(a)*dustAge*30);scale.setX(i,3+dustAge*12);alpha.setX(i,now.throttle*.1*(1-dustAge));}
    }position.needsUpdate=alpha.needsUpdate=scale.needsUpdate=true;
  });
  return <points geometry={geometry} material={material} frustumCulled={false}/>;
}
function FlightScene(){
  const telemetry=useLab(s=>s.telemetry),ghost=useLab(s=>s.ghost);
  return <><FrameDriver/><World/>{telemetry&&<><Rocket telemetry={telemetry}/><Exhaust telemetry={telemetry}/><Trajectory telemetry={telemetry}/></>}{ghost&&<><Rocket telemetry={ghost} ghost/><Trajectory telemetry={ghost} ghost/></>}<CameraRig/><RenderOutput/></>;
}
export default function Scene(){return <Canvas frameloop="demand" shadows camera={{position:[75,245,80],fov:40,near:1,far:12000}} dpr={1} gl={{antialias:true,powerPreference:'high-performance',toneMapping:THREE.ACESFilmicToneMapping,toneMappingExposure:1.05,outputColorSpace:THREE.SRGBColorSpace}}><FlightScene/></Canvas>;}
