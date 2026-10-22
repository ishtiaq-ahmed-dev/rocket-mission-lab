import {useRef} from 'react';
import {useFrame} from '@react-three/fiber';
import type {Group} from 'three';
import {useLab} from './store';
import type {Telemetry} from './types';

export function supportRelease(telemetry:Telemetry|null,time:number){
  if(!telemetry||telemetry.run.mission==='landing')return 1;
  const release=telemetry.run.launch_release_time??telemetry.frames.find(f=>f.position[2]>telemetry.rocket_length/2+.05)?.t;
  if(release==null||time<release)return 0;
  return Math.min(1,(time-release)/.28);
}
export function LaunchClamp({angle}:{angle:number}){
  const arm=useRef<Group>(null);
  useFrame(()=>{const state=useLab.getState();if(arm.current)arm.current.rotation.z=supportRelease(state.telemetry,state.time)*1.35;});
  return <group position={[Math.cos(angle)*3.1,.04,Math.sin(angle)*3.1]} rotation={[0,-angle,0]}>
    <mesh position={[0,.3,0]} castShadow><boxGeometry args={[1.4,.6,1.5]}/><meshStandardMaterial color="#4a4d47" metalness={.6} roughness={.5}/></mesh>
    <mesh position={[0,1.25,0]} castShadow><boxGeometry args={[.65,1.9,.8]}/><meshStandardMaterial color="#777e75" metalness={.7} roughness={.4}/></mesh>
    <group ref={arm} position={[-.1,2.15,0]}>
      <mesh position={[-.55,0,0]} castShadow><boxGeometry args={[1.5,.32,.7]}/><meshStandardMaterial color="#b5b4a2" metalness={.75} roughness={.35}/></mesh>
      <mesh rotation={[Math.PI/2,0,0]}><cylinderGeometry args={[.18,.18,1,16]}/><meshStandardMaterial color="#343b36" metalness={.8}/></mesh>
    </group>
  </group>;
}
export function ServiceArm({height,index}:{height:number;index:number}){
  const arm=useRef<Group>(null);
  useFrame(()=>{const state=useLab.getState();if(arm.current)arm.current.rotation.y=supportRelease(state.telemetry,state.time)*Math.PI/2;});
  return <group ref={arm} position={[-4.1,height,0]}>
    <mesh position={[-3.6,0,0]} castShadow><boxGeometry args={[7.2,.22,1.1]}/><meshStandardMaterial color="#858b7e" metalness={.55} roughness={.5}/></mesh>
    <mesh position={[-7.4,-.85,0]} rotation={[0,0,.5]}><cylinderGeometry args={[.09,.11,2.1,8]}/><meshStandardMaterial color="#5b6157" metalness={.7}/></mesh>
    <mesh position={[-7.2,.55,0]}><boxGeometry args={[.7,.7,.7]}/><meshStandardMaterial color={index===1?'#c98048':'#737a70'} metalness={.4} roughness={.5}/></mesh>
  </group>;
}
