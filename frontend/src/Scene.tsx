import {useMemo,useRef} from 'react';
import {Canvas,useFrame,useThree} from '@react-three/fiber';
import {OrbitControls,Line,Sky,Text,ContactShadows} from '@react-three/drei';
import * as THREE from 'three';
import {useLab} from './store';
import {sample} from './telemetry';
import type {Telemetry} from './types';

const C=new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1,0,0),-Math.PI/2);
const Ci=C.clone().invert();
const world=(p:number[]):[number,number,number]=>[p[0],p[2],-p[1]];
function Terrain(){
  const geometry=useMemo(()=>{
    const geo=new THREE.PlaneGeometry(4800,4800,150,150);geo.rotateX(-Math.PI/2);
    const pos=geo.attributes.position; const colors=[];const color=new THREE.Color();
    for(let i=0;i<pos.count;i++){
      const x=pos.getX(i),z=pos.getZ(i),shore=340+110*Math.sin(z/440)+80*Math.cos(z/250);
      const land=THREE.MathUtils.smoothstep(shore-x,0,170);
      const distance=Math.hypot(x,z);const hills=(Math.sin(x*.009)*Math.cos(z*.006)*12+18)*THREE.MathUtils.smoothstep(distance,240,900);
      pos.setY(i,-4+land*(4+hills));
      const variation=(Math.sin(x*.055+z*.025)+Math.cos(x*.013-z*.052))*.025;
      color.setRGB(.22+variation,.255+variation,.19+variation); if(land<.9)color.setRGB(.35,.33,.25);
      colors.push(color.r,color.g,color.b);
    }
    geo.setAttribute('color',new THREE.Float32BufferAttribute(colors,3));geo.computeVertexNormals();return geo;
  },[]);
  return <><mesh geometry={geometry} receiveShadow><meshStandardMaterial vertexColors roughness={1}/></mesh><mesh rotation={[-Math.PI/2,0,0]} position={[0,-1.2,0]} receiveShadow><planeGeometry args={[18000,18000]}/><meshStandardMaterial color="#426b70" roughness={.36} metalness={.5}/></mesh>
  {Array.from({length:9},(_,i)=><mesh key={i} position={[650+i*110,-.8,-500+i*130]} rotation={[-Math.PI/2,0,-.2]}><planeGeometry args={[230,1]}/><meshBasicMaterial color="#94b6b4" transparent opacity={.15}/></mesh>)}
  <mesh position={[-170,.02,0]} rotation={[-Math.PI/2,0,0]} receiveShadow><planeGeometry args={[320,12]}/><meshStandardMaterial color="#484c47"/></mesh>
  <mesh position={[-310,8,-70]} castShadow><boxGeometry args={[38,16,65]}/><meshStandardMaterial color="#747f7b" roughness={.9}/></mesh>
  <mesh position={[-310,17,-70]}><boxGeometry args={[41,2,68]}/><meshStandardMaterial color="#394a4b"/></mesh>
  {[-1,1].map((n)=><group key={n} position={[-140,0,n*75]}><mesh position={[0,7,0]} castShadow><cylinderGeometry args={[8,8,14,24]}/><meshStandardMaterial color="#b4b8a9" metalness={.45} roughness={.5}/></mesh><mesh position={[0,14,0]}><sphereGeometry args={[8,24,12,0,Math.PI*2,0,Math.PI/2]}/><meshStandardMaterial color="#c1c8b8" metalness={.4} roughness={.5}/></mesh></group>)}
  {Array.from({length:6},(_,i)=><group key={i} position={[-70-i*90,0,-160-i*15]}><mesh position={[0,12,0]} castShadow><cylinderGeometry args={[.3,.6,24,6]}/><meshStandardMaterial color="#87918b"/></mesh><mesh position={[0,24,0]}><sphereGeometry args={[1,8,8]}/><meshBasicMaterial color="#e38d4d"/></mesh></group>)}
  </>;
}
function Pad(){
  const ship=useLab(s=>s.pad)==='Ship';
  return <group position={[0,.1,0]}>
    {ship&&<><mesh position={[0,-2,0]} receiveShadow><boxGeometry args={[65,5,95]}/><meshStandardMaterial color="#182a30" roughness={.7}/></mesh><mesh position={[23,5,32]}><boxGeometry args={[10,10,15]}/><meshStandardMaterial color="#b5c4bd"/></mesh></>}
    <mesh receiveShadow><cylinderGeometry args={[29,30,1,96]}/><meshStandardMaterial color="#9a9a84" roughness={.95}/></mesh>
    <mesh position={[0,.55,0]} receiveShadow><cylinderGeometry args={[24,24,.15,96]}/><meshStandardMaterial color="#343d3b" roughness={.9}/></mesh>
    <mesh rotation={[-Math.PI/2,0,0]} position={[0,.66,0]}><ringGeometry args={[20.9,21.3,96]}/><meshBasicMaterial color="#d5d4af"/></mesh>
    <mesh rotation={[-Math.PI/2,0,0]} position={[0,.67,0]}><ringGeometry args={[4.7,5,64]}/><meshBasicMaterial color="#d5d4af"/></mesh>
    {[-1,1].map(n=><mesh key={n} position={[n*6,.69,0]} rotation={[-Math.PI/2,0,0]}><planeGeometry args={[1,18]}/><meshBasicMaterial color="#dfdfc8"/></mesh>)}
    <mesh position={[0,.7,0]} rotation={[-Math.PI/2,0,0]}><planeGeometry args={[12,1]}/><meshBasicMaterial color="#dfdfc8"/></mesh>
    {Array.from({length:16},(_,i)=>{const a=i/16*Math.PI*2;return <group key={i} position={[Math.cos(a)*27,1,Math.sin(a)*27]}><mesh><boxGeometry args={[.7,.4,.7]}/><meshBasicMaterial color="#a4d7d2"/></mesh></group>})}
  </group>;
}
function Rocket({telemetry,ghost=false}:{telemetry:Telemetry;ghost?:boolean}){
  const root=useRef<THREE.Group>(null);const flame=useRef<THREE.Group>(null);const particles=useRef<THREE.InstancedMesh>(null);
  const dummy=useMemo(()=>new THREE.Object3D(),[]);
  const material=useMemo(()=>new THREE.MeshStandardMaterial({color:ghost?'#79d5df':'#e4e5dd',metalness:.38,roughness:.4,transparent:ghost,opacity:ghost?.28:1,depthWrite:!ghost}),[ghost]);
  useFrame(()=>{
    const {time}=useLab.getState();const f=sample(telemetry.frames,time);if(!root.current)return;
    root.current.position.set(...world(f.position));
    root.current.quaternion.copy(C).multiply(new THREE.Quaternion(f.quaternion[1],f.quaternion[2],f.quaternion[3],f.quaternion[0])).multiply(Ci);
    if(flame.current){flame.current.visible=f.throttle>.02&&time<telemetry.run.duration;flame.current.scale.set(1+f.throttle*.5,Math.max(.01,f.throttle)*(1+.08*Math.sin(time*47)),1+f.throttle*.5);}
    if(particles.current){
      for(let i=0;i<65;i++){
        const age=((time*1.7+i*.153)%1);const spread=age*8;
        dummy.position.set(Math.sin(i*13)*spread,-23-age*55,Math.cos(i*9)*spread);
        dummy.scale.setScalar((.6+age*3.4)*f.throttle);dummy.updateMatrix();particles.current.setMatrixAt(i,dummy.matrix);
      }particles.current.instanceMatrix.needsUpdate=true;particles.current.visible=f.throttle>.1&&time<telemetry.run.duration;
    }
  });
  return <group ref={root}>
    <mesh material={material} castShadow={!ghost}><cylinderGeometry args={[1.8,1.8,34,40]}/></mesh>
    <mesh position={[0,18,0]} material={material}><cylinderGeometry args={[1.1,1.8,2,32]}/></mesh>
    <mesh position={[0,19.5,0]} material={material}><sphereGeometry args={[1.1,24,16,0,Math.PI*2,0,Math.PI/2]}/></mesh>
    <mesh position={[0,-18,0]} castShadow><cylinderGeometry args={[1.8,1.5,2,32]}/><meshStandardMaterial color={ghost?'#71dae6':'#272d30'} metalness={.7} roughness={.4} transparent={ghost} opacity={ghost?.25:1}/></mesh>
    <mesh position={[0,-19.8,0]}><cylinderGeometry args={[.65,1.1,1.7,24,1,true]}/><meshStandardMaterial color="#171b1c" side={THREE.DoubleSide} metalness={.8} roughness={.4}/></mesh>
    {[-13,8,15].map(y=><mesh key={y} position={[0,y,0]}><cylinderGeometry args={[1.815,1.815,.25,40]}/><meshStandardMaterial color="#626c6e" metalness={.7} transparent={ghost} opacity={ghost?.2:1}/></mesh>)}
    {!ghost&&<><Text position={[0,5,1.82]} fontSize={.85} letterSpacing={.15} color="#263b43" anchorX="center" rotation={[0,0,Math.PI/2]}>MISSION LAB</Text><mesh position={[0,10,1.8]}><planeGeometry args={[1.1,1.6]}/><meshStandardMaterial color="#dd713e"/></mesh></>}
    {[0,1,2,3].map(i=><group key={i} rotation={[0,i*Math.PI/2+Math.PI/4,0]}>
      <mesh position={[3.3,-16.7,0]} rotation={[0,0,-.48]} castShadow><boxGeometry args={[.25,7,.4]}/><meshStandardMaterial color="#495359" metalness={.6} transparent={ghost} opacity={ghost?.3:1}/></mesh>
      <mesh position={[2.8,-18.1,0]} rotation={[0,0,-.75]}><boxGeometry args={[.16,5,.2]}/><meshStandardMaterial color="#7d8685" metalness={.8}/></mesh>
      <mesh position={[5,-19.8,0]}><boxGeometry args={[1.5,.3,1.2]}/><meshStandardMaterial color="#2a3135"/></mesh>
      <group position={[2.7,12,0]}>
        {Array.from({length:5},(_,k)=><mesh key={k} position={[0,0,(k-2)*.4]}><boxGeometry args={[2,.12,.07]}/><meshStandardMaterial color="#485256"/></mesh>)}
        {Array.from({length:5},(_,k)=><mesh key={k} position={[(k-2)*.5,0,0]}><boxGeometry args={[.07,.12,1.8]}/><meshStandardMaterial color="#485256"/></mesh>)}
      </group>
    </group>)}
    {!ghost&&<><group ref={flame} position={[0,-20.4,0]}>
      <mesh position={[0,-6,0]} rotation={[0,0,Math.PI]}><coneGeometry args={[1.5,12,24,1,true]}/><meshBasicMaterial color="#ffad55" transparent opacity={.7} blending={THREE.AdditiveBlending} depthWrite={false}/></mesh>
      <mesh position={[0,-3,0]} rotation={[0,0,Math.PI]}><coneGeometry args={[.8,6,24]}/><meshBasicMaterial color="#eaf5ff" transparent opacity={.9} blending={THREE.AdditiveBlending} depthWrite={false}/></mesh>
      <pointLight color="#ff9549" intensity={180} distance={65}/>
    </group><instancedMesh ref={particles} args={[undefined,undefined,65]} frustumCulled={false}><sphereGeometry args={[1,6,6]}/><meshStandardMaterial color="#c3bca9" transparent opacity={.13} depthWrite={false}/></instancedMesh></>}
  </group>;
}
function FlightScene(){
  const telemetry=useLab(s=>s.telemetry),ghost=useLab(s=>s.ghost),mode=useLab(s=>s.camera);
  const controls=useRef<React.ComponentRef<typeof OrbitControls>>(null);const {camera}=useThree();
  const position=useMemo(()=>new THREE.Vector3(),[]),target=useMemo(()=>new THREE.Vector3(),[]);
  useFrame((_,dt)=>{
    useLab.getState().advance(Math.min(dt,.1));
    if(!telemetry||mode==='Free orbit')return;
    const f=sample(telemetry.frames,useLab.getState().time),[x,y,z]=world(f.position);const h=Math.max(y-20,0);
    if(mode==='Chase'){position.set(x+45,y+20,z+65);target.set(x,y,z);}
    else if(mode==='Ground'){position.set(105,8,120);target.set(x,Math.max(20,y-8),z);}
    else if(mode==='Top-down'){position.set(x+1,y+180,z+.1);target.set(x,0,z);}
    else {const t=useLab.getState().time*.035;position.set(x+Math.cos(.75+t)*(95+h*.22),y+30+Math.min(h*.15,35),z+Math.sin(.75+t)*(115+h*.22));target.set(x,Math.max(14,y-15),z);}
    camera.position.lerp(position,1-Math.exp(-dt*2));
    if(controls.current){controls.current.target.lerp(target,1-Math.exp(-dt*3));controls.current.update();}
  });
  const trajectory=useMemo(()=>telemetry?.frames.filter((_,i)=>i%4===0).map(f=>world(f.position))||[],[telemetry]);
  const ghostLine=useMemo(()=>ghost?.frames.filter((_,i)=>i%5===0).map(f=>world(f.position))||[],[ghost]);
  return <>
    <color attach="background" args={['#829b9e']}/><fog attach="fog" args={['#879d9c',800,3800]}/>
    <Sky distance={12000} sunPosition={[-1200,500,-500]} turbidity={5} rayleigh={.5} mieCoefficient={.008} mieDirectionalG={.85}/>
    <ambientLight intensity={.6} color="#bdcfd2"/><hemisphereLight args={['#c6e2e8','#5c5b40',1.6]}/>
    <directionalLight position={[-160,250,-100]} intensity={3.4} color="#ffe2bd" castShadow shadow-mapSize={[2048,2048]} shadow-camera-left={-170} shadow-camera-right={170} shadow-camera-top={270} shadow-camera-bottom={-170} shadow-camera-far={650} shadow-bias={-.0001}/>
    <Terrain/><Pad/><ContactShadows position={[0,.7,0]} opacity={.4} scale={90} blur={2} far={50} resolution={256}/>
    {telemetry&&<Rocket telemetry={telemetry}/>} {ghost&&<Rocket telemetry={ghost} ghost/>}
    {trajectory.length>1&&<Line points={trajectory} color="#f6b879" lineWidth={1.2} transparent opacity={.6} dashed dashSize={3} gapSize={4}/>}
    {ghostLine.length>1&&<Line points={ghostLine} color="#78dbe4" lineWidth={1} transparent opacity={.4}/>}
    <OrbitControls ref={controls} makeDefault enableDamping minDistance={12} maxDistance={1800} maxPolarAngle={Math.PI*.495} target={[0,180,0]} enabled={mode==='Free orbit'}/>
  </>;
}
export default function Scene(){return <Canvas shadows camera={{position:[155,260,180],fov:46,near:.5,far:16000}} dpr={[1,1.75]} gl={{antialias:true,powerPreference:'high-performance'}}><FlightScene/></Canvas>}
