import {useEffect,useRef,useState} from 'react';
import type {Frame} from './types';
import type {NativeEngineAudio} from './engineSonification';

export default function NativeAudio({frame,active,paused,headless}:{frame?:Frame;active:boolean;paused:boolean;headless:boolean}){
 const audio=useRef<NativeEngineAudio|null>(null),latest=useRef({frame,active,paused});
 const [enabled,setEnabled]=useState(false),[error,setError]=useState('');
 useEffect(()=>{
  latest.current={frame,active,paused};
  void audio.current?.update(frame,active&&!paused&&!document.hidden,.12).catch(()=>{});
 },[frame,active,paused]);
 useEffect(()=>{const visibility=()=>{const value=latest.current;void audio.current?.update(value.frame,value.active&&!value.paused&&!document.hidden,.12).catch(()=>{});};
  document.addEventListener('visibilitychange',visibility);
  return()=>{document.removeEventListener('visibilitychange',visibility);audio.current?.close();audio.current=null;};
 },[]);
 const toggle=async()=>{setError('');if(audio.current){audio.current.close();audio.current=null;setEnabled(false);return;}
  try{const {NativeEngineAudio}=await import('./engineSonification');audio.current=new NativeEngineAudio();await audio.current.update(frame,active&&!paused,.12);setEnabled(true);}
  catch(problem){audio.current?.close();audio.current=null;setError((problem as Error).message);}
 };
 return <div className="native-audio"><button className="btn subtle" disabled={!enabled&&(!active||headless)} onClick={()=>void toggle()}>{enabled?'Mute engine audio':'Enable engine audio'}</button><span>Optional synthesized engine sound · observer at ground origin · distance delay</span>{error&&<p role="alert">{error}</p>}</div>;
}
