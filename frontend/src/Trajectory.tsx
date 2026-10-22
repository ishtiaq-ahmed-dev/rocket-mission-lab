import {useEffect,useMemo} from 'react';
import {useFrame} from '@react-three/fiber';
import {BufferAttribute,BufferGeometry,Line,LineBasicMaterial} from 'three';
import {useLab} from './store';
import type {Telemetry} from './types';

/** Actual flown samples, never a suggested target/landing guide. Off by default. */
export default function Trajectory({telemetry,ghost=false}:{telemetry:Telemetry;ghost?:boolean}){
  const mode=useLab(s=>s.trail);
  const object=useMemo(()=>{if(mode==='Off')return null;const values=new Float32Array(telemetry.frames.flatMap(f=>[f.position[0],Math.max(.12,f.position[2]),-f.position[1]])),geometry=new BufferGeometry();geometry.setAttribute('position',new BufferAttribute(values,3));const line=new Line(geometry,new LineBasicMaterial({color:ghost?'#78c8d0':'#d8c4a0',transparent:true,opacity:.38,depthTest:true,depthWrite:false}));line.frustumCulled=false;return line;},[telemetry,ghost,mode]);
  useEffect(()=>()=>{object?.geometry.dispose();object?.material.dispose();},[object]);
  useFrame(()=>{
    const time=useLab.getState().time;
    let count=telemetry.frames.length;
    if(mode==='Flown'){let lo=0,hi=count;while(lo<hi){const mid=(lo+hi)>>1;if(telemetry.frames[mid].t<=time)lo=mid+1;else hi=mid;}count=lo;}
    object?.geometry.setDrawRange(0,mode==='Off'?0:count);
  });
  if(!object)return null;
  return <primitive object={object}/>;
}
