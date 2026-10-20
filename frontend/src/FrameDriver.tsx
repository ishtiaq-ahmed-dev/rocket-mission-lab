import {useEffect} from 'react';
import {useThree} from '@react-three/fiber';
import {useLab} from './store';
import {startPlaybackClock} from './frameScheduler';

/** Render on interaction or on the bounded playback clock, never an idle loop. */
export default function FrameDriver(){
 const {invalidate}=useThree(),playing=useLab(s=>s.playing),limit=useLab(s=>s.frameLimit);
 useEffect(()=>useLab.subscribe((next,previous)=>{
  if(next.time!==previous.time||next.telemetry!==previous.telemetry||next.ghost!==previous.ghost)invalidate();
 }),[invalidate]);
 useEffect(()=>{
  const hidden=()=>{if(document.hidden)useLab.getState().set({playing:false});};
  document.addEventListener('visibilitychange',hidden);return()=>document.removeEventListener('visibilitychange',hidden);
 },[]);
 useEffect(()=>{
  invalidate();if(!playing)return;
  return startPlaybackClock({now:()=>performance.now(),request:callback=>requestAnimationFrame(callback),cancel:id=>cancelAnimationFrame(id),playing:()=>useLab.getState().playing,advance:dt=>useLab.getState().advance(dt),invalidate},limit);
 },[playing,limit,invalidate]);
 return null;
}
