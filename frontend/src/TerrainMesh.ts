import {BufferGeometry,Float32BufferAttribute} from 'three';
import {terrainHeight,shoreline} from './terrain';

/** Fine near-range grid and stitched transition collars into the distant mesh.
 * Both resolutions contribute all their boundary vertices to each collar.
 * Geometry shares UVs in world meters across every patch, avoiding texture seams.
 */
export function createTerrainMesh(quality:string){
 const positions:number[]=[],uvs:number[]=[],indices:number[]=[],normals:number[]=[],colors:number[]=[];
 const nearStep=quality==='Balanced'?4:quality==='High'?2:quality==='Ultra'?1:.5;
 const rangeStep=quality==='Balanced'?8:quality==='High'?4:quality==='Ultra'?2:1;
 const farStep=24,farBoundary=504;
 function vertex(x:number,z:number){
  const id=positions.length/3,y=terrainHeight(x,z);positions.push(x,y,z);uvs.push(x/90,z/90);
  // Identical normals at patch boundaries prevent lighting seams when the
  // neighboring patches use different triangle sizes.
  const epsilon=.25,dx=(terrainHeight(x+epsilon,z)-terrainHeight(x-epsilon,z))/(2*epsilon),dz=(terrainHeight(x,z+epsilon)-terrainHeight(x,z-epsilon))/(2*epsilon),length=Math.hypot(dx,1,dz);
  normals.push(-dx/length,1/length,-dz/length);
  const inland=Math.max(0,Math.min(1,(shoreline(z)-x-65)/100));
  const variation=.94+.06*Math.sin(x*.043+Math.cos(z*.029)*2)*Math.cos(z*.037),dry=Math.max(0,Math.min(1,(y+1.2)/1.45)),wet=.68+.32*dry*dry*(3-2*dry);
  colors.push((.92-inland*.17)*variation*wet,(.88-inland*.09)*variation*wet,(.72-inland*.18)*variation*wet);
  return id;
 }
 function patch(minX:number,maxX:number,minZ:number,maxZ:number,step:number){
  const nx=Math.round((maxX-minX)/step),nz=Math.round((maxZ-minZ)/step),base=positions.length/3;
  for(let z=0;z<=nz;z++)for(let x=0;x<=nx;x++)vertex(minX+x*step,minZ+z*step);
  for(let z=0;z<nz;z++)for(let x=0;x<nx;x++){const a=base+z*(nx+1)+x,b=a+1,c=a+nx+1,d=c+1;indices.push(a,c,b,b,c,d);}
 }
 // Fine geometry is reserved for the visible range; 4K remains an opt-in mode.
 patch(-180,180,-180,180,nearStep);
 // The collar uses the fine boundary spacing and a coarse outer edge. Fan
 // stitching avoids overlapping coplanar meshes and unmatched T-junctions.
 function side(axis:'x'|'z',sign:number,inner:number,outer:number,innerStep:number,outerStep:number){
  const count=Math.round(2*inner/innerStep),inside:number[]=[],outside:number[]=[];
  for(let i=0;i<=count;i++){const along=-inner+i*innerStep,x=axis==='x'?sign*inner:along,z=axis==='z'?sign*inner:along;inside.push(vertex(x,z));}
  const n=Math.round(2*outer/outerStep);for(let i=0;i<=n;i++){const along=-outer+i*outerStep,x=axis==='x'?sign*outer:along,z=axis==='z'?sign*outer:along;outside.push(vertex(x,z));}
  let a=0,b=0;const flip=(axis==='x'&&sign===-1)||(axis==='z'&&sign===1);
  const tri=(p:number,q:number,r:number)=>{if(flip)indices.push(p,r,q);else indices.push(p,q,r);};
  while(a<count||b<n){if(a<count&&(b===n||(a+1)/count<=(b+1)/n)){tri(inside[a],inside[a+1],outside[b]);a++;}else{tri(inside[a],outside[b+1],outside[b]);b++;}}
 }
 for(const axis of ['x','z'] as const)for(const sign of [-1,1])side(axis,sign,180,192,nearStep,rangeStep);
 // Continue fine geometry across the coastline, access road and facilities,
 // not just the pad, without making distant land use the same density.
 patch(-480,-192,-480,480,rangeStep);patch(192,480,-480,480,rangeStep);
 patch(-192,192,-480,-192,rangeStep);patch(-192,192,192,480,rangeStep);
 for(const axis of ['x','z'] as const)for(const sign of [-1,1])side(axis,sign,480,farBoundary,rangeStep,farStep);
 patch(-2400,-farBoundary,-2400,2400,farStep);patch(farBoundary,2400,-2400,2400,farStep);
 patch(-farBoundary,farBoundary,-2400,-farBoundary,farStep);patch(-farBoundary,farBoundary,farBoundary,2400,farStep);
 // Low-detail land continues to the fog horizon instead of ending at an
 // obvious square island edge. Four patches never overlap the inner surface.
 for(const axis of ['x','z'] as const)for(const sign of [-1,1])side(axis,sign,2400,2520,farStep,120);
 patch(-9000,-2520,-9000,9000,120);patch(2520,9000,-9000,9000,120);
 patch(-2520,2520,-9000,-2520,120);patch(-2520,2520,2520,9000,120);
 const geometry=new BufferGeometry();geometry.setAttribute('position',new Float32BufferAttribute(positions,3));geometry.setAttribute('uv',new Float32BufferAttribute(uvs,2));geometry.setAttribute('normal',new Float32BufferAttribute(normals,3));geometry.setAttribute('color',new Float32BufferAttribute(colors,3));geometry.setIndex(indices);geometry.computeBoundingSphere();
 return geometry;
}
