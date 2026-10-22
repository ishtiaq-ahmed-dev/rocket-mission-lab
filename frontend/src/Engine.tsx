import {useEffect,useMemo,useRef} from 'react';
import {useFrame} from '@react-three/fiber';
import * as THREE from 'three';
import {useLab} from './store';
import {sample} from './telemetry';
import {ENGINE_PIVOT_Y,NOZZLE_LENGTH} from './vehicleDimensions';
import {sceneSurfaceHeight} from './surface';
import {nozzleRotation,plumeLength} from './engineKinematics';
import type {Telemetry} from './types';
import {depthVertex,depthFragment} from './shaderDepth';
const vertex=`varying vec2 uvp;uniform float expansion;void main(){uvp=uv;vec3 p=position;p.xz*=1.+(expansion-1.)*pow(1.-uv.y,.65);gl_Position=projectionMatrix*modelViewMatrix*vec4(p,1.);}`;
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
const coreFragment=`varying vec2 uvp;uniform float time;uniform float power;
void main(){
 float d=1.-uvp.y;
 float edge=smoothstep(1.,.55,d);
 float bands=.8+.2*sin(d*70.-time*40.);
 vec3 color=mix(vec3(1.,.62,.18),vec3(1.,.97,.86),smoothstep(.5,1.,d));
 gl_FragColor=vec4(color*1.4,edge*power*bands*.75);
 #include <tonemapping_fragment>
 #include <colorspace_fragment>
}`;
/** Axisymmetric exhaust follows the same opposite thrust vector as physics. */
export default function Engine({telemetry}:{telemetry:Telemetry}){
  const pivot=useRef<THREE.Group>(null),plume=useRef<THREE.Group>(null),light=useRef<THREE.PointLight>(null);
  // Normal blending preserves flame color against the requested white surface;
  // additive emission clips to white and disappears against that background.
  const material=useMemo(()=>new THREE.ShaderMaterial({uniforms:{time:{value:0},power:{value:0},expansion:{value:1}},vertexShader:depthVertex(vertex),fragmentShader:depthFragment(fragment),transparent:true,depthWrite:false,side:THREE.DoubleSide,blending:THREE.NormalBlending}),[]);
  const coreMaterial=useMemo(()=>new THREE.ShaderMaterial({uniforms:{time:{value:0},power:{value:0},expansion:{value:1}},vertexShader:depthVertex(vertex),fragmentShader:depthFragment(coreFragment),transparent:true,depthWrite:false,side:THREE.DoubleSide,blending:THREE.AdditiveBlending}),[]);
  const bell=useMemo(()=>new THREE.LatheGeometry([[.35,0],[.38,-.25],[.46,-.65],[.66,-1.1],[.88,-1.5]].map(([x,y])=>new THREE.Vector2(x,y)),48),[]);
  const inner=useMemo(()=>new THREE.LatheGeometry([[.3,-.02],[.32,-.3],[.4,-.7],[.57,-1.16],[.79,-1.5]].map(([x,y])=>new THREE.Vector2(x,y)),48),[]);
  useEffect(()=>()=>{material.dispose();coreMaterial.dispose();bell.dispose();inner.dispose();},[material,coreMaterial,bell,inner]);
  useFrame(()=>{
    const {time}=useLab.getState(),f=sample(telemetry.frames,time),active=time<telemetry.run.duration&&f.throttle>.02;
    // Gimbal bell follows the physical thrust axis: exhaust points opposite the
    // body-frame force vector (x east, y north, z up -> local x, z, y).
    // Actuator rates are already integrated by physics. A second visual lag
    // makes the bell disagree with the force and changes its pose while paused.
    if(pivot.current)nozzleRotation(f.gimbal,pivot.current.quaternion);
    const power=active?f.throttle:0;
    if(plume.current){
      const expansion=1+Math.min(5.5,Math.max(0,f.position[2]-20)/18000);
      const flicker=1+.025*Math.sin(time*53)+.018*Math.sin(time*31);
      const baseScale=.3+f.throttle*1.25;
      // The plume is anchored at the nozzle exit, so truncating its length keeps
      // the flame from visibly passing through the pad or terrain on final descent.
      const surface=sceneSurfaceHeight(f.position[0],-f.position[1],telemetry.run.flight_plan,useLab.getState().pad);
      const groundReach=plumeLength(f,surface,22*baseScale)/(22*baseScale);
      plume.current.visible=power>.004;
      plume.current.scale.set(flicker,baseScale*groundReach,flicker);
      material.uniforms.expansion.value=expansion;coreMaterial.uniforms.expansion.value=expansion;
    }
    material.uniforms.time.value=time;material.uniforms.power.value=power;
    coreMaterial.uniforms.time.value=time;coreMaterial.uniforms.power.value=power;
    if(light.current)light.current.intensity=power*(25+115*f.throttle)*(.94+.06*Math.sin(time*45));
  });
  return <group>
    <group ref={pivot} position={[0,ENGINE_PIVOT_Y,0]}>
      {/* heat shield / gimbal ball */}
      <mesh position={[0,.28,0]}><sphereGeometry args={[.52,20,12,0,Math.PI*2,0,Math.PI*.62]}/><meshStandardMaterial color="#3b3a35" metalness={.9} roughness={.32}/></mesh>
      <mesh geometry={bell}><meshStandardMaterial color="#4b4941" roughness={.38} metalness={.88} side={THREE.DoubleSide}/></mesh>
      <mesh geometry={inner} scale={[.985,.99,.985]}><meshStandardMaterial color="#1c1b18" roughness={.55} metalness={.72} side={THREE.DoubleSide}/></mesh>
      <mesh position={[0,-1.5,0]} rotation={[Math.PI/2,0,0]}><torusGeometry args={[.88,.045,10,56]}/><meshStandardMaterial color="#a29a83" metalness={.9} roughness={.25}/></mesh>
      {[.5,.8,1.1,1.35].map((y,i)=><mesh key={y} position={[0,-y,0]} rotation={[Math.PI/2,0,0]}><torusGeometry args={[.43+i*.14,.022,6,40]}/><meshStandardMaterial color="#918976" metalness={.85} roughness={.38}/></mesh>)}
      {/* regenerative cooling tubes and actuator hardpoints */}
      {Array.from({length:24},(_,i)=>{const a=i/24*Math.PI*2;return <mesh key={i} position={[Math.cos(a)*.61,-.83,Math.sin(a)*.61]} rotation={[Math.cos(a)*.34,0,Math.sin(a)*.34]}><cylinderGeometry args={[.016,.016,1.22,6]}/><meshStandardMaterial color="#8e8878" metalness={.78} roughness={.42}/></mesh>;})}
      <group ref={plume} position={[0,-NOZZLE_LENGTH,0]}>
        <mesh position={[0,-11,0]} material={material}><cylinderGeometry args={[.84,2.8,22,32,12,true]}/></mesh>
        <mesh position={[0,-5.5,0]} scale={[.72,.52,.72]} material={material}><cylinderGeometry args={[.8,1.9,20,24,8,true]}/></mesh>
        <mesh position={[0,-4.2,0]} material={coreMaterial}><cylinderGeometry args={[.52,.92,8.4,24,6,true]}/></mesh>
      </group>
      <pointLight ref={light} position={[0,-2.2,0]} color="#ffb750" distance={38} decay={2}/>
    </group>
    {/* fixed actuator housings above the gimbal pivot */}
    <group position={[0,ENGINE_PIVOT_Y+.55,0]}>
      <mesh><cylinderGeometry args={[.56,.62,.4,24]}/><meshStandardMaterial color="#55534b" metalness={.82} roughness={.34}/></mesh>
      {[0,Math.PI/2,Math.PI,Math.PI*1.5].map(a=><group key={a} position={[Math.cos(a)*.78,0,Math.sin(a)*.78]} rotation={[Math.sin(a)*.55,0,-Math.cos(a)*.55]}><mesh position={[0,-.55,0]}><cylinderGeometry args={[.06,.06,1.1,10]}/><meshStandardMaterial color="#8f8878" metalness={.9} roughness={.28}/></mesh><mesh position={[0,.08,0]}><cylinderGeometry args={[.12,.12,.38,12]}/><meshStandardMaterial color="#393832" metalness={.55} roughness={.5}/></mesh></group>)}
    </group>
  </group>;
}
