import {useEffect,useRef} from 'react';
import {useFrame,useThree} from '@react-three/fiber';
import {PerspectiveCamera,Vector2} from 'three';
import {registerCapture,pixelRatioForQuality} from './capture';
import {useLab} from './store';
export default function RenderOutput(){
 const {gl,scene,camera,size,setDpr}=useThree(),quality=useLab(s=>s.quality),playing=useLab(s=>s.playing);
 const measurement=useRef({time:-1,frames:0}),buffer=useRef(new Vector2());
 useFrame(state=>{
  const sample=measurement.current;
  if(!playing){
   gl.getDrawingBufferSize(buffer.current);const info=`${buffer.current.x} × ${buffer.current.y} · IDLE`;
   if(useLab.getState().renderInfo!==info)useLab.getState().set({renderInfo:info});
   sample.time=-1;sample.frames=0;return;
  }
  if(sample.time<0){sample.time=state.clock.elapsedTime;sample.frames=0;return;}
  sample.frames++;
  const elapsed=state.clock.elapsedTime-sample.time;
  if(elapsed>=1){
   gl.getDrawingBufferSize(buffer.current);
   useLab.getState().set({renderInfo:`${buffer.current.x} × ${buffer.current.y} · ${Math.round(sample.frames/elapsed)} FPS`});
   sample.time=state.clock.elapsedTime;sample.frames=0;
  }
 });
 useEffect(()=>setDpr(pixelRatioForQuality(quality,size.width,size.height)),[quality,size.width,size.height,setDpr]);
 useEffect(()=>{
  registerCapture(()=>{
   const ctx=gl.getContext();if(ctx.getParameter(ctx.MAX_RENDERBUFFER_SIZE)<3840)throw new Error('This GPU context cannot allocate a 3840-pixel render buffer.');
   const previousSize=gl.getSize(new Vector2()),ratio=gl.getPixelRatio(),screenshotCamera=(camera as PerspectiveCamera).clone();
   screenshotCamera.aspect=3840/2160;screenshotCamera.updateProjectionMatrix();
   try{
    gl.setPixelRatio(1);gl.setSize(3840,2160,false);gl.render(scene,screenshotCamera);
    const url=gl.domElement.toDataURL('image/png');const link=document.createElement('a');link.href=url;link.download=`rocket-lab-${useLab.getState().time.toFixed(2)}s-3840x2160.png`;link.click();
   }finally{
    // Restore CSS size before supersampling, avoiding a transient 4K × DPR
    // allocation that can exhaust the browser's framebuffer budget.
    gl.setSize(previousSize.x,previousSize.y,false);gl.setPixelRatio(ratio);gl.render(scene,camera);
   }
  });return()=>registerCapture(null);
 },[gl,scene,camera]);
 return null;
}
