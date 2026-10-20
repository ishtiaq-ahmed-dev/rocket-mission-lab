// Meshoptimizer derivatives retain UV/material maps and compact unused vertices.
import {readFileSync,writeFileSync} from 'node:fs';
import path from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const {MeshoptSimplifier}=await import(pathToFileURL(path.join(root,'frontend/node_modules/meshoptimizer/meshopt_simplifier.module.js')).href);
await MeshoptSimplifier.ready;
const dir=path.join(root,'frontend/public/assets/models/coast_rocks_05');
const original=JSON.parse(readFileSync(path.join(dir,'coast_rocks_05_1k.gltf'))),source=readFileSync(path.join(dir,'coast_rocks_05.bin'));
const components={SCALAR:1,VEC2:2,VEC3:3,VEC4:4};
function accessor(id){const a=original.accessors[id],b=original.bufferViews[a.bufferView],start=(b.byteOffset||0)+(a.byteOffset||0),size=components[a.type];const copy=source.subarray(start,start+a.count*size*4);const buffer=copy.buffer.slice(copy.byteOffset,copy.byteOffset+copy.byteLength);return a.componentType===5125?new Uint32Array(buffer):new Float32Array(buffer);}
const p=original.meshes[0].primitives[0],positions=accessor(p.attributes.POSITION),indices=accessor(p.indices),report=[];
for(const [name,triangles] of [['web',30000],['mid',3000],['low',1000]]){
 const gltf=structuredClone(original),[reduced,error]=MeshoptSimplifier.simplify(indices,positions,3,triangles*3,.05);
 const [remap,count]=MeshoptSimplifier.compactMesh(reduced);
 const chunks=[];let offset=0;const views=[],accessors=[];
 function append(array,type,componentType,target){const data=Buffer.from(array.buffer,array.byteOffset,array.byteLength);views.push({buffer:0,byteOffset:offset,byteLength:data.byteLength,target});chunks.push(data);offset+=data.byteLength;const id=accessors.length;accessors.push({bufferView:views.length-1,componentType,count:array.length/components[type],type});return id;}
 const attrs={};
 for(const [key,id] of Object.entries(p.attributes)){
  const old=original.accessors[id],values=accessor(id),size=components[old.type],compact=new Float32Array(count*size);
  for(let i=0;i<remap.length;i++)if(remap[i]<count)for(let c=0;c<size;c++)compact[remap[i]*size+c]=values[i*size+c];
  const next=append(compact,old.type,old.componentType,34962);if(old.min)accessors[next].min=old.min;if(old.max)accessors[next].max=old.max;attrs[key]=next;
 }
 const index=append(reduced,'SCALAR',5125,34963),stem=`coast_rocks_05_${name}`;
 gltf.meshes[0].primitives[0]={attributes:attrs,indices:index,material:p.material};gltf.accessors=accessors;gltf.bufferViews=views;gltf.buffers=[{uri:stem+'.bin',byteLength:offset}];
 writeFileSync(path.join(dir,stem+'.bin'),Buffer.concat(chunks));writeFileSync(path.join(dir,stem+'.gltf'),JSON.stringify(gltf));
 report.push({name,triangles:reduced.length/3,vertices:count,buffer_bytes:offset,relative_error:error});
}
writeFileSync(path.join(root,'data/rock-lod-validation.json'),JSON.stringify(report,null,2)+'\n');console.log(report);
