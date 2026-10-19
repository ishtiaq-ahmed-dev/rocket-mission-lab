import {useEffect,useMemo} from 'react';
import {useFrame,useThree} from '@react-three/fiber';
import {Environment,useTexture} from '@react-three/drei';
import {Water} from 'three/addons/objects/Water.js';
import * as THREE from 'three';
import {useLab} from './store';
import Nature from './Nature';
import {createTerrainMesh} from './TerrainMesh';
import {terrainHeight} from './terrain';

const grounded=(x:number,z:number):[number,number,number]=>[x,terrainHeight(x,z),z];

function canvasTexture(size:number,draw:(ctx:CanvasRenderingContext2D)=>void){
  const canvas=document.createElement('canvas');canvas.width=size;canvas.height=size;draw(canvas.getContext('2d')!);
  const texture=new THREE.CanvasTexture(canvas);texture.colorSpace=THREE.SRGBColorSpace;texture.anisotropy=16;return texture;
}
export function useVehicleTexture(){
  return useMemo(()=>canvasTexture(2048,ctx=>{
    ctx.fillStyle='#e9e8df';ctx.fillRect(0,0,2048,2048);
    // Seeded panel grain, soot and rivets; generated locally, no external font.
    let seed=919;const random=()=>{seed=(seed*1664525+1013904223)>>>0;return seed/4294967296;};
    for(let i=0;i<55000;i++){const y=random()*2048;ctx.fillStyle=`rgba(63,67,62,${.015+random()*.035+(y>1500?(y-1500)/548*.1:0)})`;ctx.fillRect(random()*2048,y,1+random()*3,random()*5+1);}
    const soot=ctx.createLinearGradient(0,1350,0,2048);soot.addColorStop(0,'#342f2500');soot.addColorStop(.55,'#37362f0d');soot.addColorStop(1,'#2f2b2560');ctx.fillStyle=soot;ctx.fillRect(0,1350,2048,698);
    for(let y=165;y<2000;y+=183){ctx.fillStyle='#71796f49';ctx.fillRect(0,y,2048,2);ctx.fillStyle='#fffef164';ctx.fillRect(0,y+3,2048,2);for(let x=20;x<2048;x+=42){ctx.fillStyle='#5c685c70';ctx.beginPath();ctx.arc(x,y-5,1.3,0,Math.PI*2);ctx.fill();}}
    for(let x=0;x<2048;x+=256){ctx.fillStyle='#727c7018';ctx.fillRect(x,0,1,2048);}
    for(const x of [450,1474]){ctx.save();ctx.translate(x,890);ctx.rotate(-Math.PI/2);ctx.fillStyle='#1c303b';ctx.font='600 53px Arial';ctx.textAlign='center';ctx.fillText('MISSION LAB',0,0);ctx.font='24px Arial';ctx.fillStyle='#65716d';ctx.fillText('REUSABLE FLIGHT RESEARCH',0,46);ctx.restore();ctx.fillStyle='#c65f33';ctx.fillRect(x-45,460,90,75);ctx.fillStyle='#f2eee0';ctx.font='bold 35px Arial';ctx.textAlign='center';ctx.fillText('01',x,510);}
  }),[]);
}
function Ocean(){
  const quality=useLab(s=>s.quality);
  const water=useMemo(()=>{
    const normals=canvasTexture(512,ctx=>{const data=ctx.createImageData(512,512);for(let y=0;y<512;y++)for(let x=0;x<512;x++){const i=(y*512+x)*4;data.data[i]=128+Math.round(35*Math.cos(x*.21+y*.17)+18*Math.sin(x*.067-y*.12));data.data[i+1]=128+Math.round(33*Math.sin(x*.12-y*.19)+15*Math.cos(x*.05+y*.27));data.data[i+2]=240;data.data[i+3]=255;}ctx.putImageData(data,0,0);});normals.colorSpace=THREE.NoColorSpace;normals.wrapS=normals.wrapT=THREE.RepeatWrapping;
    const object=new Water(new THREE.PlaneGeometry(18000,18000),{textureWidth:quality==='Balanced'?512:1024,textureHeight:quality==='Balanced'?512:1024,waterNormals:normals,sunDirection:new THREE.Vector3(-.5,.65,-.4).normalize(),sunColor:0xffe6c5,waterColor:0x20535b,distortionScale:2.6,fog:true});
    object.rotation.x=-Math.PI/2;object.position.y=-1.3;object.material.uniforms.size.value=3.5;
    return object;
  },[quality]);
  useFrame(()=>{water.material.uniforms.time.value=useLab.getState().time*.35;water.material.uniforms.distortionScale.value=2.2;});
  return <primitive object={water}/>;
}
function Landscape(){
  const quality=useLab(s=>s.quality);
  const suffix=quality==='Ultra'||quality==='4K'?'-4k':'';
  const maps=useTexture(['color','normal','roughness'].map(kind=>`/assets/terrain/ground-${kind}${suffix}.jpg`));
  const {gl}=useThree();
  const textures=useMemo(()=>maps.map((source,i)=>{const map=source.clone();map.wrapS=map.wrapT=THREE.RepeatWrapping;map.repeat.set(1,1);map.anisotropy=Math.min(16,gl.capabilities.getMaxAnisotropy());map.colorSpace=i===0?THREE.SRGBColorSpace:THREE.NoColorSpace;map.needsUpdate=true;return map;}),[maps,gl]);
  const geometry=useMemo(()=>createTerrainMesh(quality),[quality]);
  useEffect(()=>()=>{geometry.dispose();},[geometry]);
  useEffect(()=>()=>{textures.forEach(map=>map.dispose());},[textures]);
  return <mesh geometry={geometry} receiveShadow><meshStandardMaterial vertexColors map={textures[0]} normalMap={textures[1]} normalScale={[.28,.28]} roughnessMap={textures[2]} roughness={1} color="#ffffff" envMapIntensity={.25}/></mesh>;
}
function Road(){
  const texture=useMemo(()=>canvasTexture(1024,ctx=>{ctx.fillStyle='#555a58';ctx.fillRect(0,0,1024,1024);let seed=91;for(let i=0;i<60000;i++){seed=(seed*1664525+1013904223)>>>0;const x=seed%1024;seed=(seed*1664525+1013904223)>>>0;const y=seed%1024;ctx.fillStyle=i%2?'#ffffff0c':'#11161128';ctx.fillRect(x,y,1,1);}ctx.fillStyle='#d0c9a5';ctx.fillRect(485,0,5,1024);ctx.fillRect(534,0,5,1024);ctx.fillStyle='#d0c9a590';ctx.fillRect(45,0,8,1024);ctx.fillRect(970,0,8,1024);}),[]);
  const road=useMemo(()=>{const map=texture.clone();map.wrapS=map.wrapT=THREE.RepeatWrapping;map.repeat.set(1,18);map.needsUpdate=true;return map;},[texture]);
  return <><mesh rotation={[-Math.PI/2,0,Math.PI/2]} position={[-180.5,.035,0]} receiveShadow><planeGeometry args={[15,305]}/><meshStandardMaterial color="#a6a18a" roughness={1} polygonOffset polygonOffsetFactor={-1} polygonOffsetUnits={-1}/></mesh><mesh rotation={[-Math.PI/2,0,Math.PI/2]} position={[-180.5,.07,0]} receiveShadow><planeGeometry args={[12,299]}/><meshStandardMaterial map={road} roughness={.94} polygonOffset polygonOffsetFactor={-2} polygonOffsetUnits={-2}/></mesh></>;
}
function Facilities(){
  return <>
    <Road/>
    <mesh rotation={[-Math.PI/2,0,0]} position={[-280,.04,-60]} receiveShadow><planeGeometry args={[85,115]}/><meshStandardMaterial color="#8a928b" roughness={.9}/></mesh>
    <group position={[-280,0,-70]}><mesh position={[0,9,0]} castShadow receiveShadow><boxGeometry args={[38,18,65]}/><meshStandardMaterial color="#bbc3bb" roughness={.76}/></mesh><mesh position={[0,18.5,0]} castShadow><boxGeometry args={[40,1,67]}/><meshStandardMaterial color="#4a5758" roughness={.8}/></mesh>
    {Array.from({length:13},(_,i)=><mesh key={i} position={[19.1,9,(i-6)*4.6]}><boxGeometry args={[.15,17,.16]}/><meshStandardMaterial color="#87928d"/></mesh>)}
    <mesh position={[19.2,4,14]}><boxGeometry args={[.2,8,16]}/><meshStandardMaterial color="#5c6b70" metalness={.3}/></mesh>
    {Array.from({length:6},(_,i)=><mesh key={i} position={[(i-2.5)*5.5,11,32.6]}><boxGeometry args={[3,3,.15]}/><meshStandardMaterial color="#415b65" metalness={.45} roughness={.22}/></mesh>)}
    </group>
    {[-1,1].map(n=><group key={n} position={[-135,0,n*72]}><mesh position={[0,7,0]} castShadow><cylinderGeometry args={[7,7,14,48]}/><meshPhysicalMaterial color="#b5beb7" roughness={.38} metalness={.65}/></mesh><mesh position={[0,14,0]}><sphereGeometry args={[7,40,20,0,Math.PI*2,0,Math.PI/2]}/><meshPhysicalMaterial color="#c9cfc4" metalness={.6} roughness={.3}/></mesh>{[3,7,11].map(y=><mesh key={y} position={[0,y,0]} rotation={[Math.PI/2,0,0]}><torusGeometry args={[7.03,.07,8,64]}/><meshStandardMaterial color="#65726b" metalness={.6}/></mesh>)}<mesh position={[9,3,0]} rotation={[0,0,Math.PI/2]}><cylinderGeometry args={[.3,.3,9,12]}/><meshStandardMaterial color="#a3afa5" metalness={.6}/></mesh></group>)}
    {Array.from({length:7},(_,i)=><group key={i} position={grounded(-65-i*65,-125-i*12)}><mesh position={[0,12,0]} castShadow><cylinderGeometry args={[.2,.35,24,12]}/><meshStandardMaterial color="#8f9c99" metalness={.8} roughness={.3}/></mesh><mesh position={[0,24,0]}><sphereGeometry args={[.6,12,12]}/><meshBasicMaterial color="#e5b26d"/></mesh><mesh position={[0,22,-1.2]} rotation={[-.25,0,0]}><boxGeometry args={[2.1,.35,1]}/><meshStandardMaterial color="#d7d9c8"/></mesh></group>)}
  </>;
}
export function LandingPad(){
  const ship=useLab(s=>s.pad)==='Ship';
  const texture=useMemo(()=>canvasTexture(2048,ctx=>{
    ctx.fillStyle='#4b5150';ctx.fillRect(0,0,2048,2048);let seed=23;const random=()=>{seed=(seed*1664525+1013904223)>>>0;return seed/4294967296;};
    for(let i=0;i<100000;i++){ctx.fillStyle=i%2?'#ffffff12':'#101c1820';ctx.fillRect(random()*2048,random()*2048,random()*3+1,random()*3+1);}
    ctx.strokeStyle='#242e2a90';ctx.lineWidth=2;for(let i=1;i<8;i++){ctx.beginPath();ctx.moveTo(i*256,0);ctx.lineTo(i*256,2048);ctx.stroke();ctx.beginPath();ctx.moveTo(0,i*256);ctx.lineTo(2048,i*256);ctx.stroke();}
    ctx.strokeStyle='#e5e1cb';ctx.lineWidth=17;ctx.beginPath();ctx.arc(1024,1024,880,0,Math.PI*2);ctx.stroke();ctx.lineWidth=9;ctx.beginPath();ctx.arc(1024,1024,225,0,Math.PI*2);ctx.stroke();
    ctx.fillStyle='#dedecb';ctx.fillRect(720,610,35,830);ctx.fillRect(1293,610,35,830);ctx.fillRect(720,1006,608,35);ctx.font='bold 85px Arial';ctx.textAlign='center';ctx.fillText('LANDING ZONE  01',1024,1715);
    const scorch=ctx.createRadialGradient(1024,1024,0,1024,1024,540);scorch.addColorStop(0,'#101714b0');scorch.addColorStop(.35,'#151c1940');scorch.addColorStop(1,'#151c1900');ctx.fillStyle=scorch;ctx.fillRect(0,0,2048,2048);
    for(let i=0;i<1900;i++){ctx.fillStyle='#323c3650';ctx.fillRect(random()*2048,random()*2048,random()*7,random()*5);}
  }),[]);
  return <group position={[0,0,0]}>
    {ship&&<><mesh position={[0,-2.6,0]} receiveShadow><boxGeometry args={[65,5,95]}/><meshStandardMaterial color="#263a40" roughness={.7}/></mesh><mesh position={[23,5,32]} castShadow><boxGeometry args={[10,10,15]}/><meshStandardMaterial color="#c6cec7"/></mesh></>}
    <mesh position={[0,-.3,0]} receiveShadow><cylinderGeometry args={[29,30,.7,128]}/><meshStandardMaterial color="#a5a68f" roughness={.95}/></mesh>
    <mesh rotation={[-Math.PI/2,0,0]} position={[0,.075,0]} receiveShadow><circleGeometry args={[25,128]}/><meshStandardMaterial map={texture} roughness={.9} metalness={.05} polygonOffset polygonOffsetFactor={-2} polygonOffsetUnits={-2}/></mesh>
    {Array.from({length:24},(_,i)=>{const a=i/24*Math.PI*2;return <group key={i} position={[Math.cos(a)*27,.2,Math.sin(a)*27]}><mesh castShadow><boxGeometry args={[.5,.4,.5]}/><meshStandardMaterial color="#545c57"/></mesh><mesh position={[0,.23,0]}><sphereGeometry args={[.14,12,8]}/><meshBasicMaterial color="#bfebce"/></mesh></group>})}
  </group>;
}
export default function World(){const quality=useLab(s=>s.quality),ship=useLab(s=>s.pad)==='Ship';return <>
  <Environment files="/assets/environment/coastal-sky.hdr" background backgroundBlurriness={0} backgroundIntensity={.85} environmentIntensity={.65} environmentRotation={[0,1.2,0]}/>
  <fog attach="fog" args={['#aab7b3',1100,5000]}/>
  <ambientLight intensity={.12}/><hemisphereLight args={['#c7d8e5','#6c735b',.65]}/>
  <directionalLight position={[-180,260,170]} intensity={3} color="#fff0d9" castShadow shadow-mapSize={quality==='Balanced'?[2048,2048]:[4096,4096]} shadow-camera-left={-110} shadow-camera-right={110} shadow-camera-top={310} shadow-camera-bottom={-90} shadow-camera-far={700} shadow-normalBias={.025} shadow-bias={-.00008} shadow-radius={3}/>
  <group position={[ship?-850:0,0,0]}><Landscape/><Nature/><Facilities/></group><Ocean/><LandingPad/>
</>}
