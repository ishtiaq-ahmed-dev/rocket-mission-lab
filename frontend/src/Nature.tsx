import {useLayoutEffect,useMemo,useRef} from 'react';
import {useGLTF} from '@react-three/drei';
import * as THREE from 'three';
import {terrainHeight,shoreline} from './terrain';

function randoms(seed:number){return()=>{seed=(seed*1664525+1013904223)>>>0;return seed/4294967296;};}
export default function Nature(){
  const rocks=useGLTF('/assets/models/coast_rocks_05/coast_rocks_05_web.gltf');
  const rockInstances=useRef<THREE.InstancedMesh>(null),grassInstances=useRef<THREE.InstancedMesh>(null);
  const rock=useMemo(()=>{let mesh:THREE.Mesh|undefined;rocks.scene.traverse(o=>{if(!mesh&&(o as THREE.Mesh).isMesh)mesh=o as THREE.Mesh;});return mesh!;},[rocks]);
  const grassGeometry=useMemo(()=>{
    // Real blade geometry avoids the opaque-card / broken-alpha artifacts of
    // vegetation atlases. Each cluster has curved, tapered blades with normals.
    const positions:number[]=[],colors:number[]=[],indices:number[]=[],rng=randoms(99);const color=new THREE.Color();
    for(let b=0;b<14;b++){
      const angle=rng()*Math.PI*2,height=.3+rng()*.7,bend=.1+rng()*.25,x=(rng()-.5)*.45,z=(rng()-.5)*.45,start=positions.length/3;
      color.setHSL(.17+rng()*.06,.25+rng()*.15,.19+rng()*.12);
      for(let segment=0;segment<=4;segment++){const t=segment/4,width=.045*(1-t)+.001,dx=Math.cos(angle),dz=Math.sin(angle),centerX=x+dx*t*t*bend,centerZ=z+dz*t*t*bend;for(const side of [-1,1]){positions.push(centerX-dz*width*side,height*t,centerZ+dx*width*side);colors.push(color.r*(.65+t*.35),color.g*(.65+t*.35),color.b*(.65+t*.35));}if(segment<4){const i=start+segment*2;indices.push(i,i+1,i+2,i+1,i+3,i+2);}}
    }const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.Float32BufferAttribute(positions,3));geometry.setAttribute('color',new THREE.Float32BufferAttribute(colors,3));geometry.setIndex(indices);geometry.computeVertexNormals();return geometry;
  },[]);
  useLayoutEffect(()=>{
    const dummy=new THREE.Object3D(),rng=randoms(427);
    for(let i=0;i<18;i++){const z=(rng()-.5)*1200,x=shoreline(z)-100-rng()*45,y=terrainHeight(x,z);dummy.position.set(x,y-.15,z);dummy.rotation.set(0,rng()*Math.PI*2,0);const scale=1.4+rng()*2.1;dummy.scale.set(scale,scale,scale);dummy.updateMatrix();rockInstances.current?.setMatrixAt(i,dummy.matrix);}
    if(rockInstances.current)rockInstances.current.instanceMatrix.needsUpdate=true;
    for(let i=0;i<2800;i++){let x=0,z=0;for(let attempt=0;attempt<30;attempt++){x=(rng()-.5)*850;z=(rng()-.5)*750;const onRoad=Math.abs(z)<10&&x<0&&x>-330,nearPad=Math.hypot(x,z)<36,facility=(x<-95&&Math.abs(z)<110);if(!onRoad&&!nearPad&&!facility&&x<shoreline(z)-110)break;}dummy.position.set(x,terrainHeight(x,z)+.02,z);dummy.rotation.set(0,rng()*Math.PI*2,0);const scale=.65+rng()*1.8;dummy.scale.set(scale,scale,scale);dummy.updateMatrix();grassInstances.current?.setMatrixAt(i,dummy.matrix);}
    if(grassInstances.current)grassInstances.current.instanceMatrix.needsUpdate=true;
  },[]);
  return <><instancedMesh ref={rockInstances} args={[rock.geometry,rock.material,18]} receiveShadow castShadow frustumCulled={false}/><instancedMesh ref={grassInstances} args={[grassGeometry,undefined,2800]} receiveShadow castShadow frustumCulled={false}><meshStandardMaterial vertexColors roughness={.95} side={THREE.DoubleSide}/></instancedMesh></>;
}
