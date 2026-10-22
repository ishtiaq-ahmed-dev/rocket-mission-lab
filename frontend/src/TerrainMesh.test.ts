import {it,expect} from 'vitest';
import {createTerrainMesh} from './TerrainMesh';
import {pixelRatioForQuality} from './capture';
import {Mesh,MeshBasicMaterial,Raycaster,Vector3,DoubleSide} from 'three';
it('keeps actual near and distant terrain triangles beneath relocated pads',()=>{
 const sites:[number,number][]=[[80,-40],[-600,800],[-3500,2800]],geometry=createTerrainMesh('Balanced',sites),material=new MeshBasicMaterial({side:DoubleSide}),mesh=new Mesh(geometry,material);
 mesh.updateMatrixWorld();
 for(const [x,z] of sites)for(const [dx,dz] of [[0,0],[25,0],[-25,0],[0,25],[0,-25]]){
  const hits=new Raycaster(new Vector3(x+dx,500,z+dz),new Vector3(0,-1,0)).intersectObject(mesh);
  expect(hits.length).toBeGreaterThan(0);
  expect(hits[0].point.y).toBeCloseTo(0,4);
 }
 geometry.dispose();material.dispose();
});
it('builds a fine terrain without reversed or degenerate triangles',()=>{
 const geometry=createTerrainMesh('Balanced'),p=geometry.attributes.position,index=geometry.index!;
 let bad=0;for(let i=0;i<index.count;i+=3){const a=index.getX(i),b=index.getX(i+1),c=index.getX(i+2),up=(p.getZ(b)-p.getZ(a))*(p.getX(c)-p.getX(a))-(p.getX(b)-p.getX(a))*(p.getZ(c)-p.getZ(a));if(up<=0)bad++;}
 expect(bad).toBe(0);expect(index.count/3).toBeGreaterThan(100000);expect(index.count/3).toBeLessThan(200000);expect(p.count).toBe(geometry.attributes.uv.count);geometry.dispose();
});
it('terrain patches agree on height, normal and UV at their common boundaries',()=>{
 const geometry=createTerrainMesh('Balanced'),p=geometry.attributes.position,n=geometry.attributes.normal,uv=geometry.attributes.uv,seams=new Map<string,number[]>();let matches=0;
 for(let i=0;i<p.count;i++){
  const x=p.getX(i),z=p.getZ(i);if(![180,192,480,504,2400,2520].includes(Math.max(Math.abs(x),Math.abs(z))))continue;
  const key=`${x},${z}`,values=[p.getY(i),n.getX(i),n.getY(i),n.getZ(i),uv.getX(i),uv.getY(i)],other=seams.get(key);
  if(other){expect(values).toEqual(other);matches++;}else seams.set(key,values);
 }
 expect(matches).toBeGreaterThan(2000);geometry.dispose();
});
it('4K live quality fits a UHD buffer and retains ordinary quality presets',()=>{
 expect(pixelRatioForQuality('4K',1920,1080)).toBe(2);
 expect(pixelRatioForQuality('4K',1280,720)).toBe(3);
 expect(pixelRatioForQuality('4K',3840,2160)).toBe(1);
 expect(pixelRatioForQuality('Balanced',1920,1080)).toBe(1);
});
