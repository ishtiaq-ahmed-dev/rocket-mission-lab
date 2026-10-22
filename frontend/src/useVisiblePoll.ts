import {useEffect} from 'react';

/** No overlapping refreshes and no background-tab polling. */
export function useVisiblePoll(refresh:()=>Promise<unknown>,interval:number,enabled=true){
 useEffect(()=>{
  if(!enabled)return;
  let stopped=false,pending=false,timer:ReturnType<typeof setTimeout>|undefined;
  const run=async()=>{
   if(stopped||pending||document.hidden)return;
   pending=true;
   try{await refresh();}finally{
    pending=false;
    if(!stopped&&!document.hidden)timer=setTimeout(()=>void run(),interval);
   }
  };
  const visibility=()=>{clearTimeout(timer);if(!document.hidden)void run();};
  void run();document.addEventListener('visibilitychange',visibility);
  return()=>{stopped=true;clearTimeout(timer);document.removeEventListener('visibilitychange',visibility);};
 },[refresh,interval,enabled]);
}
