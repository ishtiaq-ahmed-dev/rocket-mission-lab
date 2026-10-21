import {useEffect,useMemo} from 'react';
import * as THREE from 'three';
import {useLab} from './store';

/** Small local vehicle texture; the environment has no texture downloads. */
export function useVehicleTexture(){
  const texture=useMemo(()=>{
    const canvas=document.createElement('canvas');canvas.width=canvas.height=1024;
    const ctx=canvas.getContext('2d')!;
    ctx.fillStyle='#efeee8';ctx.fillRect(0,0,1024,1024);
    for(let y=90;y<1024;y+=128){
      ctx.fillStyle='#aaa99f';ctx.fillRect(0,y,1024,1);
      for(let x=12;x<1024;x+=32){ctx.fillStyle='#74746f';ctx.fillRect(x,y-3,2,2);}
    }
    const soot=ctx.createLinearGradient(0,770,0,1024);soot.addColorStop(0,'#302a2100');soot.addColorStop(1,'#302a2170');ctx.fillStyle=soot;ctx.fillRect(0,770,1024,254);
    for(const x of [260,760]){ctx.save();ctx.translate(x,460);ctx.rotate(-Math.PI/2);ctx.textAlign='center';ctx.fillStyle='#262522';ctx.font='600 30px Arial';ctx.fillText('MISSION LAB',0,0);ctx.fillStyle='#ad5c27';ctx.font='16px Arial';ctx.fillText('EXPERIMENTAL / 01',0,30);ctx.restore();}
    const result=new THREE.CanvasTexture(canvas);result.colorSpace=THREE.SRGBColorSpace;result.anisotropy=4;return result;
  },[]);
  useEffect(()=>()=>texture.dispose(),[texture]);
  return texture;
}
function Site({xy,color,radius}:{xy:[number,number];color:string;radius:number}){
  return <group position={[xy[0],.025,-xy[1]]} rotation={[-Math.PI/2,0,0]}>
    <mesh><ringGeometry args={[radius-.12,radius,64]}/><meshBasicMaterial color={color} side={THREE.DoubleSide}/></mesh>
    <mesh><planeGeometry args={[1.4,.1]}/><meshBasicMaterial color={color}/></mesh>
    <mesh rotation={[0,0,Math.PI/2]}><planeGeometry args={[1.4,.1]}/><meshBasicMaterial color={color}/></mesh>
  </group>;
}
export default function World(){
  const plan=useLab(s=>s.telemetry?.run.flight_plan);
  const launch=plan?.launch||[0,0],landing=plan?.landing||[0,0];
  return <>
    <color attach="background" args={['#f5f4f0']}/>
    <hemisphereLight args={['#ffffff','#c6c0b3',2.3]}/>
    <directionalLight position={[120,240,90]} intensity={3.1} color="#fff8ec"/>
    <directionalLight position={[-80,70,-110]} intensity={1.2} color="#ffffff"/>
    <mesh rotation={[-Math.PI/2,0,0]}><planeGeometry args={[200000,200000]}/><meshStandardMaterial color="#ffffff" roughness={1}/></mesh>
    <Site xy={launch} color="#ac7428" radius={7}/>
    <Site xy={landing} color="#40805a" radius={5}/>
  </>;
}
