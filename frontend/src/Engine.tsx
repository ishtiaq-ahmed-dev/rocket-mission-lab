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
 float diamond1=pow(max(0.,cos(distance*48.-time*12.)),12.)*exp(-distance*3.5);
 float diamond2=pow(max(0.,cos(distance*32.-time*8.)),8.)*exp(-distance*2.8);
 float diamonds=diamond1*.7+diamond2*.3;
 float ripple=sin(distance*42.-time*26.+sin(uvp.x*24.)*.35);
 float fade=pow(max(0.,1.-distance),1.6)*smoothstep(0.,.02,distance);
 vec3 coreColor=vec3(1.,.96,.82);
 vec3 midColor=vec3(1.,.58,.08);
 vec3 edgeColor=vec3(.85,.18,.02);
 vec3 hot=mix(edgeColor,midColor,exp(-distance*4.));
 hot=mix(hot,coreColor,pow(diamonds,1.5)+exp(-distance*10.)*.8);
 float alpha=fade*(.52+.1*ripple+diamonds*.28)*power;
 gl_FragColor=vec4(hot*(1.7+diamonds*1.5),alpha);
 #include <tonemapping_fragment>
 #include <colorspace_fragment>
}`;
const coreFragment=`varying vec2 uvp;uniform float time;uniform float power;
void main(){
 float d=1.-uvp.y;
 float edge=smoothstep(1.,.45,d);
 float bands=.75+.25*sin(d*64.-time*38.);
 float machDisks=pow(max(0.,cos(d*52.-time*10.)),14.)*exp(-d*4.);
 vec3 color=mix(vec3(1.,.65,.2),vec3(1.,.98,.92),smoothstep(.4,1.,d));
 color+=vec3(.4,.8,1.)*machDisks*1.2;
 gl_FragColor=vec4(color*1.6,edge*power*bands*(.8+machDisks*.4));
 #include <tonemapping_fragment>
 #include <colorspace_fragment>
}`;
const groundBlastFragment=`varying vec2 uvp;uniform float time;uniform float power;uniform float reach;
void main(){
 float r=length(uvp-vec2(.5))*2.;
 float wave=sin(r*20.-time*24.);
 float fade=smoothstep(1.,.2,r)*smoothstep(0.,.15,r);
 vec3 dust=mix(vec3(.7,.45,.2),vec3(1.,.65,.18),wave*.5+.5);
 gl_FragColor=vec4(dust*1.4,fade*power*reach*.6);
 #include <tonemapping_fragment>
 #include <colorspace_fragment>
}`;

export default function Engine({telemetry}:{telemetry:Telemetry}){
  const pivot=useRef<THREE.Group>(null),plume=useRef<THREE.Group>(null),outerPlumes=useRef<THREE.Group>(null),light=useRef<THREE.PointLight>(null),groundBlast=useRef<THREE.Mesh>(null);
  const material=useMemo(()=>new THREE.ShaderMaterial({uniforms:{time:{value:0},power:{value:0},expansion:{value:1}},vertexShader:depthVertex(vertex),fragmentShader:depthFragment(fragment),transparent:true,depthWrite:false,side:THREE.DoubleSide,blending:THREE.NormalBlending}),[]);
  const coreMaterial=useMemo(()=>new THREE.ShaderMaterial({uniforms:{time:{value:0},power:{value:0},expansion:{value:1}},vertexShader:depthVertex(vertex),fragmentShader:depthFragment(coreFragment),transparent:true,depthWrite:false,side:THREE.DoubleSide,blending:THREE.AdditiveBlending}),[]);
  const blastMaterial=useMemo(()=>new THREE.ShaderMaterial({uniforms:{time:{value:0},power:{value:0},reach:{value:0}},vertexShader:'varying vec2 uvp;void main(){uvp=uv;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);}',fragmentShader:groundBlastFragment,transparent:true,depthWrite:false,side:THREE.DoubleSide,blending:THREE.NormalBlending}),[]);
  
  const bell=useMemo(()=>new THREE.LatheGeometry([[.35,0],[.38,-.25],[.46,-.65],[.66,-1.1],[.88,-1.5]].map(([x,y])=>new THREE.Vector2(x,y)),48),[]);
  const outerBell=useMemo(()=>new THREE.LatheGeometry([[.28,0],[.31,-.2],[.38,-.52],[.53,-.88],[.7,-1.2]].map(([x,y])=>new THREE.Vector2(x,y)),32),[]);
  const inner=useMemo(()=>new THREE.LatheGeometry([[.3,-.02],[.32,-.3],[.4,-.7],[.57,-1.16],[.79,-1.5]].map(([x,y])=>new THREE.Vector2(x,y)),48),[]);
  
  useEffect(()=>()=>{material.dispose();coreMaterial.dispose();blastMaterial.dispose();bell.dispose();outerBell.dispose();inner.dispose();},[material,coreMaterial,blastMaterial,bell,outerBell,inner]);

  // 8 Outer engine angles in Octaweb layout
  const octawebAngles=useMemo(()=>Array.from({length:8},(_,i)=>i*Math.PI/4),[]);

  useFrame(()=>{
    const {time}=useLab.getState(),f=sample(telemetry.frames,time),active=time<telemetry.run.duration&&f.throttle>.02;
    if(pivot.current)nozzleRotation(f.gimbal,pivot.current.quaternion);
    const power=active?f.throttle:0;
    const isTakeoff=f.phase==='takeoff';
    
    if(plume.current){
      const expansion=1+Math.min(5.5,Math.max(0,f.position[2]-20)/18000);
      const flicker=1+.03*Math.sin(time*53)+.02*Math.sin(time*31);
      const baseScale=.3+f.throttle*1.35;
      const surface=sceneSurfaceHeight(f.position[0],-f.position[1],telemetry.run.flight_plan,useLab.getState().pad);
      const groundReach=plumeLength(f,surface,22*baseScale)/(22*baseScale);
      
      plume.current.visible=power>.004;
      plume.current.scale.set(flicker,baseScale*groundReach,flicker);
      material.uniforms.expansion.value=expansion;
      coreMaterial.uniforms.expansion.value=expansion;

      // Ground blast impingement when close to surface
      const altAGL=Math.max(0,f.position[2]-20-surface);
      if(groundBlast.current){
        const close=altAGL<28&&power>.05;
        groundBlast.current.visible=close;
        if(close){
          const reach=Math.max(0,1-altAGL/28);
          blastMaterial.uniforms.reach.value=reach;
          groundBlast.current.position.set(0,-(20+altAGL)+surface+.08,0);
          const blastScale=14+f.throttle*16+(1-reach)*10;
          groundBlast.current.scale.set(blastScale,blastScale,blastScale);
        }
      }
    }

    // Outer booster engines fire during takeoff / ascent
    if(outerPlumes.current){
      outerPlumes.current.visible=isTakeoff&&power>.05;
      const outerScale=(.25+f.throttle*1.1)*(1+.02*Math.sin(time*47));
      outerPlumes.current.scale.set(outerScale,outerScale,outerScale);
    }

    material.uniforms.time.value=time;material.uniforms.power.value=power;
    coreMaterial.uniforms.time.value=time;coreMaterial.uniforms.power.value=power;
    blastMaterial.uniforms.time.value=time;blastMaterial.uniforms.power.value=power;
    if(light.current){
      const multiplier=isTakeoff?1.8:1.0;
      light.current.intensity=power*(30+140*f.throttle)*multiplier*(.92+.08*Math.sin(time*45));
    }
  });

  return <group>
    {/* Center Gimbaling Engine */}
    <group ref={pivot} position={[0,ENGINE_PIVOT_Y,0]}>
      <mesh position={[0,.28,0]}><sphereGeometry args={[.52,20,12,0,Math.PI*2,0,Math.PI*.62]}/><meshStandardMaterial color="#3b3a35" metalness={.9} roughness={.32}/></mesh>
      <mesh geometry={bell}><meshStandardMaterial color="#4b4941" roughness={.38} metalness={.88} side={THREE.DoubleSide}/></mesh>
      <mesh geometry={inner} scale={[.985,.99,.985]}><meshStandardMaterial color="#1c1b18" roughness={.55} metalness={.72} side={THREE.DoubleSide}/></mesh>
      <mesh position={[0,-1.5,0]} rotation={[Math.PI/2,0,0]}><torusGeometry args={[.88,.045,10,56]}/><meshStandardMaterial color="#a29a83" metalness={.9} roughness={.25}/></mesh>
      {[.5,.8,1.1,1.35].map((y,i)=><mesh key={y} position={[0,-y,0]} rotation={[Math.PI/2,0,0]}><torusGeometry args={[.43+i*.14,.022,6,40]}/><meshStandardMaterial color="#918976" metalness={.85} roughness={.38}/></mesh>)}
      {Array.from({length:24},(_,i)=>{const a=i/24*Math.PI*2;return <mesh key={i} position={[Math.cos(a)*.61,-.83,Math.sin(a)*.61]} rotation={[Math.cos(a)*.34,0,Math.sin(a)*.34]}><cylinderGeometry args={[.016,.016,1.22,6]}/><meshStandardMaterial color="#8e8878" metalness={.78} roughness={.42}/></mesh>;})}
      
      {/* Center Plume */}
      <group ref={plume} position={[0,-NOZZLE_LENGTH,0]}>
        <mesh position={[0,-11,0]} material={material}><cylinderGeometry args={[.84,2.8,22,32,12,true]}/></mesh>
        <mesh position={[0,-5.5,0]} scale={[.72,.52,.72]} material={material}><cylinderGeometry args={[.8,1.9,20,24,8,true]}/></mesh>
        <mesh position={[0,-4.2,0]} material={coreMaterial}><cylinderGeometry args={[.52,.92,8.4,24,6,true]}/></mesh>
      </group>
      <pointLight ref={light} position={[0,-2.2,0]} color="#ffaa44" distance={50} decay={1.8}/>
    </group>

    {/* 8 Outer Engines in Octaweb Pattern */}
    <group position={[0,ENGINE_PIVOT_Y+.25,0]}>
      {octawebAngles.map((angle,i)=>{
        const ox=Math.cos(angle)*.98, oz=Math.sin(angle)*.98;
        return <group key={i} position={[ox,0,oz]}>
          <mesh geometry={outerBell}><meshStandardMaterial color="#44423b" roughness={.4} metalness={.85} side={THREE.DoubleSide}/></mesh>
          <mesh position={[0,-1.2,0]} rotation={[Math.PI/2,0,0]}><torusGeometry args={[.7,.035,8,36]}/><meshStandardMaterial color="#9e957e" metalness={.9}/></mesh>
          {/* Outer turbopump exhaust duct */}
          <mesh position={[Math.cos(angle)*.45,-.6,Math.sin(angle)*.45]} rotation={[0,0,.15]}><cylinderGeometry args={[.06,.06,.8,10]}/><meshStandardMaterial color="#2d2a26" metalness={.8}/></mesh>
        </group>;
      })}
    </group>

    {/* Outer Plumes during takeoff / ascent */}
    <group ref={outerPlumes} position={[0,ENGINE_PIVOT_Y-1.0,0]}>
      {octawebAngles.map((angle,i)=>{
        const ox=Math.cos(angle)*.98, oz=Math.sin(angle)*.98;
        return <group key={i} position={[ox,-NOZZLE_LENGTH*.7,oz]}>
          <mesh position={[0,-8,0]} scale={[.68,1,.68]} material={material}><cylinderGeometry args={[.68,2.2,16,20,8,true]}/></mesh>
          <mesh position={[0,-3.2,0]} scale={[.55,.6,.55]} material={coreMaterial}><cylinderGeometry args={[.42,.75,6.5,18,4,true]}/></mesh>
        </group>;
      })}
    </group>

    {/* Ground Blast & Dust Impingement Ring */}
    <mesh ref={groundBlast} rotation={[-Math.PI/2,0,0]} material={blastMaterial} visible={false}>
      <ringGeometry args={[.2,1,48]}/>
    </mesh>

    {/* Fixed actuator housings above the gimbal pivot */}
    <group position={[0,ENGINE_PIVOT_Y+.55,0]}>
      <mesh><cylinderGeometry args={[.56,.62,.4,24]}/><meshStandardMaterial color="#55534b" metalness={.82} roughness={.34}/></mesh>
      {[0,Math.PI/2,Math.PI,Math.PI*1.5].map(a=><group key={a} position={[Math.cos(a)*.78,0,Math.sin(a)*.78]} rotation={[Math.sin(a)*.55,0,-Math.cos(a)*.55]}><mesh position={[0,-.55,0]}><cylinderGeometry args={[.06,.06,1.1,10]}/><meshStandardMaterial color="#8f8878" metalness={.9} roughness={.28}/></mesh><mesh position={[0,.08,0]}><cylinderGeometry args={[.12,.12,.38,12]}/><meshStandardMaterial color="#393832" metalness={.55} roughness={.5}/></mesh></group>)}
    </group>
  </group>;
}
