import {useEffect,useLayoutEffect,useMemo,useRef} from 'react';
import {useFrame,useThree} from '@react-three/fiber';
import {useGLTF} from '@react-three/drei';
import * as THREE from 'three';
import {terrainHeight,shoreline} from './terrain';
import {useLab} from './store';

function randoms(seed:number){return()=>{seed=(seed*1664525+1013904223)>>>0;return seed/4294967296;};}
export default function Nature(){
 const assets=useGLTF(['web','mid','low'].map(level=>`/assets/models/coast_rocks_05/coast_rocks_05_${level}.gltf`));
 const quality=useLab(s=>s.quality),{camera}=useThree();
 const rockInstances=useRef<Array<THREE.InstancedMesh|null>>([]),grassInstances=useRef<THREE.InstancedMesh>(null);
 const rocks=useMemo(()=>assets.map(asset=>{let mesh:THREE.Mesh|undefined;asset.scene.traverse(o=>{if(!mesh&&(o as THREE.Mesh).isMesh)mesh=o as THREE.Mesh;});return mesh!;}),[assets]);
 const grassCount=quality==='Balanced'?600:quality==='High'?1000:quality==='Ultra'?1800:2800;
 const poses=useMemo(()=>{const rng=randoms(427),dummy=new THREE.Object3D();return Array.from({length:18},()=>{const z=(rng()-.5)*1200,x=shoreline(z)-100-rng()*45;dummy.position.set(x,terrainHeight(x,z)-.15,z);dummy.rotation.set(0,rng()*Math.PI*2,0);const scale=1.4+rng()*2.1;dummy.scale.set(scale,scale,scale);dummy.updateMatrix();return {position:dummy.position.clone(),matrix:dummy.matrix.clone()};});},[]);
 const grassGeometry=useMemo(()=>{
  const positions:number[]=[],colors:number[]=[],indices:number[]=[],rng=randoms(99),color=new THREE.Color();
  const blades=quality==='4K'?14:8,segments=quality==='4K'?4:3;
  for(let b=0;b<blades;b++){
   const angle=rng()*Math.PI*2,height=.3+rng()*.7,bend=.1+rng()*.25,x=(rng()-.5)*.45,z=(rng()-.5)*.45,start=positions.length/3;
   color.setHSL(.17+rng()*.06,.25+rng()*.15,.19+rng()*.12);
   for(let segment=0;segment<=segments;segment++){
    const t=segment/segments,width=.045*(1-t)+.001,dx=Math.cos(angle),dz=Math.sin(angle),cx=x+dx*t*t*bend,cz=z+dz*t*t*bend;
    for(const side of [-1,1]){positions.push(cx-dz*width*side,height*t,cz+dx*width*side);colors.push(color.r*(.65+t*.35),color.g*(.65+t*.35),color.b*(.65+t*.35));}
    if(segment<segments){const i=start+segment*2;indices.push(i,i+1,i+2,i+1,i+3,i+2);}
   }
  }
  const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.Float32BufferAttribute(positions,3));geometry.setAttribute('color',new THREE.Float32BufferAttribute(colors,3));geometry.setIndex(indices);geometry.computeVertexNormals();return geometry;
 },[quality]);
 useEffect(()=>()=>grassGeometry.dispose(),[grassGeometry]);
 useLayoutEffect(()=>{
  const dummy=new THREE.Object3D(),rng=randoms(428);
  for(let i=0;i<grassCount;i++){
   let x=0,z=0;
   for(let attempt=0;attempt<30;attempt++){x=(rng()-.5)*850;z=(rng()-.5)*750;const road=Math.abs(z)<10&&x<0&&x>-330,pad=Math.hypot(x,z)<36,facility=x<-95&&Math.abs(z)<110;if(!road&&!pad&&!facility&&x<shoreline(z)-110)break;}
   dummy.position.set(x,terrainHeight(x,z)+.02,z);dummy.rotation.set(0,rng()*Math.PI*2,0);const scale=.65+rng()*1.8;dummy.scale.set(scale,scale,scale);dummy.updateMatrix();grassInstances.current?.setMatrixAt(i,dummy.matrix);
  }
  if(grassInstances.current){grassInstances.current.instanceMatrix.needsUpdate=true;grassInstances.current.computeBoundingSphere();}
 },[grassCount]);
 const localCamera=useMemo(()=>new THREE.Vector3(),[]);
 useFrame(()=>{
  localCamera.copy(camera.position);if(useLab.getState().pad==='Ship')localCamera.x+=850;
  const counts=[0,0,0];
  for(const pose of poses){const distance=localCamera.distanceTo(pose.position),close=(quality==='Ultra'||quality==='4K')&&distance<100,level=close?0:distance<300?1:2;rockInstances.current[level]?.setMatrixAt(counts[level]++,pose.matrix);}
  rockInstances.current.forEach((mesh,i)=>{if(mesh){mesh.count=counts[i];mesh.instanceMatrix.needsUpdate=true;}});
  if(grassInstances.current)grassInstances.current.visible=camera.position.y<140;
 });
 return <>{rocks.map((rock,i)=><instancedMesh key={i} ref={node=>{rockInstances.current[i]=node;}} args={[rock.geometry,rock.material,18]} receiveShadow frustumCulled={false}/>)}<instancedMesh ref={grassInstances} args={[grassGeometry,undefined,grassCount]} receiveShadow><meshStandardMaterial vertexColors roughness={.95} side={THREE.DoubleSide}/></instancedMesh></>;
}
