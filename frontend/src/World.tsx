import {useEffect,useLayoutEffect,useMemo,useRef} from 'react';
import {useFrame,useThree} from '@react-three/fiber';
import {Environment,useTexture} from '@react-three/drei';
import * as THREE from 'three';
import {useLab} from './store';
import Nature from './Nature';
import {createTerrainMesh} from './TerrainMesh';
import {terrainHeight} from './terrain';
import {terrainSites,sceneryOffset,type Site} from './surface';
import {landingAt} from './telemetry';
import {LaunchClamp,ServiceArm} from './LaunchHardware';
import SuborbitalWorld from './SuborbitalWorld';

const ORIGIN:Site=[0,0];
const grounded=(x:number,z:number):[number,number,number]=>[x,terrainHeight(x,z),z];

function canvasTexture(size:number,draw:(ctx:CanvasRenderingContext2D)=>void,logicalSize=size){
  const canvas=document.createElement('canvas');canvas.width=size;canvas.height=size;const context=canvas.getContext('2d')!;context.scale(size/logicalSize,size/logicalSize);draw(context);
  const texture=new THREE.CanvasTexture(canvas);texture.colorSpace=THREE.SRGBColorSpace;texture.anisotropy=16;return texture;
}
export function useVehicleTexture(enabled=true){
  const quality=useLab(s=>s.quality);
  const texture=useMemo(()=>enabled?canvasTexture(quality==='Performance'?1024:2048,ctx=>{
    ctx.fillStyle='#f2f1ea';ctx.fillRect(0,0,2048,2048);
    // Seeded aerospace composite grain and micro-noise
    let seed=919;const random=()=>{seed=(seed*1664525+1013904223)>>>0;return seed/4294967296;};
    for(let i=0;i<65000;i++){const y=random()*2048;ctx.fillStyle=`rgba(40,44,42,${.012+random()*.025+(y>1450?(y-1450)/598*.12:0)})`;ctx.fillRect(random()*2048,y,1+random()*3,random()*4+1);}
    
    // Cryogenic LOX tank frost band (subtle cold white frost gradient)
    const frost=ctx.createLinearGradient(0,350,0,950);
    frost.addColorStop(0,'rgba(255,255,255,0)');frost.addColorStop(.3,'rgba(255,255,255,.16)');frost.addColorStop(.7,'rgba(255,255,255,.18)');frost.addColorStop(1,'rgba(255,255,255,0)');
    ctx.fillStyle=frost;ctx.fillRect(0,350,2048,600);

    // Reentry aerothermal soot gradient near aft skirt
    const soot=ctx.createLinearGradient(0,1200,0,2048);
    soot.addColorStop(0,'rgba(28,24,20,0)');soot.addColorStop(.4,'rgba(35,30,24,.15)');soot.addColorStop(.75,'rgba(26,22,18,.5)');soot.addColorStop(1,'rgba(16,14,12,.82)');
    ctx.fillStyle=soot;ctx.fillRect(0,1200,2048,848);

    // Circumferential stringers, panel seams and rivet rows
    for(let y=120;y<2040;y+=140){
      ctx.fillStyle='#5a635a38';ctx.fillRect(0,y,2048,2);
      ctx.fillStyle='#ffffff60';ctx.fillRect(0,y+2,2048,2);
      for(let x=15;x<2048;x+=36){
        ctx.fillStyle='#4c544c65';ctx.beginPath();ctx.arc(x,y-4,1.4,0,Math.PI*2);ctx.fill();
        ctx.fillStyle='#ffffff40';ctx.beginPath();ctx.arc(x+1,y-3,0.7,0,Math.PI*2);ctx.fill();
      }
    }
    // Vertical panel segments
    for(let x=0;x<2048;x+=256){
      ctx.fillStyle='#5a635a22';ctx.fillRect(x,0,2,2048);
      ctx.fillStyle='#ffffff35';ctx.fillRect(x+2,0,1,2048);
    }

    // Top interstage dark carbon composite band
    ctx.fillStyle='#1e2022';ctx.fillRect(0,0,2048,160);
    ctx.fillStyle='#363a3d';ctx.fillRect(0,156,2048,8);
    // Optical tracking roll patterns (black and white checkered blocks)
    for(let x=0;x<2048;x+=256){
      if((x/256)%2===0){ctx.fillStyle='#181a1c';ctx.fillRect(x,164,128,64);ctx.fillRect(x+128,228,128,64);}
      else {ctx.fillStyle='#ffffff';ctx.fillRect(x,164,128,64);ctx.fillRect(x+128,228,128,64);}
    }

    // Aerospace livery markings
    for(const x of [480,1504]){
      ctx.save();ctx.translate(x,980);ctx.rotate(-Math.PI/2);
      // Vertical UNITED STATES
      ctx.fillStyle='#0f1c24';ctx.font='bold 58px Arial, sans-serif';ctx.textAlign='center';ctx.fillText('UNITED STATES',0,0);
      ctx.font='600 24px Arial, sans-serif';ctx.fillStyle='#4b5956';ctx.fillText('ISS ORBITAL SYSTEMS · OMNIVERSE',0,42);
      ctx.restore();

      // American Flag graphic
      ctx.save();ctx.translate(x-40,430);
      ctx.fillStyle='#b22234';ctx.fillRect(0,0,80,48);
      for(let i=1;i<7;i+=2){ctx.fillStyle='#ffffff';ctx.fillRect(0,i*(48/7),80,48/7);}
      ctx.fillStyle='#3c3b6e';ctx.fillRect(0,0,36,26);
      ctx.fillStyle='#ffffff';ctx.fillRect(6,6,4,4);ctx.fillRect(16,6,4,4);ctx.fillRect(26,6,4,4);
      ctx.fillRect(11,14,4,4);ctx.fillRect(21,14,4,4);
      ctx.restore();

      // Booster identification tag
      ctx.fillStyle='#2c363f';ctx.fillRect(x-55,510,110,65);
      ctx.fillStyle='#f0ede1';ctx.font='bold 32px Arial, sans-serif';ctx.textAlign='center';ctx.fillText('ISS-01',x,555);
      ctx.fillStyle='#d46536';ctx.fillRect(x-55,575,110,8);
    }
  },2048):null,[quality,enabled]);
  useEffect(()=>()=>texture?.dispose(),[texture]);
  return texture;
}
function Ocean(){
  const water=useMemo(()=>{
    const normals=canvasTexture(512,ctx=>{const data=ctx.createImageData(512,512);for(let y=0;y<512;y++)for(let x=0;x<512;x++){const i=(y*512+x)*4;data.data[i]=128+Math.round(35*Math.cos(x*.21+y*.17)+18*Math.sin(x*.067-y*.12));data.data[i+1]=128+Math.round(33*Math.sin(x*.12-y*.19)+15*Math.cos(x*.05+y*.27));data.data[i+2]=240;data.data[i+3]=255;}ctx.putImageData(data,0,0);});normals.colorSpace=THREE.NoColorSpace;normals.wrapS=normals.wrapT=THREE.RepeatWrapping;
    normals.repeat.set(650,650);return normals;
  },[]);
  useEffect(()=>()=>water.dispose(),[water]);
  useFrame(()=>{const t=useLab.getState().time;water.offset.set(t*.0015,t*.0007);});
  return <mesh rotation={[-Math.PI/2,0,0]} position={[0,-1.3,0]}><planeGeometry args={[18000,18000]}/><meshPhysicalMaterial color="#315c63" roughness={.2} metalness={0} ior={1.33} normalMap={water} normalScale={[.35,.35]} envMapIntensity={1.4}/></mesh>;
}
function Landscape({sites}:{sites:Site[]}){
  const quality=useLab(s=>s.quality);
  const suffix=quality==='Performance'?'-1k':quality==='Balanced'?'':'-4k';
  const maps=useTexture(['color','normal','roughness'].map(kind=>`/assets/terrain/ground-${kind}${suffix}.jpg`));
  const {gl}=useThree();
  const textures=useMemo(()=>maps.map((source,i)=>{const map=source.clone();map.wrapS=map.wrapT=THREE.RepeatWrapping;map.repeat.set(1,1);map.anisotropy=Math.min(quality==='Performance'?4:16,gl.capabilities.getMaxAnisotropy());map.colorSpace=i===0?THREE.SRGBColorSpace:THREE.NoColorSpace;map.needsUpdate=true;return map;}),[maps,gl,quality]);
  const geometry=useMemo(()=>createTerrainMesh(quality,sites),[quality,sites]);
  useEffect(()=>()=>{geometry.dispose();},[geometry]);
  useEffect(()=>()=>{textures.forEach(map=>map.dispose());},[textures]);
  return <mesh geometry={geometry} receiveShadow><meshStandardMaterial vertexColors map={textures[0]} normalMap={textures[1]} normalScale={[.28,.28]} roughnessMap={textures[2]} roughness={1} color="#ffffff" envMapIntensity={.25}/></mesh>;
}
function Road(){
  const texture=useMemo(()=>canvasTexture(1024,ctx=>{ctx.fillStyle='#555a58';ctx.fillRect(0,0,1024,1024);let seed=91;for(let i=0;i<60000;i++){seed=(seed*1664525+1013904223)>>>0;const x=seed%1024;seed=(seed*1664525+1013904223)>>>0;const y=seed%1024;ctx.fillStyle=i%2?'#ffffff0c':'#11161128';ctx.fillRect(x,y,1,1);}ctx.fillStyle='#d0c9a5';ctx.fillRect(485,0,5,1024);ctx.fillRect(534,0,5,1024);ctx.fillStyle='#d0c9a590';ctx.fillRect(45,0,8,1024);ctx.fillRect(970,0,8,1024);}),[]);
  const road=useMemo(()=>{const map=texture.clone();map.wrapS=map.wrapT=THREE.RepeatWrapping;map.repeat.set(1,18);map.needsUpdate=true;return map;},[texture]);
  useEffect(()=>()=>{road.dispose();texture.dispose();},[road,texture]);
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
function PadLights({radius}:{radius:number}){
  const bases=useRef<THREE.InstancedMesh>(null),bulbs=useRef<THREE.InstancedMesh>(null);
  useLayoutEffect(()=>{
    const pose=new THREE.Object3D();
    for(let i=0;i<24;i++){
      const angle=i/24*Math.PI*2;pose.position.set(Math.cos(angle)*(radius+1),.2,Math.sin(angle)*(radius+1));pose.updateMatrix();bases.current?.setMatrixAt(i,pose.matrix);
      pose.position.y=.43;pose.updateMatrix();bulbs.current?.setMatrixAt(i,pose.matrix);
    }
    for(const mesh of [bases.current,bulbs.current])if(mesh){mesh.instanceMatrix.needsUpdate=true;mesh.computeBoundingSphere();}
  },[radius]);
  return <><instancedMesh ref={bases} args={[undefined,undefined,24]}><boxGeometry args={[.5,.4,.5]}/><meshStandardMaterial color="#545c57"/></instancedMesh><instancedMesh ref={bulbs} args={[undefined,undefined,24]}><sphereGeometry args={[.14,8,6]}/><meshBasicMaterial color="#bfebce"/></instancedMesh></>;
}
export function LandingPad({xy=[0,0],launch=false,label,radius=25}:{xy?:Site;launch?:boolean;label?:string;radius?:number}){
  const padLabel=label||(launch?'TAKEOFF PAD 01':'LANDING PAD 01');
  const ship=useLab(s=>s.pad)==='Ship'&&!launch;
  const stand=useLab(s=>s.telemetry?.launch_stand_height??0);
  const quality=useLab(s=>s.quality);
  const texture=useMemo(()=>canvasTexture(quality==='Performance'?1024:2048,ctx=>{
    // Base concrete slab
    ctx.fillStyle=launch?'#d2d5ce':'#404645';ctx.fillRect(0,0,2048,2048);
    let seed=launch?77:23;const random=()=>{seed=(seed*1664525+1013904223)>>>0;return seed/4294967296;};
    for(let i=0;i<85000;i++){ctx.fillStyle=i%2?'#ffffff12':'#101c1822';ctx.fillRect(random()*2048,random()*2048,random()*3+1,random()*3+1);}
    // Structural concrete expansion joints
    ctx.strokeStyle='#242e2a90';ctx.lineWidth=3;
    for(let i=1;i<8;i++){ctx.beginPath();ctx.moveTo(i*256,0);ctx.lineTo(i*256,2048);ctx.stroke();ctx.beginPath();ctx.moveTo(0,i*256);ctx.lineTo(2048,i*256);ctx.stroke();}

    if(launch){
      // ====== TAKEOFF PAD MARKINGS (ISS & NVIDIA ISAAC SIM) ======
      // Outer safety perimeter with alternating yellow & black hazard stripes
      ctx.save();
      ctx.lineWidth=48;
      for(let a=0;a<Math.PI*2;a+=Math.PI/32){
        ctx.strokeStyle=(Math.floor(a/(Math.PI/32))%2===0)?'#ffd200':'#1c1c1c';
        ctx.beginPath();ctx.arc(1024,1024,930,a,a+Math.PI/32+.01);ctx.stroke();
      }
      ctx.restore();

      // Launch mount ring & blast trench perimeter
      ctx.strokeStyle='#e2ded0';ctx.lineWidth=14;ctx.beginPath();ctx.arc(1024,1024,800,0,Math.PI*2);ctx.stroke();
      ctx.lineWidth=8;ctx.beginPath();ctx.arc(1024,1024,400,0,Math.PI*2);ctx.stroke();

      // North orientation indicator
      ctx.fillStyle='#ffd200';ctx.beginPath();ctx.moveTo(1024,65);ctx.lineTo(990,125);ctx.lineTo(1058,125);ctx.closePath();ctx.fill();
      ctx.fillStyle='#ffffff';ctx.font='bold 42px Arial, sans-serif';ctx.textAlign='center';ctx.fillText('▲ NORTH',1024,175);

      // Top label — Explicit TAKEOFF PAD branding
      ctx.fillStyle='#ffffff';ctx.font='900 76px Arial, sans-serif';ctx.textAlign='center';
      ctx.fillText(padLabel,1024,270);
      ctx.fillStyle='#ffd200';ctx.font='bold 34px Arial, sans-serif';
      ctx.fillText('ISS ORBITAL SYSTEMS · NVIDIA SIMULATOR',1024,320);

      // Prominent Upper TAKEOFF wording (positioned cleanly above center trench)
      ctx.fillStyle='#ffd200';ctx.font='900 135px Arial, sans-serif';ctx.textAlign='center';
      ctx.fillText('TAKEOFF',1024,670);

      // Prominent Lower LAUNCH COMPLEX wording (positioned cleanly below center trench)
      ctx.fillStyle='#ffffff';ctx.font='900 85px Arial, sans-serif';ctx.textAlign='center';
      ctx.fillText('LAUNCH PAD',1024,1420);

      // Complex coordinate details & separation requirements
      ctx.fillStyle='#c8d1cf';ctx.font='bold 36px Consolas, monospace';
      ctx.fillText('TAKEOFF COMPLEX 01 · PAD A',1024,1660);
      ctx.font='30px Consolas, monospace';
      ctx.fillText('ISS ORBITAL SYSTEMS · NVIDIA ISAAC SIMULATOR',1024,1710);
      ctx.fillText(`COORD [${xy[0].toFixed(0)}, ${xy[1].toFixed(0)}] · DOWNRANGE SEPARATION > 1,000 M`,1024,1760);

      // Blast flame deflector boundary
      ctx.strokeStyle='#f0b34270';ctx.lineWidth=6;ctx.strokeRect(690,690,668,668);
    }else{
      // ====== LANDING PAD MARKINGS (ISS & NVIDIA ISAAC SIM) ======
      // Outer reflective boundary ring
      ctx.strokeStyle='#f5f3e9';ctx.lineWidth=22;ctx.beginPath();ctx.arc(1024,1024,920,0,Math.PI*2);ctx.stroke();
      ctx.strokeStyle='#79dfb5';ctx.lineWidth=8;ctx.beginPath();ctx.arc(1024,1024,885,0,Math.PI*2);ctx.stroke();

      // Concentric distance rings: 20m, 15m, 10m, 5m
      ctx.strokeStyle='#dedbc8';ctx.lineWidth=6;ctx.beginPath();ctx.arc(1024,1024,720,0,Math.PI*2);ctx.stroke();
      ctx.lineWidth=6;ctx.beginPath();ctx.arc(1024,1024,480,0,Math.PI*2);ctx.stroke();
      ctx.strokeStyle='#79dfb5';ctx.lineWidth=8;ctx.beginPath();ctx.arc(1024,1024,240,0,Math.PI*2);ctx.stroke();

      // Central Bullseye Target Cross
      ctx.fillStyle='#dedecb';ctx.fillRect(1008,760,32,528);ctx.fillRect(760,1008,528,32);

      // Top label — Explicit LANDING PAD branding
      ctx.fillStyle='#ffffff';ctx.font='900 76px Arial, sans-serif';ctx.textAlign='center';
      ctx.fillText(padLabel,1024,270);
      ctx.fillStyle='#79dfb5';ctx.font='bold 34px Arial, sans-serif';
      ctx.fillText('ISS ORBITAL SYSTEMS · NVIDIA SIMULATOR',1024,320);

      // Prominent Upper LANDING wording (positioned cleanly above center cross)
      ctx.fillStyle='#79dfb5';ctx.font='900 135px Arial, sans-serif';ctx.textAlign='center';
      ctx.fillText('LANDING',1024,670);

      // Prominent Lower TOUCHDOWN ZONE wording (positioned cleanly below center cross)
      ctx.fillStyle='#ffffff';ctx.font='900 85px Arial, sans-serif';ctx.textAlign='center';
      ctx.fillText('LANDING ZONE',1024,1420);

      // Realistic hoverslam rocket exhaust scorch marks
      const scorch=ctx.createRadialGradient(1024,1024,0,1024,1024,560);
      scorch.addColorStop(0,'rgba(16,22,19,0.85)');scorch.addColorStop(.4,'rgba(24,30,26,0.45)');scorch.addColorStop(1,'rgba(20,26,22,0)');
      ctx.fillStyle=scorch;ctx.fillRect(0,0,2048,2048);

      // Landing Zone details & separation telemetry
      ctx.fillStyle='#c8d1cf';ctx.font='bold 36px Consolas, monospace';
      ctx.fillText('LANDING ZONE 01 · TOUCHDOWN TARGET',1024,1660);
      ctx.font='30px Consolas, monospace';
      ctx.fillText('ISS ORBITAL SYSTEMS · NVIDIA ISAAC SIMULATOR',1024,1710);
      ctx.fillText(`COORD [${xy[0].toFixed(0)}, ${xy[1].toFixed(0)}] · DOWNRANGE RECOVERY > 1,000 M`,1024,1760);

      // Approach alignment corner chevrons
      ctx.strokeStyle='#ffd200';ctx.lineWidth=10;
      for(let a=0;a<Math.PI*2;a+=Math.PI/2){
        ctx.save();ctx.translate(1024,1024);ctx.rotate(a+Math.PI/4);
        ctx.beginPath();ctx.moveTo(760,-40);ctx.lineTo(800,0);ctx.lineTo(760,40);ctx.stroke();
        ctx.restore();
      }
    }
  },2048),[padLabel,quality,launch,xy]);
  useEffect(()=>()=>texture.dispose(),[texture]);
  return <group position={[xy[0],0,-xy[1]]}>
    {ship&&<><mesh position={[0,-2.6,0]} receiveShadow><boxGeometry args={[65,5,95]}/><meshStandardMaterial color="#263a40" roughness={.7}/></mesh><mesh position={[23,5,32]} castShadow><boxGeometry args={[10,10,15]}/><meshStandardMaterial color="#c6cec7"/></mesh></>}
    <mesh position={[0,-.375,0]} receiveShadow><cylinderGeometry args={[radius+2,radius+3,.7,128]}/><meshStandardMaterial color="#a5a68f" roughness={.95}/></mesh>
    <mesh rotation={[-Math.PI/2,0,0]} position={[0,.045,0]} receiveShadow><circleGeometry args={[radius,128]}/><meshStandardMaterial map={texture} roughness={.9} metalness={.05} polygonOffset polygonOffsetFactor={-4} polygonOffsetUnits={-4}/></mesh>
    {launch&&<>
      {/* launch stand: the booster rests on its top, altitude is measured from there */}
      {stand>0&&<mesh position={[0,stand/2,0]} castShadow receiveShadow><cylinderGeometry args={[4.2,4.8,stand,48]}/><meshStandardMaterial color="#6f746c" metalness={.5} roughness={.6}/></mesh>}
      <group position={[0,stand,0]}>
      {/* flame deflector plate and hold-down ring */}
      <mesh rotation={[-Math.PI/2,0,0]} position={[0,.06,0]}><circleGeometry args={[4.2,64]}/><meshStandardMaterial color="#9ca3a6" metalness={.6} roughness={.45} polygonOffset polygonOffsetFactor={-5} polygonOffsetUnits={-5}/></mesh>
      <mesh position={[0,.04,0]} rotation={[Math.PI/2,0,0]}><torusGeometry args={[6.7,.55,8,64]}/><meshStandardMaterial color="#5d6057" metalness={.55} roughness={.55}/></mesh>
      {[0,1,2,3].map(i=><LaunchClamp key={i} angle={i*Math.PI/2+Math.PI/4}/>)}
      </group>
      {/* fixed service tower with work platforms and swing arms */}
      <group position={[14,0,0]}>
        {[[-2.6,-2.6],[2.6,-2.6],[-2.6,2.6],[2.6,2.6]].map(([x,z],i)=><mesh key={i} position={[x,27,z]} castShadow><boxGeometry args={[.34,54,.34]}/><meshStandardMaterial color="#6e7468" metalness={.6} roughness={.48}/></mesh>)}
        {Array.from({length:9},(_,i)=><mesh key={i} position={[0,3+i*6,0]} castShadow><boxGeometry args={[5.5,.16,5.5]}/><meshStandardMaterial color="#565c53" metalness={.5} roughness={.6}/></mesh>)}
        {[8,20,32,44].map(y=><group key={y} position={[0,y,0]}>
          <mesh castShadow><boxGeometry args={[5.9,.3,5.9]}/><meshStandardMaterial color="#8c9184" metalness={.35} roughness={.7}/></mesh>
          <mesh position={[-3.2,2.4,0]} rotation={[0,0,-.68]}><boxGeometry args={[.12,5.3,.12]}/><meshStandardMaterial color="#6e7468" metalness={.6}/></mesh>
          <mesh position={[-3.2,2.4,0]} rotation={[0,0,.68]}><boxGeometry args={[.12,5.3,.12]}/><meshStandardMaterial color="#6e7468" metalness={.6}/></mesh>
        </group>)}
        {[13,31,47].map((y,i)=><ServiceArm key={y} height={y} index={i}/>)}
        <mesh position={[0,56,0]}><boxGeometry args={[1.1,3.2,1.1]}/><meshStandardMaterial color="#7d8377" metalness={.5}/></mesh>
        <mesh position={[0,58.2,0]}><sphereGeometry args={[.32,12,12]}/><meshBasicMaterial color="#ffb46a"/></mesh>
      </group>
      {/* propellant lines running from the pad edge */}
      {[-1,1].map(side=><mesh key={side} position={[side*9,.35,-8]} rotation={[0,.18,0]}><cylinderGeometry args={[.22,.22,18,12]}/><meshStandardMaterial color="#9a9d8d" metalness={.7} roughness={.4}/></mesh>)}
    </>}
    <PadLights radius={radius}/>
  </group>;
}
function TargetMarker(){
  const root=useRef<THREE.Group>(null),telemetry=useLab(s=>s.telemetry);
  useFrame(()=>{if(root.current&&telemetry){const target=landingAt(telemetry.run,useLab.getState().time);root.current.position.set(target[0],.11,-target[1]);}});
  if(!telemetry||telemetry.run.mission==='takeoff')return null;
  return <group ref={root}><mesh rotation={[-Math.PI/2,0,0]}><ringGeometry args={[Math.max(.05,(telemetry.run.landing_tolerance??5)-.06),telemetry.run.landing_tolerance??5,96]}/><meshBasicMaterial color="#a8ffcd" depthWrite={false} polygonOffset polygonOffsetFactor={-6}/></mesh></group>;
}
export default function World(){
  const quality=useLab(s=>s.quality),pad=useLab(s=>s.pad),run=useLab(s=>s.telemetry?.run);
  const storePlan=useLab(s=>s.flightPlan);
  const plan=run?.initial_flight_plan||run?.flight_plan||storePlan;
  const suborbital=plan?.profile==='suborbital';
  const defaultLanding = useMemo<Site>(()=>[1200,400],[]);
  const launch=plan?.launch||ORIGIN,landing=plan?.landing||defaultLanding;
  const distinct=Math.hypot(launch[0]-landing[0],launch[1]-landing[1])>=22;
  const pads=useMemo(()=>{
    const values:Site[]=[landing];
    for(const event of run?.retargets||[])if(![...values,launch].some(p=>Math.hypot(p[0]-event.landing[0],p[1]-event.landing[1])<62))values.push(event.landing);
    return values;
  },[landing,launch,run]);
  const padRadius=distinct?Math.max(7,Math.min(25,Math.hypot(launch[0]-landing[0],launch[1]-landing[1])*.5-3.5)):25;
  const sites=useMemo(()=>[...terrainSites(plan,pad),...pads.map(([x,y]):Site=>[x-sceneryOffset(pad),-y])],[plan,pad,pads]);
  const lightTarget=useMemo(()=>{const target=new THREE.Object3D();target.position.set((launch[0]+landing[0])/2,0,-(launch[1]+landing[1])/2);return target;},[launch,landing]);
  return <>
    <Environment files="/assets/environment/coastal-sky.hdr" background={!suborbital} backgroundBlurriness={0} backgroundIntensity={.85} environmentIntensity={.65} environmentRotation={[0,1.2,0]}/>
    <fog attach="fog" args={['#aab7b3',1100,5000]}/>
    <ambientLight intensity={.12}/><hemisphereLight args={['#c7d8e5','#6c735b',.65]}/>
    <primitive object={lightTarget}/>
    <directionalLight position={[lightTarget.position.x-180,260,lightTarget.position.z+170]} target={lightTarget} intensity={3} color="#fff0d9" castShadow shadow-mapSize={quality==='Balanced'?[1024,1024]:[2048,2048]} shadow-camera-left={-110} shadow-camera-right={110} shadow-camera-top={310} shadow-camera-bottom={-90} shadow-camera-far={700} shadow-normalBias={.025} shadow-bias={-.00008} shadow-radius={3}/>
    <group position={[sceneryOffset(pad),0,0]}><Landscape sites={sites}/><Nature sites={sites}/><Facilities/></group>
    <Ocean/>
    {suborbital&&<SuborbitalWorld/>}
    {/* Takeoff pad at launch coordinates — always configured with launch=true and TAKEOFF branding */}
    <LandingPad xy={launch} launch radius={padRadius} label="TAKEOFF PAD 01"/>
    {/* Landing pad(s) downrange at landing coordinates — separated by > 1 km */}
    {distinct&&pads.map((xy,i)=><LandingPad key={`${xy[0]},${xy[1]}`} xy={xy} radius={i===0?padRadius:25} launch={false} label={`LANDING PAD ${String(i+1).padStart(2,'0')}`}/>)}
    <TargetMarker/>
  </>;
}
