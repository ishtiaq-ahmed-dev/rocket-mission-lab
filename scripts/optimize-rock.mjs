// Preserve the scan's UVs/materials while reducing its 771k-triangle index buffer.
import {readFileSync,writeFileSync} from 'node:fs';
import path from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const {MeshoptSimplifier}=await import(pathToFileURL(path.join(root,'frontend/node_modules/meshoptimizer/meshopt_simplifier.module.js')).href);
await MeshoptSimplifier.ready;
const dir=path.join(root,'frontend/public/assets/models/coast_rocks_05');
const gltf=JSON.parse(readFileSync(path.join(dir,'coast_rocks_05_1k.gltf'))),source=readFileSync(path.join(dir,'coast_rocks_05.bin'));
function accessor(id){const a=gltf.accessors[id],b=gltf.bufferViews[a.bufferView],start=(b.byteOffset||0)+(a.byteOffset||0),size=a.type==='VEC3'?3:a.type==='VEC2'?2:1;const copy=source.subarray(start,start+a.count*size*4);const buffer=copy.buffer.slice(copy.byteOffset,copy.byteOffset+copy.byteLength);return a.componentType===5125?new Uint32Array(buffer):new Float32Array(buffer);}
const p=gltf.meshes[0].primitives[0],positions=accessor(p.attributes.POSITION),indices=accessor(p.indices);
const [reduced,error]=MeshoptSimplifier.simplify(indices,positions,3,90000,.02);
const chunks=[];let offset=0;const views=[],accessors=[];
function append(array,type,componentType,target){const data=Buffer.from(array.buffer,array.byteOffset,array.byteLength);views.push({buffer:0,byteOffset:offset,byteLength:data.byteLength,target});chunks.push(data);offset+=data.byteLength;const id=accessors.length;const a={bufferView:views.length-1,componentType,count:array.length/(type==='VEC3'?3:type==='VEC2'?2:1),type};accessors.push(a);return id;}
const attrs={};for(const [key,id] of Object.entries(p.attributes)){const old=gltf.accessors[id];const next=append(accessor(id),old.type,old.componentType,34962);if(old.min)accessors[next].min=old.min;if(old.max)accessors[next].max=old.max;attrs[key]=next;}
const index=append(reduced,'SCALAR',5125,34963);gltf.meshes[0].primitives[0]={attributes:attrs,indices:index,material:p.material};gltf.accessors=accessors;gltf.bufferViews=views;gltf.buffers=[{uri:'coast_rocks_05_web.bin',byteLength:offset}];
writeFileSync(path.join(dir,'coast_rocks_05_web.bin'),Buffer.concat(chunks));writeFileSync(path.join(dir,'coast_rocks_05_web.gltf'),JSON.stringify(gltf));
console.log({originalTriangles:indices.length/3,webTriangles:reduced.length/3,relativeError:error});
