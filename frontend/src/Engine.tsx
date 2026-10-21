import {useEffect,useMemo,useRef} from 'react';
import {useFrame} from '@react-three/fiber';
import * as THREE from 'three';
import {useLab} from './store';
import {sample} from './telemetry';
import type {Telemetry} from './types';
const vertex=`varying vec2 uvp;void main(){uvp=uv;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);}`;
const fragment=`varying vec2 uvp;uniform float time;uniform float power;
void main(){
 float distance=1.-uvp.y;
 float ripple=sin(distance*48.-time*28.+sin(uvp.x*25.)*.25);
 float diamonds=pow(max(0.,cos(distance*54.)),10.)*exp(-distance*4.);
 float fade=pow(max(0.,1.-distance),1.8)*smoothstep(0.,.025,distance);
 vec3 hot=mix(vec3(1.,.24,.025),vec3(1.,.89,.62),exp(-distance*5.));
 float alpha=fade*(.48+.08*ripple+diamonds*.18)*power;
 gl_FragColor=vec4(hot*(1.6+diamonds),alpha);
 #include <tonemapping_fragment>
 #include <colorspace_fragment>
}`;
/** Axisymmetric exhaust follows the same opposite thrust vector as physics. */
export default function Engine({telemetry}:{telemetry:Telemetry}){
  const pivot=useRef<THREE.Group>(null),plume=useRef<THREE.Group>(null),light=useRef<THREE.PointLight>(null);
  const direction=useMemo(()=>new THREE.Vector3(),[]),down=useMemo(()=>new THREE.Vector3(0,-1,0),[]);
  // Normal blending preserves flame color against the requested white surface;
  // additive emission clips to white and disappears against that background.
  const material=useMemo(()=>new THREE.ShaderMaterial({uniforms:{time:{value:0},power:{value:0}},vertexShader:vertex,fragmentShader:fragment,transparent:true,depthWrite:false,side:THREE.DoubleSide,blending:THREE.NormalBlending}),[]);
  const bell=useMemo(()=>new THREE.LatheGeometry([[.35,0],[.38,-.25],[.46,-.65],[.66,-1.1],[.88,-1.5]].map(([x,y])=>new THREE.Vector2(x,y)),48),[]);
  useEffect(()=>()=>{material.dispose();bell.dispose();},[material,bell]);
  useFrame(()=>{
    const {time}=useLab.getState(),f=sample(telemetry.frames,time),active=time<telemetry.run.duration&&f.throttle>.02;
    direction.set(-Math.tan(f.gimbal[0]),-1,Math.tan(f.gimbal[1])).normalize();pivot.current?.quaternion.setFromUnitVectors(down,direction);
    if(plume.current){plume.current.visible=active;const expansion=1+Math.min(1500,Math.max(0,f.position[2]-20))/3000;plume.current.scale.set(expansion,.35+f.throttle*.85,expansion);}
    material.uniforms.time.value=time;material.uniforms.power.value=active?.5+.5*f.throttle:0;
    if(light.current)light.current.intensity=active?65*f.throttle:0;
  });
  return <group ref={pivot} position={[0,-18.5,0]}>
    <mesh geometry={bell}><meshStandardMaterial color="#4b4941" roughness={.4} metalness={.85} side={THREE.DoubleSide}/></mesh>
    {[.5,.8,1.1,1.4].map((y,i)=><mesh key={y} position={[0,-y,0]} rotation={[Math.PI/2,0,0]}><torusGeometry args={[.43+i*.14,.025,6,40]}/><meshStandardMaterial color="#8b8270" metalness={.85} roughness={.4}/></mesh>)}
    <group ref={plume} position={[0,-1.5,0]}>
      <mesh position={[0,-10,0]} material={material}><cylinderGeometry args={[.8,2.8,20,32,12,true]}/></mesh>
      <mesh position={[0,-5,0]} scale={[.7,.5,.7]} material={material}><cylinderGeometry args={[.8,1.8,20,24,8,true]}/></mesh>
    </group>
    <pointLight ref={light} position={[0,-2,0]} color="#ffb750" distance={30} decay={2}/>
  </group>;
}
