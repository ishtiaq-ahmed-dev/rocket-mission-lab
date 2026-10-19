import {useMemo,useRef} from 'react';
import {useFrame} from '@react-three/fiber';
import * as THREE from 'three';
import {useLab} from './store';
import {sample} from './telemetry';
import type {Telemetry} from './types';

const flameVertex=`varying vec2 vUv;void main(){vUv=uv;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);}`;
const flameFragment=`
varying vec2 vUv;uniform float time;uniform float power;
float hash(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}
float noise(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.0-2.0*f);return mix(mix(hash(i),hash(i+vec2(1,0)),f.x),mix(hash(i+vec2(0,1)),hash(i+vec2(1)),f.x),f.y);}
void main(){
 float travel=1.0-vUv.y;float x=(vUv.x-.5)*2.0;
 float swirl=noise(vec2(x*5.0,travel*13.0-time*8.0));
 float width=mix(.33,.04,pow(travel,.85))*(.82+swirl*.3);
 float core=exp(-pow(x/(width*.6),2.0)*2.0);
 float envelope=exp(-pow(x/width,2.0)*2.4)*pow(1.0-travel,1.05);
 float diamonds=pow(max(0.0,cos(travel*62.0-time*.8)),12.0)*exp(-travel*3.2)*core;
 float turbulence=.6+.4*noise(vec2(x*12.0+time,travel*35.0-time*18.0));
 vec3 color=mix(vec3(.68,.23,.045),vec3(.42,.58,1.0),core*.7);
 color=mix(color,vec3(1.0,.91,.67),clamp(core*(1.0-travel)*.75+diamonds*.55,0.0,1.0));
 float alpha=(envelope*turbulence*.65+diamonds*.18)*power;
 gl_FragColor=vec4(color*1.9,alpha);
 #include <tonemapping_fragment>
 #include <colorspace_fragment>
}`;
export default function Engine({telemetry}:{telemetry:Telemetry}){
  const pivot=useRef<THREE.Group>(null),plume=useRef<THREE.Group>(null),light=useRef<THREE.PointLight>(null);
  const direction=useMemo(()=>new THREE.Vector3(),[]),down=useMemo(()=>new THREE.Vector3(0,-1,0),[]);
  const material=useMemo(()=>new THREE.ShaderMaterial({uniforms:{time:{value:0},power:{value:0}},vertexShader:flameVertex,fragmentShader:flameFragment,transparent:true,depthWrite:false,side:THREE.DoubleSide,blending:THREE.AdditiveBlending}),[]);
  useFrame(()=>{
    const {time}=useLab.getState(),f=sample(telemetry.frames,time),active=time<telemetry.run.duration&&f.throttle>.02;
    direction.set(-Math.tan(f.gimbal[0]),-1,Math.tan(f.gimbal[1])).normalize();pivot.current?.quaternion.setFromUnitVectors(down,direction);
    if(plume.current){plume.current.visible=active;plume.current.scale.y=.5+f.throttle*.9;}
    material.uniforms.time.value=time;material.uniforms.power.value=active?.5+f.throttle*.5:0;
    if(light.current)light.current.intensity=active?120*f.throttle:0;
  });
  return <group ref={pivot} position={[0,-18.1,0]}>
    <mesh position={[0,-.65,0]} castShadow><cylinderGeometry args={[.49,.83,1.3,64,14,true]}/><meshPhysicalMaterial color="#41413e" roughness={.38} metalness={.82} side={THREE.DoubleSide}/></mesh>
    <mesh position={[0,-1.28,0]} rotation={[Math.PI/2,0,0]}><torusGeometry args={[.83,.035,8,64]}/><meshStandardMaterial color="#716d61" metalness={.9} roughness={.3}/></mesh>
    <group ref={plume} position={[0,-1.3,0]}>{[0,Math.PI/3,Math.PI*2/3].map(angle=><mesh key={angle} position={[0,-6,0]} rotation={[0,angle,0]} material={material}><planeGeometry args={[4,12,1,1]}/></mesh>)}</group>
    <pointLight ref={light} position={[0,-2,0]} color="#ffc993" distance={40} decay={2}/>
  </group>;
}
