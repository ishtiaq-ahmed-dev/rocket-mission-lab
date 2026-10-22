import {useEffect,useMemo,useRef} from 'react';
import {useFrame} from '@react-three/fiber';
import * as THREE from 'three';
import {depthVertex,depthFragment} from './shaderDepth';

/** Rendering only: spherical horizon at the study's 6,371 km Earth radius.
 * Atmospheric color is illustrative; it does not supply any flight forces. */
export default function SuborbitalWorld(){
  const sky=useRef<THREE.Mesh>(null);
  const material=useMemo(()=>new THREE.ShaderMaterial({side:THREE.BackSide,depthWrite:false,
    uniforms:{height:{value:0}},
    vertexShader:depthVertex('varying vec3 ray;void main(){ray=position;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);}'),
    fragmentShader:depthFragment(`varying vec3 ray;uniform float height;
      void main(){vec3 d=normalize(ray);float air=exp(-max(0.,height)/18000.);
      vec3 day=mix(vec3(.69,.79,.84),vec3(.12,.34,.63),pow(max(0.,d.y),.45));
      vec3 color=mix(vec3(.001,.003,.009),day,air);
      vec3 sun=normalize(vec3(-180.,260.,170.));float disc=smoothstep(.99994,.99997,dot(d,sun));
      color+=vec3(1.,.93,.78)*disc*2.;gl_FragColor=vec4(color,1.);
      #include <tonemapping_fragment>
      #include <colorspace_fragment>
      }`)}),[]);
  const atmosphere=useMemo(()=>new THREE.ShaderMaterial({transparent:true,depthWrite:false,side:THREE.BackSide,
    uniforms:{opacity:{value:0}},vertexShader:depthVertex('varying vec3 normalWorld;varying vec3 view;void main(){vec4 world=modelMatrix*vec4(position,1.);normalWorld=normalize(mat3(modelMatrix)*normal);view=cameraPosition-world.xyz;gl_Position=projectionMatrix*viewMatrix*world;}'),
    fragmentShader:depthFragment(`varying vec3 normalWorld;varying vec3 view;uniform float opacity;
      void main(){float rim=pow(1.-abs(dot(normalize(normalWorld),normalize(view))),4.);
      gl_FragColor=vec4(vec3(.16,.46,.93),rim*opacity);
      #include <tonemapping_fragment>
      #include <colorspace_fragment>
      }`)}),[]);
  useEffect(()=>()=>{material.dispose();atmosphere.dispose();},[material,atmosphere]);
  useFrame(({camera,scene})=>{
    if(sky.current)sky.current.position.copy(camera.position);
    const height=Math.max(0,camera.position.y);
    material.uniforms.height.value=height;
    atmosphere.uniforms.opacity.value=THREE.MathUtils.clamp((height-20000)/80000,0,.7);
    if(scene.fog instanceof THREE.Fog){scene.fog.near=1100+height*3;scene.fog.far=5000+height*25;}
  });
  return <>
    <mesh ref={sky} material={material} renderOrder={-100} frustumCulled={false}><sphereGeometry args={[2700000,48,32]}/></mesh>
    <mesh position={[0,-6371000,0]}><sphereGeometry args={[6370997,256,128]}/><meshStandardMaterial color="#305b70" roughness={.78} metalness={0}/></mesh>
    <mesh position={[0,-6371000,0]} material={atmosphere}><sphereGeometry args={[6431000,192,96]}/></mesh>
  </>;
}
