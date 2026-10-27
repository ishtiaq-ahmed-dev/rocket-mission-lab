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
  <mesh position={[0,3.3,0]} castShadow><cylinderGeometry args={[1.8,1.8,6.6,48]}/><meshStandardMaterial color="#f0eee6" metalness={.35} roughness={.38}/></mesh>
  {/* Payload fairing / nosecone */}
  <mesh position={[0,7.8,0]} castShadow><coneGeometry args={[1.8,2.4,48]}/><meshStandardMaterial color="#e5e2d6" metalness={.45} roughness={.3}/></mesh>
  <mesh position={[0,9.05,0]}><sphereGeometry args={[.18,16,12]}/><meshStandardMaterial color="#353b3f" metalness={.7}/></mesh>
  {/* Second stage vacuum engine bell */}
  <mesh position={[0,-.5,0]}><cylinderGeometry args={[.45,1.2,1.6,32,1,true]}/><meshStandardMaterial color="#2d3032" metalness={.9} roughness={.25} side={THREE.DoubleSide}/></mesh>
  <mesh position={[0,.2,0]}><cylinderGeometry args={[1.81,1.81,.4,48]}/><meshStandardMaterial color="#26282a" metalness={.7} roughness={.35}/></mesh>
</>;}

function GridFins({telemetry,ghost}:{telemetry:Telemetry;ghost:boolean}){
  const fins=useRef<(THREE.Group|null)[]>([]);
  useFrame(()=>{
    const {time}=useLab.getState(),f=sample(telemetry.frames,time);
    const ang=f.angular_velocity;
    fins.current.forEach((fin,i)=>{
      if(!fin)return;
      // Articulate grid fins based on roll/pitch/yaw aerodynamic control
      const deflection=(i%2===0?ang[0]:ang[1])*.4+Math.sin(time*8+i)*.02;
      fin.rotation.z=THREE.MathUtils.clamp(deflection,-.35,.35);
    });
  });
  return <group position={[0,15.2,0]}>
    {[0,Math.PI/2,Math.PI,Math.PI*1.5].map((angle,i)=>{
      const x=Math.cos(angle)*1.81,z=Math.sin(angle)*1.81;
      return <group key={i} position={[x,0,z]} rotation={[0,-angle,0]}>
        {/* Actuator spindle & base housing */}
        <mesh position={[0,0,0]} rotation={[0,0,Math.PI/2]}><cylinderGeometry args={[.14,.14,.38,16]}/><meshStandardMaterial color="#4a4f52" metalness={.85} roughness={.3}/></mesh>
        <mesh position={[.16,0,0]}><boxGeometry args={[.18,.4,.28]}/><meshStandardMaterial color="#383d40" metalness={.8} roughness={.4}/></mesh>
        
        {/* Articulated Titanium Waffle Grid Fin */}
        <group ref={el=>fins.current[i]=el} position={[.3,0,0]}>
          {/* Outer titanium frame */}
          <mesh castShadow={!ghost}><boxGeometry args={[.06,1.4,1.1]}/><meshStandardMaterial color="#8a948e" metalness={.88} roughness={.32}/></mesh>
          {/* Inner waffle grid cells (open intersecting lattice blades) */}
          {[-.42,-.14,.14,.42].map(y=><mesh key={y} position={[0,y,0]}><boxGeometry args={[.05,.04,1.06]}/><meshStandardMaterial color="#7a857e" metalness={.9} roughness={.35}/></mesh>)}
          {[-.35,-.12,.12,.35].map(z=><mesh key={z} position={[0,0,z]}><boxGeometry args={[.05,1.36,.04]}/><meshStandardMaterial color="#7a857e" metalness={.9} roughness={.35}/></mesh>)}
        </group>
      </group>;
    })}
  </group>;
}

function RCSThrusters({telemetry}:{telemetry:Telemetry}){
  const puffs=useRef<(THREE.Mesh|null)[]>([]);
  useFrame(()=>{
    const {time}=useLab.getState(),f=sample(telemetry.frames,time);
    const active=Math.hypot(f.angular_velocity[0],f.angular_velocity[1],f.angular_velocity[2])>.03&&time<telemetry.run.duration;
    puffs.current.forEach(p=>{
      if(!p)return;
      p.visible=active;
      if(active){
        const scale=.6+.4*Math.sin(time*45);
        p.scale.set(scale,scale,scale);
      }
    });
  });
  return <group position={[0,16.2,0]}>
    {[Math.PI/4,3*Math.PI/4,5*Math.PI/4,7*Math.PI/4].map((angle,i)=>{
      const x=Math.cos(angle)*1.81,z=Math.sin(angle)*1.81;
      return <group key={i} position={[x,0,z]} rotation={[0,-angle,0]}>
        {/* Pod housing */}
        <mesh><boxGeometry args={[.14,.26,.26]}/><meshStandardMaterial color="#2d3236" metalness={.7}/></mesh>
        {/* Nozzle horns */}
        <mesh position={[.08,.06,0]} rotation={[0,0,-Math.PI/2]}><coneGeometry args={[.04,.1,8]}/><meshStandardMaterial color="#788085" metalness={.85}/></mesh>
        {/* Animated Cold Gas Nitrogen Puff */}
        <mesh ref={el=>puffs.current[i]=el} position={[.25,.06,0]} rotation={[0,0,-Math.PI/2]} visible={false}>
          <coneGeometry args={[.22,.6,12,1,true]}/>
          <meshBasicMaterial color="#ffffff" transparent opacity={.45}/>
        </mesh>
      </group>;
    })}
  </group>;
}

function Rocket({telemetry,ghost=false}:{telemetry:Telemetry;ghost?:boolean}){
  const root=useRef<THREE.Group>(null),attached=useRef<THREE.Group>(null),released=useRef<THREE.Group>(null);
  const stageOffset=useMemo(()=>new THREE.Vector3(),[]);
  const map=useVehicleTexture(!ghost);
  const material=useMemo(()=>new THREE.MeshPhysicalMaterial({map:ghost?null:map,color:ghost?'#79d5df':'#ffffff',metalness:ghost?.1:.18,roughness:.32,clearcoat:.3,clearcoatRoughness:.25,transparent:ghost,opacity:ghost?.22:1,depthWrite:!ghost}),[ghost,map]);
  useEffect(()=>()=>material.dispose(),[material]);
  useFrame(()=>{
    const {time}=useLab.getState(),f=sample(telemetry.frames,time);if(!root.current)return;
    root.current.position.set(...physicsPosition(f.position));physicsRotation(f.quaternion,root.current.quaternion);
    const separation=telemetry.run.separation;
    if(attached.current)attached.current.visible=!separation||time<separation.t;
    if(released.current&&separation){
      // Only the integrated upper_stage state from the simulator is drawn; no analytic fallback.
      const stage=f.upper_stage;
      released.current.visible=time>=separation.t&&!!stage&&!stage.impacted;
      if(stage){
        physicsRotation(stage.quaternion,released.current.quaternion);
        stageOffset.set(0,-4.5,0).applyQuaternion(released.current.quaternion);
        released.current.position.set(...physicsPosition(stage.position)).add(stageOffset);
      }
    }
  });
  return <>
    <group ref={root}>
      {/* Main Booster Cylindrical Fuselage */}
      <mesh material={material} castShadow={!ghost} receiveShadow><cylinderGeometry args={[1.8,1.8,34,96,16]}/></mesh>

      {/* Nosecone or Interstage */}
      {telemetry.run.mission!=='combined'?<>
        <mesh position={[0,18,0]} material={material} castShadow={!ghost}><cylinderGeometry args={[1.15,1.8,2,64]}/></mesh>
        <mesh position={[0,19.3,0]} material={material} castShadow={!ghost}><sphereGeometry args={[1.15,48,24,0,Math.PI*2,0,Math.PI/2]}/></mesh>
      </>:<mesh position={[0,18.5,0]} castShadow={!ghost}><cylinderGeometry args={[1.8,1.8,3,64]}/><meshPhysicalMaterial color="#222426" metalness={.6} roughness={.4} transparent={ghost} opacity={ghost?.22:1}/></mesh>}
      
      {/* Lower Aft Skirt Flare */}
      <mesh position={[0,-17.6,0]} castShadow={!ghost}><cylinderGeometry args={[1.8,1.55,1.4,64]}/><meshPhysicalMaterial color={ghost?'#71dae6':'#26282a'} metalness={.75} roughness={.38} transparent={ghost} opacity={ghost?.22:1}/></mesh>
      {/* Base Heat Shield Dome */}
      <mesh position={[0,-17.85,0]} rotation={[Math.PI,0,0]}><sphereGeometry args={[1.56,32,16,0,Math.PI*2,0,Math.PI/3]}/><meshStandardMaterial color="#1a1c1e" roughness={.7} metalness={.5}/></mesh>

      {/* Circumferential Structural Ring Stiffeners */}
      {[-16.7,-12.5,8,15.3].map(y=><mesh key={y} position={[0,y,0]}><cylinderGeometry args={[1.814,1.814,.08,96]}/><meshPhysicalMaterial color="#6e7570" metalness={.8} roughness={.25} transparent={ghost} opacity={ghost?.2:1}/></mesh>)}
      
      {/* Dual Aerodynamic Conduit Raceways */}
      {[-1,1].map(side=><group key={side} position={[side*1.815,-.5,0]}>
        <mesh castShadow={!ghost}><boxGeometry args={[.09,30,.22]}/><meshPhysicalMaterial color="#e6e4dc" metalness={.35} roughness={.4} transparent={ghost} opacity={ghost?.22:1}/></mesh>
        {/* Raceway aerodynamic endcaps */}
        <mesh position={[0,15.1,0]}><coneGeometry args={[.12,.4,4]}/><meshStandardMaterial color="#353b3f"/></mesh>
        <mesh position={[0,-15.1,0]} rotation={[Math.PI,0,0]}><coneGeometry args={[.12,.4,4]}/><meshStandardMaterial color="#353b3f"/></mesh>
      </group>)}

      {/* External Liquid Oxygen Transfer Feedline */}
      <mesh position={[0,-1,1.82]} castShadow={!ghost}><cylinderGeometry args={[.065,.065,24,16]}/><meshPhysicalMaterial color="#d8ded9" metalness={.6} roughness={.35} transparent={ghost} opacity={ghost?.22:1}/></mesh>

      {/* Hypersonic Titanium Grid Fins */}
      <GridFins telemetry={telemetry} ghost={ghost}/>

      {/* Cold Gas RCS Attitude Thrusters */}
      <RCSThrusters telemetry={telemetry}/>

      {/* Articulated Telescopic Landing Gear */}
      <LandingGear telemetry={telemetry} ghost={ghost}/>

      {/* Second Stage / Payload for Combined mission */}
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

function FlightScene(){
  const telemetry=useLab(s=>s.telemetry),ghost=useLab(s=>s.ghost);
  return <>
    <FrameDriver/>
    <World/>
    {telemetry&&<><Rocket telemetry={telemetry}/><Exhaust telemetry={telemetry}/><Trajectory telemetry={telemetry}/></>}
    {ghost&&<><Rocket telemetry={ghost} ghost/><Trajectory telemetry={ghost} ghost/></>}
    <CameraRig/>
    <RenderOutput/>
  </>;
}

export default function Scene(){
  const quality=useLab(s=>s.quality);
  const dpr=quality==='Performance'||quality==='Balanced'?1:Math.min(typeof window!=='undefined'?window.devicePixelRatio:1, 1.5);
  return <Canvas
    frameloop="demand"
    shadows={quality!=='Performance'}
    camera={{position:[75,245,80],fov:40,near:0.5,far:250000}}
    dpr={dpr}
    gl={{
      antialias:quality!=='Performance',
      powerPreference:quality==='Performance'?'low-power':'high-performance',
      toneMapping:THREE.ACESFilmicToneMapping,
      toneMappingExposure:1.05,
      outputColorSpace:THREE.SRGBColorSpace
    }}
  >
    <FlightScene/>
  </Canvas>;
}
