import {useCallback,useEffect,useState} from 'react';
import {Rocket,Radio,Square,Flame,Crosshair} from 'lucide-react';
import type {Frame} from './types';
import NumberField from './NumberField';
import {useVisiblePoll} from './useVisiblePoll';
import NativeSetup from './NativeSetup';
import type {NativeRuntime} from './NativeSetup';
import NativeHistory from './NativeHistory';
import type {NativeSample} from './NativeHistory';
import NativeAudio from './NativeAudio';

interface Status {connected:boolean;sequence?:number;updated_at?:number;runtime?:NativeRuntime;snapshot?:{engine:string;mission:string;frame:Frame;landing:[number,number];outcome:string|null;payload_attached:boolean;steps:number;headless:boolean;renderer:string;qualification:string;paused?:boolean;time_scale?:number;control_mode?:string}|null}

/** Native telemetry only: this page never creates a WebGL canvas. */
export default function NativeMonitor(){
 const [status,setStatus]=useState<Status>({connected:false}),[error,setError]=useState(''),[x,setX]=useState(80),[y,setY]=useState(40),[socketActive,setSocketActive]=useState(false);
 const [throttle,setThrottle]=useState(0),[gimbalX,setGimbalX]=useState(0),[gimbalY,setGimbalY]=useState(0),[roll,setRoll]=useState(0);
 const [history,setHistory]=useState<NativeSample[]>([]);
 const accept=useCallback((value:Status)=>{setStatus(value);const frame=value.snapshot?.frame;if(frame)setHistory(previous=>{
  if(previous.at(-1)?.t===frame.t)return previous;
  const sample={t:frame.t,clearance:Math.max(0,frame.clearance??frame.position[2]),verticalSpeed:frame.velocity[2]};
  return previous.length&&frame.t<previous.at(-1)!.t?[sample]:[...previous.slice(-119),sample];
 });},[]);
 const refresh=useCallback(async()=>{try{const response=await fetch('/api/native/status');if(response.ok)accept(await response.json());}catch{setStatus({connected:false});}},[accept]);
 useVisiblePoll(refresh,2000,!socketActive);
 useEffect(()=>{
  let socket:WebSocket|null=null;
  let retry:ReturnType<typeof setTimeout>|null=null,failures=0,disposed=false;
  const connect=()=>{if(disposed||document.hidden)return;const connection=new WebSocket(`${location.protocol==='https:'?'wss:':'ws:'}//${location.host}/api/native/stream`);socket=connection;
   connection.onopen=()=>{failures=0;setSocketActive(true);};
   connection.onclose=()=>{if(disposed||socket!==connection)return;socket=null;setSocketActive(false);if(!document.hidden&&!retry)retry=setTimeout(()=>{retry=null;connect();},Math.min(10000,500*2**Math.min(failures++,5)));};
   connection.onerror=()=>connection.close();
   connection.onmessage=event=>{try{accept(JSON.parse(event.data));}catch{/* retain last valid packet */}};
  };
  const visibility=()=>{if(retry){clearTimeout(retry);retry=null;}const previous=socket;socket=null;previous?.close();setSocketActive(false);if(!document.hidden)connect();};
  connect();document.addEventListener('visibilitychange',visibility);
  return()=>{disposed=true;document.removeEventListener('visibilitychange',visibility);if(retry)clearTimeout(retry);socket?.close();};
 },[accept]);
 const command=async(type:string,extra:Record<string,unknown>={})=>{setError('');try{const response=await fetch('/api/native/command',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({type,...extra,...(type==='retarget'?{landing:[x,y]}:{}),...(type==='manual'?{action:[throttle*2-1,gimbalX,gimbalY],roll}:{})})});const value=await response.json();if(!response.ok)throw new Error(value.detail||'Command failed');}catch(problem){setError((problem as Error).message);}};
 const snapshot=status.snapshot,frame=snapshot?.frame;
 const stale=!!status.updated_at&&Date.now()/1000-status.updated_at>3;
 const active=status.connected&&!stale;
 const controllable=active&&!['training','qualification'].includes(snapshot?.control_mode??'');
 return <div className="content-page native-monitor">
  <div className="page-head"><div><div className="breadcrumb"><Radio size={14}/>NATIVE PHYSX & RTX</div><h1>Isaac Sim flight control</h1><p className="page-sub">The native Isaac window renders the vehicle. This dashboard receives physical telemetry and sends flight commands.</p></div><span className="tag">{active?'Native engine connected':stale?'Telemetry stale':'Native engine offline'}</span></div>
  {error&&<p role="alert" className="error-banner">{error}</p>}
  <NativeSetup runtime={status.runtime} connected={active} onStarted={()=>void refresh()} onError={setError}/>
  <div className="mission-stats">{[
   ['Simulation time',frame?`${frame.t.toFixed(2)} s`:'—'],['Ground clearance',frame?`${Math.max(0,frame.clearance??frame.position[2]).toFixed(1)} m`:'—'],
   ['Speed',frame?`${Math.hypot(...frame.velocity).toFixed(2)} m/s`:'—'],['Propellant',frame?`${(frame.fuel_mass/1000).toFixed(2)} t`:'—'],
   ['Throttle',frame?`${(frame.throttle*100).toFixed(1)}%`:'—'],['Payload',snapshot?(snapshot.payload_attached?'Attached':'Released'):'—'],
  ].map(([label,value])=><section className="stat-card" key={label}><span className="field-label">{label}</span><h2>{value}</h2></section>)}</div>
  <NativeHistory samples={history}/>
  <section className="panel" style={{padding:24,marginTop:20}}><h2><Rocket size={20}/>Native simulation</h2>
   <p>{snapshot?`${snapshot.engine} · ${snapshot.mission} · ${snapshot.headless?'headless':snapshot.renderer} · ${snapshot.steps.toLocaleString()} control steps`:'Start the standalone native runner to connect. No browser 3D engine is loaded on this page.'}</p>
   <p>{snapshot?.qualification||'Native physics and mission reliability are qualified separately from the archived MuJoCo results.'}</p>
   <p>{snapshot?.outcome?`Last outcome: ${snapshot.outcome.replaceAll('_',' ')}`:'Commands take effect at the next physical control step.'}</p>
   {snapshot&&<p>{snapshot.paused?'Physics paused':`Physics running · ${snapshot.time_scale??1}× visual clock`} · {snapshot.control_mode??'guidance'} control · Applied target: {snapshot.landing[0].toFixed(1)}, {snapshot.landing[1].toFixed(1)} m</p>}
   <div className="compare-row"><button className="btn subtle" disabled={!controllable} onClick={()=>void command(snapshot?.paused?'resume':'pause')}>{snapshot?.paused?'Resume physics':'Pause physics'}</button><button className="btn subtle" disabled={!controllable||!snapshot?.paused} onClick={()=>void command('step')}>Advance 0.1 s</button><label>Camera <select aria-label="Native camera" className="full-select" disabled={!controllable||snapshot?.headless} defaultValue="free" onChange={event=>void command('camera',{mode:event.target.value})}><option value="free">Free orbit</option><option value="follow">Follow vehicle</option><option value="vehicle">Frame vehicle</option><option value="launch">Launch site</option><option value="landing">Landing site</option></select></label></div>
   <NativeAudio frame={frame} active={active} paused={!!snapshot?.paused} headless={!!snapshot?.headless}/>
   <details><summary>Standalone launch and diagnostics</summary><pre style={{overflowX:'auto',padding:16,background:'#f6f4fb',color:'#403751'}}>powershell -File scripts/run_isaac.ps1{`\n`}powershell -File scripts/run_isaac.ps1 -Headless -Diagnostic</pre></details>
   <p>The Isaac viewport provides native orbit, pan, zoom and camera selection. Automatic following is optional through <code>--follow-camera</code>.</p>
  </section>
  <section className="panel" style={{padding:24,marginTop:20}}><h3><Crosshair size={18}/>Landing command</h3><div className="retarget-inputs"><label>East · m<NumberField label="Native landing X" value={x} min={-10000} max={10000} step={5} onCommit={setX}/></label><label>North · m<NumberField label="Native landing Y" value={y} min={-10000} max={10000} step={5} onCommit={setY}/></label></div>
   <div className="compare-row"><button className="btn primary" disabled={!controllable} onClick={()=>void command('retarget')}><Crosshair size={15}/>Retarget</button><button className="btn subtle" disabled={!controllable||!snapshot?.payload_attached} onClick={()=>void command('detach')}>Cut off & release payload</button><button className="btn subtle" disabled={!controllable} onClick={()=>void command('cutoff')}><Flame size={15}/>Engine cutoff</button><button className="btn subtle" disabled={!active} onClick={()=>void command('stop')}><Square size={15}/>Stop native run</button></div>
   <p>Payload release waits for engine shutdown. A new target can be physically unreachable; telemetry and outcomes retain failures.</p>
   <details><summary>Manual engine control</summary><p>Manual control holds your commanded throttle and gimbal. It bypasses guidance and can crash the vehicle. A single gimballed engine cannot independently command all six degrees of freedom.</p>
    <label>Throttle command · {(throttle*100).toFixed(0)}%<input aria-label="Native manual throttle" type="range" min={0} max={1} step={.01} value={throttle} onChange={event=>setThrottle(+event.target.value)}/></label>
    <label>Gimbal X · {(gimbalX*8).toFixed(1)}°<input aria-label="Native manual gimbal X" type="range" min={-1} max={1} step={.01} value={gimbalX} onChange={event=>setGimbalX(+event.target.value)}/></label>
    <label>Gimbal Y · {(gimbalY*8).toFixed(1)}°<input aria-label="Native manual gimbal Y" type="range" min={-1} max={1} step={.01} value={gimbalY} onChange={event=>setGimbalY(+event.target.value)}/></label>
    <label>Roll jets · {(roll*100).toFixed(0)}%<input aria-label="Native manual roll jets" type="range" min={-1} max={1} step={.01} value={roll} onChange={event=>setRoll(+event.target.value)}/></label>
    <p>Roll uses opposed cold-gas jets with a finite 40 kg supply. Zero commands close their valves.</p>
    <button className="btn subtle" disabled={!controllable} onClick={()=>void command('manual')}>Apply manual engine command</button><button className="btn primary" disabled={!controllable} onClick={()=>void command('guidance')}>Resume guidance</button>
   </details>
  </section>
 </div>;
}
