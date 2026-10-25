import {Component,Suspense,lazy,memo,useEffect,useMemo,useState} from 'react';
import type {ErrorInfo,ReactNode} from 'react';
import {
  Activity,ArrowDown,ArrowRight,ArrowUp,ArrowUpRight,Box,Check,ChevronDown,ChevronRight,
  CircleAlert,CircleCheck,Clapperboard,Compass,Crosshair,Download,Expand,Flame,FlaskConical,
  Focus,Fuel,Gauge,Layers,LoaderCircle,MapPin,Pause,Play,RotateCcw,Rocket,
  ShieldCheck,Sparkles,Target,Timer,TrendingDown,TrendingUp,Volume2,VolumeX,Wind,X,Zap,
} from 'lucide-react';
import {Area,Bar,BarChart,CartesianGrid,Cell,ComposedChart,Line,ReferenceLine,ResponsiveContainer,Tooltip,XAxis,YAxis} from 'recharts';
import {useLab,useInstrumentTime} from './store';
import {missionAudio} from './audio';
import {capture4k} from './capture';
import FlightEvents from './FlightEvents';
import FlightPlanEditor from './FlightPlanEditor';
import NumberField from './NumberField';
import {compact,decimatedFrames,frameMetrics,sample,landingAt} from './telemetry';
import type {Checkpoint,Mission,Method,Retarget,Telemetry} from './types';

const missionBlurbs:Record<Mission,string>={landing:'Fly a precision powered descent to the recovery pad coordinates.',takeoff:'Launch from the pad, climb to the separation altitude and hit the target ascent speed.',combined:'Launch, release an unpowered upper stage and return the booster to the recovery site.'};
const levels=['Untuned','PID feedback','Convex guidance','LQR guidance'];
const rlLevels=['Early checkpoint','Intermediate','Later checkpoint','Best measured'];
const captions=['An untuned controller reveals the failure modes.','Feedback gains improve the trajectory.','Constrained guidance plans a powered descent.','LQR stabilizes translation and attitude with descent feedforward.'];
const formatTime=(t:number)=>`${Math.floor(t/60).toString().padStart(2,'0')}:${(t%60).toFixed(1).padStart(4,'0')}`;
const fixed=(v:number,d=1)=>Number.isFinite(v)?v.toFixed(d):'—';
const signed=(v:number,d=1)=>`${v>0?'+':''}${fixed(v,d)}`;
const Scene=memo(lazy(()=>import('./Scene')));
class SceneBoundary extends Component<{children:ReactNode},{error:string}>{
  state={error:''};
  static getDerivedStateFromError(error:Error){return {error:error.message||String(error)};}
  componentDidCatch(error:Error,info:ErrorInfo){console.error(error,info);}
  render(){return this.state.error?<div className="scene-fallback"><Box size={30}/><h3>3D view could not start</h3><p>{this.state.error}</p><button className="btn subtle" onClick={()=>this.setState({error:''})}>Retry 3D view</button></div>:this.props.children;}
}

export type MissionView='Overview'|'Flight deck'|'Telemetry'|'Mission plan';

export interface MissionControlProps {
  mission:Mission;method:Method;level:number;seed:number;checkpoint:string;
  checkpoints:Checkpoint[];busy:boolean;online:boolean;story:boolean;compare:string;
  onMission:(mission:Mission,method:Method,level:number)=>void;
  onLevel:(level:number)=>void;onCheckpoint:(id:string)=>void;onSeed:(seed:number)=>void;
  onRun:()=>void;onRetarget:(time:number,landing:[number,number])=>void;onGhost:()=>void;
  onStory:()=>void;onCompare:(value:string)=>void;onExport:()=>void;onError:(message:string)=>void;
  onOpenNotes:()=>void;
}

export default function MissionControl(props:MissionControlProps){
  const {mission,checkpoints,busy,online}=props;
  const telemetry=useLab(s=>s.telemetry),time=useInstrumentTime();
  const playing=useLab(s=>s.playing);
  const planX=useLab(s=>s.flightPlan.landing[0]),planY=useLab(s=>s.flightPlan.landing[1]);
  const [view,setView]=useState<MissionView>('Overview');
  const [targetX,setTargetX]=useState(planX);
  const [targetY,setTargetY]=useState(planY);
  const duration=telemetry?.frames.at(-1)?.t||1;
  const ended=time>=duration;
  const frame=telemetry?sample(telemetry.frames,time):null;
  const metrics=frame&&telemetry?frameMetrics(frame,telemetry.rocket_length):null;
  const earlier=telemetry&&time>1?sample(telemetry.frames,Math.max(0,time-5)):null;
  const earlierMetrics=earlier&&telemetry?frameMetrics(earlier,telemetry.rocket_length):null;
  const speedTrend=metrics&&earlierMetrics?metrics.speed-earlierMetrics.speed:0;
  const fuelPercent=frame&&telemetry?frame.fuel_mass/telemetry.initial_fuel*100:0;
  const appliedPlan=telemetry?.run.flight_plan?{...telemetry.run.flight_plan,landing:landingAt(telemetry.run,time)}:undefined;
  const selectedCps=checkpoints.filter(c=>c.mission===mission);
  const retargets:Retarget[]=telemetry?.run.retargets||[];
  const lastRetarget=retargets.filter(event=>event.t<=time+1e-8).at(-1);
  const transfer=appliedPlan?Math.hypot(appliedPlan.launch[0]-appliedPlan.landing[0],appliedPlan.launch[1]-appliedPlan.landing[1]):0;

  useEffect(()=>{setTargetX(planX);setTargetY(planY);},[planX,planY]);

  const chartData=useMemo(()=>{
    if(!telemetry)return [];
    return decimatedFrames(telemetry.frames,240).map(value=>{
      const m=frameMetrics(value,telemetry.rocket_length);
      return {t:+value.t.toFixed(1),altitude:+m.altitude.toFixed(1),speed:+m.speed.toFixed(2),throttle:+(value.throttle*100).toFixed(1),fuel:+(value.fuel_mass/1000).toFixed(2)};
    });
  },[telemetry]);

  const engineBars=useMemo(()=>{
    if(!telemetry)return [];
    const buckets=18,size=Math.max(1,Math.ceil(telemetry.frames.length/buckets)),values=[];
    for(let index=0;index<telemetry.frames.length;index+=size){
      const slice=telemetry.frames.slice(index,index+size);
      const throttle=slice.reduce((sum,value)=>sum+value.throttle,0)/slice.length*100;
      values.push({t:+slice[0].t.toFixed(1),throttle:+throttle.toFixed(1),fuel:+(slice.at(-1)!.fuel_mass/1000).toFixed(2)});
    }
    return values;
  },[telemetry]);

  const events=useMemo(()=>{
    if(!telemetry)return [];
    const frames=telemetry.frames,values:{t:number;label:string;detail:string;icon:'engine'|'target'|'stage'|'complete'}[]=[];
    const ignition=frames.find(value=>value.throttle>.05);if(ignition)values.push({t:ignition.t,label:'Engine ignition',detail:`${(ignition.throttle*100).toFixed(0)}% throttle`,icon:'engine'});
    for(const retarget of telemetry.run.retargets||[])values.push({t:retarget.t,label:'Landing target moved',detail:`${retarget.previous_landing.map(v=>v.toFixed(0)).join(', ')} → ${retarget.landing.map(v=>v.toFixed(0)).join(', ')} m`,icon:'target'});
    if(telemetry.run.launch_release_time!=null)values.push({t:telemetry.run.launch_release_time,label:'Hold-down release',detail:'Sustained thrust margin achieved · supports opening',icon:'stage'});
    if(telemetry.run.separation)values.push({t:telemetry.run.separation.t,label:'Stage separation',detail:`${(telemetry.run.separation.mass/1000).toFixed(1)} t released · ${frames.some(f=>f.upper_stage)?'independent unpowered dynamics':'archived ballistic preview'}`,icon:'stage'});
    const cutoff=frames.find((value,index)=>index>0&&value.throttle===0&&frames[index-1].throttle>0);
    if(cutoff)values.push({t:cutoff.t,label:'Main engine cutoff',detail:`${(cutoff.fuel_mass/1000).toFixed(2)} t propellant remaining`,icon:'engine'});
    const relight=cutoff?frames.find(value=>value.t>cutoff.t&&value.throttle>0):undefined;
    if(relight)values.push({t:relight.t,label:'Engine relight',detail:`${(relight.throttle*100).toFixed(0)}% throttle`,icon:'engine'});
    values.push({t:telemetry.run.duration,label:telemetry.run.outcome==='success'?'Flight complete':'Flight ended',detail:`${telemetry.run.outcome.replaceAll('_',' ')} · ${telemetry.run.touchdown_speed.toFixed(2)} m/s · ${telemetry.run.pad_distance.toFixed(2)} m offset`,icon:'complete'});
    return values.sort((a,b)=>a.t-b.t);
  },[telemetry]);

  const playbackStatus=time===0?'Ready':playing?'Playing':'Paused';
  const status=!telemetry?'Awaiting flight':ended?(telemetry.run.outcome==='success'?'Nominal':'Review needed'):playbackStatus;
  const statusTone=!telemetry?'neutral':ended?(telemetry.run.outcome==='success'?'good':'bad'):'live';
  const retargetReady=!!telemetry&&online&&!busy&&!ended&&(metrics?.altitude??0)>=20&&telemetry.run.mission!=='takeoff';

  const jump=(t:number)=>useLab.getState().set({time:Math.min(t,telemetry?.frames.at(-1)?.t||t),playing:false});
  const selectView=(next:MissionView)=>{setView(next);if(next!=='Flight deck'&&next!=='Overview')useLab.getState().set({playing:false});};

  return <div className="page mission-page">
    <header className="page-head">
      <div>
        <div className="breadcrumb"><span className="live-dot"/>MISSION CONTROL <span>/</span> LIVE FLIGHT LAB</div>
        <h1>Every flight, measured.</h1>
        <p className="page-sub">A 6-DOF booster simulation with configurable launch and landing sites, sampled engine telemetry and recorded evidence.</p>
      </div>
      <div className="head-actions">
        <span className={`online-pill ${online?'online':''}`}><span className="status-dot on"/>{online?'Local engine online':'Offline replay'}</span>
        <button className="icon-pill" aria-label="Read the flight manual" title="Flight manual" onClick={props.onOpenNotes}><FlaskConical size={17}/></button>
        <button className="btn primary" disabled={busy} onClick={props.onRun}>{busy?<LoaderCircle size={16} className="spin"/>:<Sparkles size={16}/>}Run flight</button>
      </div>
    </header>

    <section className="workspace">
      <div className="workspace-head">
        <div className="workspace-title">
          <h2>Mission overview</h2>
          <p>{missionBlurbs[telemetry?.run.mission||mission]}</p>
        </div>
        <div className="tabs" role="tablist" aria-label="Mission control views">
          {(['Overview','Flight deck','Telemetry','Mission plan'] as const).map(tab=><button key={tab} role="tab" aria-selected={view===tab} className={`tab ${view===tab?'active':''}`} onClick={()=>selectView(tab)}>{tab}</button>)}
        </div>
        <button className="btn primary compact-btn" disabled={busy} onClick={props.onRun}>{busy?<LoaderCircle size={15} className="spin"/>:<Play size={14} fill="currentColor"/>}Run flight</button>
      </div>

      <div className="workspace-body">
      {view==='Overview'&&<>
        <div className="section-head">
          <div><h3>Flight overview</h3><p>Live values from the recorded simulation, sampled at the playback clock.</p></div>
          <span className={`status-chip ${statusTone}`}>{statusTone==='live'?<span className="status-dot on"/>:statusTone==='good'?<CircleCheck size={14}/>:statusTone==='bad'?<CircleAlert size={14}/>:<Timer size={14}/>}{status}</span>
        </div>
        <div className="kpi-grid">
          <article className="kpi-card">
            <div className="kpi-top"><span className="kpi-icon purple"><Activity size={18}/></span><span className="kpi-label">Mission status</span><span className={`delta ${statusTone==='bad'?'warn':statusTone==='good'?'good':''}`}>{telemetry?(ended?(telemetry.run.outcome==='success'?'COMPLETE':'CHECK'):'LIVE'):'READY'}</span></div>
            <strong className="kpi-value">{telemetry?(ended?(telemetry.run.outcome==='success'?'Nominal':'Review'):playbackStatus):'Ready'}</strong>
            <span className="kpi-sub">{telemetry?`${telemetry.run.method==='rl'?`${telemetry.run.algorithm} agent`:`Classical L${telemetry.run.level}`} · seed ${telemetry.run.seed}`:'Select a mission and run a flight'}</span>
          </article>
          <article className="kpi-card">
            <div className="kpi-top"><span className="kpi-icon blue"><Gauge size={18}/></span><span className="kpi-label">Total speed</span><span className={`delta ${speedTrend<0?'good':''}`}>{speedTrend<0?<TrendingDown size={12}/>:<TrendingUp size={12}/>}{`${signed(speedTrend,1)} m/s`}</span></div>
            <strong className="kpi-value">{fixed(metrics?.speed||0,1)}<small>m/s</small></strong>
            <span className="kpi-sub">Vertical {signed(metrics?.verticalSpeed||0,1)} · lateral {fixed(metrics?.horizontalSpeed||0,1)} m/s</span>
          </article>
          <article className="kpi-card">
            <div className="kpi-top"><span className="kpi-icon amber"><ArrowDown size={18}/></span><span className="kpi-label">Altitude AGL</span><span className="delta neutral">{telemetry?.run.mission==='takeoff'?`TARGET ${fixed(telemetry?.run.target_altitude??telemetry?.run.flight_plan?.separation_altitude??NaN,0)} m`:'ABOVE PAD'}</span></div>
            <strong className="kpi-value">{fixed(metrics?.altitude||0,1)}<small>m</small></strong>
            <span className="kpi-sub">{telemetry?.run.mission==='takeoff'?`Ascent ${signed(metrics?.verticalSpeed||0,1)} m/s${telemetry?.run.target_velocity!=null?` · target ${fixed(telemetry.run.target_velocity,0)} m/s`:''}`:`Descent ${signed(metrics?.verticalSpeed||0,1)} m/s · tilt ${fixed(metrics?.tilt||0,2)}°`}</span>
          </article>
          <article className="kpi-card">
            <div className="kpi-top"><span className="kpi-icon teal"><Fuel size={18}/></span><span className="kpi-label">Propellant</span><span className="delta neutral">{fixed(fuelPercent,0)}%</span></div>
            <strong className="kpi-value">{fixed(fuelPercent,1)}<small>%</small></strong>
            <div className="kpi-track"><i style={{width:`${Math.max(0,Math.min(100,fuelPercent))}%`}}/></div>
            <span className="kpi-sub">{frame?(frame.fuel_mass/1000).toFixed(2):'—'} t remaining · throttle {fixed((frame?.throttle||0)*100,0)}%</span>
          </article>
        </div>

        <div className="flight-grid">
          <LiveView {...props} telemetry={telemetry} metrics={metrics} duration={duration} ended={ended} plan={appliedPlan}/>
          <SetupPanel {...props} selectedCps={selectedCps} targetX={targetX} targetY={targetY} setTargetX={setTargetX} setTargetY={setTargetY} retargetReady={retargetReady} lastRetarget={lastRetarget} onJump={jump}/>
        </div>

        <div className="chart-grid">
          <ProfileChart data={chartData} time={time} duration={duration} currentAltitude={metrics?.altitude||0} currentSpeed={metrics?.speed||0} mission={telemetry?.run.mission||mission} tolerance={telemetry?.run.landing_tolerance??5}/>
          <EngineChart data={engineBars} time={time} throttle={(frame?.throttle||0)*100} minimum={(telemetry?.min_throttle??.35)*100}/>
        </div>

        <div className="bottom-grid">
          <SitePanel plan={appliedPlan} transfer={transfer} retargets={retargets} onEdit={()=>selectView('Mission plan')}/>
          <FlightLog events={events} onJump={jump} onAll={()=>selectView('Telemetry')}/>
        </div>
      </>}

      {view==='Flight deck'&&<>
        <div className="section-head"><div><h3>Flight deck</h3><p>Scrub the recorded flight, inspect events and configure the next run.</p></div><span className="status-chip live"><span className="status-dot on"/>6-DOF · MuJoCo</span></div>
        <div className="flight-grid single-setup">
          <LiveView {...props} telemetry={telemetry} metrics={metrics} duration={duration} ended={ended} plan={appliedPlan}/>
          <SetupPanel {...props} selectedCps={selectedCps} targetX={targetX} targetY={targetY} setTargetX={setTargetX} setTargetY={setTargetY} retargetReady={retargetReady} lastRetarget={lastRetarget} onJump={jump}/>
        </div>
        <InstrumentRow metrics={metrics} frame={frame} fuelPercent={fuelPercent} initialFuel={telemetry?.initial_fuel||1}/>
        <FlightEvents telemetry={telemetry}/>
        {telemetry&&ended&&<OutcomeCard telemetry={telemetry}/>}
      </>}

      {view==='Telemetry'&&<>
        <div className="section-head"><div><h3>Flight telemetry</h3><p>Every value below is sampled from the recorded MuJoCo state, not a scripted animation.</p></div><button className="btn subtle" onClick={props.onExport}><Download size={15}/>Export JSON</button></div>
        <InstrumentRow metrics={metrics} frame={frame} fuelPercent={fuelPercent} initialFuel={telemetry?.initial_fuel||1}/>
        <div className="chart-grid">
          <ProfileChart data={chartData} time={time} duration={duration} currentAltitude={metrics?.altitude||0} currentSpeed={metrics?.speed||0} mission={telemetry?.run.mission||mission} tolerance={telemetry?.run.landing_tolerance??5}/>
          <EngineChart data={engineBars} time={time} throttle={(frame?.throttle||0)*100} minimum={(telemetry?.min_throttle??.35)*100}/>
        </div>
        <MiniCharts data={chartData} time={time}/>
        <FlightEvents telemetry={telemetry}/>
        <FlightLog events={events} onJump={jump}/>
      </>}

      {view==='Mission plan'&&<>
        <div className="section-head"><div><h3>Mission plan</h3><p>Local meters on a flat Z = 0 surface. X is east and Y is north; these are not geographic coordinates.</p></div><span className="status-chip neutral"><MapPin size={14}/>{transfer.toFixed(0)} m transfer</span></div>
        <div className="plan-grid">
          <section className="plan-card">
            <div className="card-title"><h3>Launch and landing geometry</h3><span className="chip">Applied with Run flight</span></div>
            <div className="plan-editor"><FlightPlanEditor/></div>
            <div className="plan-facts">
              <div><span>Launch site</span><strong>{appliedPlan?appliedPlan.launch.map(v=>v.toFixed(0)).join(', '):'—'} m</strong></div>
              <div><span>Landing site</span><strong>{appliedPlan?appliedPlan.landing.map(v=>v.toFixed(0)).join(', '):'—'} m</strong></div>
              <div><span>Separation altitude</span><strong>{appliedPlan?`${appliedPlan.separation_altitude} m`:'—'}</strong></div>
              <div><span>Surface transfer</span><strong>{transfer.toFixed(0)} m</strong></div>
            </div>
          </section>
          <RetargetCard targetX={targetX} targetY={targetY} setTargetX={setTargetX} setTargetY={setTargetY} time={time} ready={retargetReady} onRetarget={()=>props.onRetarget(time,[targetX,targetY])} lastRetarget={lastRetarget} mission={telemetry?.run.mission||mission} plan={appliedPlan}/>
        </div>
        <section className="plan-card">
          <div className="card-title"><h3>What the plan controls</h3></div>
          <div className="info-grid">
            <div><span className="kpi-icon purple"><Rocket size={17}/></span><strong>Launch coordinates</strong><p>The booster starts on this prepared pad for takeoff and combined flights, and landing starts in the air above it.</p></div>
            <div><span className="kpi-icon blue"><Target size={17}/></span><strong>Landing coordinates</strong><p>The touchdown target. Change it before a run or command a new target during playback to fly a divert.</p></div>
            <div><span className="kpi-icon amber"><ArrowUp size={17}/></span><strong>Separation altitude</strong><p>Combined flights command cutoff at this altitude, finish engine shutdown, then release the 2.5 t stage into independently integrated unpowered flight.</p></div>
            <div><span className="kpi-icon teal"><ShieldCheck size={17}/></span><strong>Reachability</strong><p>Accepted input ranges are not a flight envelope. Fuel, engine-floor thrust, wind and control limits can still cause a crash or a missed pad.</p></div>
          </div>
        </section>
      </>}
      </div>
    </section>
    <footer className="page-footer"><span><FlaskConical size={13}/>EDUCATIONAL FLIGHT RESEARCH · APPROXIMATE VEHICLE PARAMETERS</span><span>z-up physics · quaternion attitude · SI units <span className="orange-text">/</span> v1.1</span></footer>
  </div>;
}

function LiveView({telemetry,metrics,duration,ended,plan,story,level,busy,onError}:MissionControlProps&{telemetry:Telemetry|null;metrics:ReturnType<typeof frameMetrics>|null;duration:number;ended:boolean;plan:Telemetry['run']['flight_plan']}){
  const time=useInstrumentTime(),playing=useLab(s=>s.playing),speed=useLab(s=>s.speed);
  const sound=useLab(s=>s.sound),quality=useLab(s=>s.quality),trail=useLab(s=>s.trail),pad=useLab(s=>s.pad);
  const camera=useLab(s=>s.camera),cameraTool=useLab(s=>s.cameraTool),followRocket=useLab(s=>s.followRocket);
  const cameraDistance=useLab(s=>s.cameraDistance),renderInfo=useLab(s=>s.renderInfo),recording=useLab(s=>s.recording);
  const ghost=useLab(s=>s.ghost);
  const retarget=telemetry?.run.retargets?.filter(event=>event.t<=time+1e-8).at(-1);
  const [showHud,setShowHud]=useState(true);

  // Keyboard shortcut to toggle HUD
  useEffect(()=>{
    const onKey=(e:KeyboardEvent)=>{
      if((e.target as HTMLElement).matches('input,select,textarea')||e.ctrlKey||e.metaKey) return;
      if(e.code==='KeyH') setShowHud(prev=>!prev);
    };
    window.addEventListener('keydown',onKey);
    return()=>window.removeEventListener('keydown',onKey);
  },[]);

  // Export telemetry as RFC-4180 CSV for scientific analysis
  const exportCSV=()=>{
    if(!telemetry) return;
    const headers=['time_s','pos_x_m','pos_y_m','altitude_agl_m','vel_x_mps','vel_y_mps','vel_z_mps','speed_mps','tilt_deg','throttle_pct','fuel_kg','gimbal_x_rad','gimbal_y_rad'];
    const rows=telemetry.frames.map(f=>{
      const m=frameMetrics(f,telemetry.rocket_length);
      return [
        f.t.toFixed(3),f.position[0].toFixed(3),f.position[1].toFixed(3),m.altitude.toFixed(3),
        f.velocity[0].toFixed(3),f.velocity[1].toFixed(3),f.velocity[2].toFixed(3),m.speed.toFixed(3),
        m.tilt.toFixed(2),(f.throttle*100).toFixed(1),f.fuel_mass.toFixed(1),f.gimbal[0].toFixed(4),f.gimbal[1].toFixed(4)
      ].join(',');
    });
    const blob=new Blob([[headers.join(','),...rows].join('\n')],{type:'text/csv'});
    const url=URL.createObjectURL(blob);
    const a=document.createElement('a');
    a.href=url;a.download=`flight_telemetry_${telemetry.run.id}.csv`;a.click();
    URL.revokeObjectURL(url);
  };

  const fSample=telemetry?sample(telemetry.frames,time):null;
  const currentThrottle=fSample?.throttle||0;
  const currentFuel=fSample?.fuel_mass||0;
  const targetErr=telemetry&&plan&&telemetry.run.mission!=='takeoff'
    ? Math.hypot(fSample?fSample.position[0]-plan.landing[0]:0,fSample?fSample.position[1]-plan.landing[1]:0)
    : 0;
  const mach=((metrics?.speed||0)/340.3).toFixed(2);

  return <section className="live-card" aria-label="3D rocket world">
    <div className="live-head">
      <div className="live-title"><span className="live-dot"/>Flight playback <span className="chip">{pad==='Ship'?'Offshore':'Coastal'} range</span><span className="chip accent">6-DOF PhysX</span></div>
      <div className="live-tools">
        <button aria-label={sound?'Mute mission sound':'Enable mission sound'} title="Engine and wind sound" className={sound?'tool active':''} onClick={()=>{if(sound)missionAudio.mute();else void missionAudio.enable().catch(e=>onError(String(e)));}}>{sound?<Volume2 size={15}/>:<VolumeX size={15}/>}</button>
        <select aria-label="Environment" value={pad} onChange={e=>useLab.getState().set({pad:e.target.value})}><option>Coastal</option><option>Ship</option></select>
        <select aria-label="Trajectory display" value={trail} onChange={e=>useLab.getState().set({trail:e.target.value as 'Off'|'Flown'|'Full'})}><option value="Off">No trail</option><option value="Flown">Flown trail</option><option value="Full">Full path</option></select>
        <select aria-label="Graphics quality" value={quality} onChange={e=>useLab.getState().set({quality:e.target.value,frameLimit:e.target.value==='Performance'?30:60})}>
          <option value="Performance">Eco (30 FPS · Low GPU)</option>
          <option value="Balanced">Balanced (60 FPS)</option>
          <option value="High">High Detail (60 FPS)</option>
          <option value="Ultra">Research Ultra (High-DPI)</option>
        </select>
        <button aria-label="Toggle HUD" title="Toggle Avionics HUD (Key H)" className={showHud?'tool active':''} onClick={()=>setShowHud(!showHud)}><Gauge size={15}/></button>
        <button aria-label="Export CSV" title="Export CSV for Research (Pandas/MATLAB)" onClick={exportCSV}><Download size={15}/></button>
        <button aria-label="Export 4K still" title="Export 3840 × 2160 PNG" onClick={()=>{try{capture4k();}catch(e){onError(String(e));}}}><Clapperboard size={15}/></button>
        <button title="Recording mode · Escape to exit" aria-label="Recording mode" className={recording?'tool active':''} onClick={()=>useLab.getState().set({recording:!recording})}><Expand size={15}/></button>
        <button title="Reset camera (Key R)" aria-label="Reset camera" onClick={()=>useLab.getState().set({camera:'Rocket',cameraRevision:useLab.getState().cameraRevision+1,followRocket:true})}><Focus size={15}/></button>
      </div>
    </div>
    <div className="viewport">
      <SceneBoundary><Suspense fallback={<div className="scene-fallback"><LoaderCircle className="spin"/>Preparing the flight world…</div>}><Scene/></Suspense></SceneBoundary>
      <div className="scene-label"><span className="status-dot on"/>FLIGHT RANGE <span>/</span> {pad==='Ship'?'OFFSHORE PLATFORM':'COASTAL RANGE'}<small>{telemetry?'6-DOF MUJOCO ACCELERATED':'OFFLINE REPLAY'}</small></div>
      
      {showHud&&(
        <div className="floating-hud aerospace-hud">
          <div>
            <span>ALTITUDE AGL</span>
            <strong data-testid="altitude">{fixed(metrics?.altitude||0,1)}<small>m</small></strong>
            <span className="hud-sub-metric">{metrics?.verticalSpeed!=null&&metrics.verticalSpeed>=0?'▲ +':'▼ '}{fixed(metrics?.verticalSpeed||0,1)} m/s vert</span>
          </div>
          <div>
            <span>TOTAL VELOCITY</span>
            <strong>{fixed(metrics?.speed||0,1)}<small>m/s</small></strong>
            <span className="hud-sub-metric">M {mach} · Horiz {fixed(metrics?.horizontalSpeed||0,1)} m/s</span>
          </div>
          <div>
            <span>ATTITUDE & TWR</span>
            <strong>{fixed(metrics?.tilt||0,1)}<small>° tilt</small></strong>
            <span className="hud-sub-metric">Throttle {fixed(currentThrottle*100,0)}% · {(currentFuel/1000).toFixed(2)} t fuel</span>
          </div>
          {telemetry&&plan&&telemetry.run.mission!=='takeoff'&&(
            <div>
              <span>LANDING TARGET OFFSET</span>
              <strong data-testid="target-offset">{targetErr.toFixed(2)}<small>m</small></strong>
              <span className="hud-sub-metric">Pad [{(plan?.landing||[1050,250])[0]}, {(plan?.landing||[1050,250])[1]}]</span>
            </div>
          )}
          <div className="hud-phase"><span className="status-dot on"/>{ended?'FLIGHT COMPLETED':framePhase(time,telemetry)}</div>
        </div>
      )}

      <div className="scene-coordinate">
        <span>LOCAL METERS · Z UP · QUATERNION ATTITUDE</span>
        {plan&&<span className="applied-plan">LAUNCH {plan.launch.join(', ')} → LAND {plan.landing.join(', ')}<br/>SEPARATION {plan.separation_altitude} m</span>}
        {retarget&&<span className="retarget-flag">RETARGET T+{retarget.t.toFixed(1)} s → {retarget.landing.map(v=>v.toFixed(0)).join(', ')}</span>}
        <span>CAM {cameraDistance>=1000?`${(cameraDistance/1000).toFixed(1)} km`:`${cameraDistance} m`} · {camera.toUpperCase()}</span>
        <span>{renderInfo}</span>
      </div>
      <div className="navigation-tools" role="group" aria-label="3D mouse controls">
        {(['Rotate','Pan'] as const).map(tool=><button key={tool} aria-pressed={cameraTool===tool} className={cameraTool===tool?'selected':''} onClick={()=>useLab.getState().set({cameraTool:tool})}>{tool}</button>)}
        <button aria-label="Zoom in" onClick={()=>useLab.getState().set({cameraCommand:'In',commandRevision:useLab.getState().commandRevision+1})}>+</button>
        <button aria-label="Zoom out" onClick={()=>useLab.getState().set({cameraCommand:'Out',commandRevision:useLab.getState().commandRevision+1})}>−</button>
        <button aria-pressed={followRocket} className={followRocket?'selected':''} onClick={()=>useLab.getState().set({followRocket:!followRocket})}>Follow {followRocket?'on':'off'}</button>
      </div>
      <div className="compass"><span>N</span><i/><span className="compass-e">E</span></div>
      {telemetry&&<div className="playback">
        <div className="transport">
          <button aria-label="Restart playback" onClick={()=>useLab.getState().set({time:0,playing:true})}><RotateCcw size={16}/></button>
          <button className="play-button" aria-label={playing?'Pause playback':'Play playback'} onClick={()=>useLab.getState().set({playing:!playing,time:ended?0:time})}>{playing?<Pause size={15} fill="currentColor"/>:<Play size={15} fill="currentColor"/>}</button>
          <span className="timecode">{formatTime(time)}<span> / {formatTime(duration)}</span> <span className="timecode-badge">1:1 REAL TIME</span></span>
        </div>
        <input aria-label="Playback position" className="scrubber" type="range" min={0} max={duration} step={.02} value={time} onInput={e=>useLab.getState().set({time:+e.currentTarget.value,playing:false})} onChange={e=>useLab.getState().set({time:+e.target.value,playing:false})}/>
        <select aria-label="Playback speed" value={speed} onChange={e=>useLab.getState().set({speed:+e.target.value})}>{[.25,.5,1,2,4].map(value=><option key={value} value={value}>{value===1?'1.0× (Real Time)':`${value}×`}</option>)}</select>
      </div>}
      {story&&<div className="story-caption"><span>CHAPTER 0{level} / 04</span><strong>{captions[Math.max(0,Math.min(3,level-1))]}</strong></div>}
      {ghost&&<div className="ghost-legend"><span/>CURRENT RUN<i/>COMPARISON · L{ghost.run.level}<button aria-label="Remove comparison" onClick={()=>useLab.getState().set({ghost:null})}><X size={12}/></button></div>}
      {busy&&<div className="loading-overlay"><LoaderCircle className="spin"/>Computing flight…</div>}
      
      {/* 6 Dedicated Aerospace Camera Views with Hotkey Badges */}
      <div className="camera-bar">
        <span><Focus size={13}/>CAMERA</span>
        {[
          {id:'Rocket',label:'Orbit',hotkey:'1',title:'Free 360° inspection orbit (Key 1)'},
          {id:'Chase',label:'Chase',hotkey:'2',title:'Aerodynamic trajectory chase (Key 2)'},
          {id:'Tower',label:'Tower',hotkey:'3',title:'Launch service tower optical tracking (Key 3)'},
          {id:'Onboard',label:'Engine',hotkey:'4',title:'Onboard nozzle & grid fins view (Key 4)'},
          {id:'Pad',label:'Pad LZ-1',hotkey:'5',title:'Touchdown landing zone telephoto (Key 5)'},
          {id:'Mission',label:'Corridor',hotkey:'6',title:'Wide mission corridor overview (Key 6)'},
          {id:'Top-down',label:'Top-down',hotkey:'T',title:'Direct overhead nadir view'}
        ].map(item=>(
          <button
            key={item.id}
            title={item.title}
            onClick={()=>useLab.getState().set({camera:item.id,cameraRevision:useLab.getState().cameraRevision+1,followRocket:item.id!=='Mission'})}
            className={camera===item.id?'selected':''}
          >
            {item.label} <span className="cam-key">[{item.hotkey}]</span>
          </button>
        ))}
      </div>
    </div>
  </section>;
}

function framePhase(time:number,telemetry:Telemetry|null){
  if(!telemetry)return 'AWAITING FLIGHT';
  const f=sample(telemetry.frames,time),agl=f.position[2]-telemetry.rocket_length/2;
  if(f.phase==='takeoff'&&f.hold_down)return f.throttle>.02?'IGNITION · HOLD-DOWNS ENGAGED':'ON PAD · PRE-IGNITION';
  if(f.throttle<.02)return f.phase==='takeoff'&&agl<1.5?'ON PAD · PRE-IGNITION':'ENGINE OFF · COAST';
  return f.phase==='takeoff'?'ASCENT BURN':'LANDING BURN';
}

function SetupPanel(props:MissionControlProps&{selectedCps:Checkpoint[];targetX:number;targetY:number;setTargetX:(v:number)=>void;setTargetY:(v:number)=>void;retargetReady:boolean;lastRetarget:Retarget|undefined;onJump:(t:number)=>void}){
  const {mission,method,level,seed,checkpoint,busy,online,story,compare}=props;
  const time=useInstrumentTime(),volume=useLab(s=>s.volume),telemetry=useLab(s=>s.telemetry),audioPerspective=useLab(s=>s.audioPerspective);
  return <aside className="setup-card">
    <div className="setup-head"><h3>Mission setup</h3><span className="chip">6-DOF</span></div>
    <div className="setup-scroll">
      <label className="field-label">MISSION PROFILE</label>
      <div className="mission-options">{(['landing','takeoff','combined'] as Mission[]).map(value=><button key={value} className={mission===value?'chosen':''} onClick={()=>props.onMission(value,method,level)}>{value==='landing'?<ArrowDown size={16}/>:value==='takeoff'?<ArrowUp size={16}/>:<RotateCcw size={16}/>}<span>{value==='landing'?'Landing':value==='takeoff'?'Takeoff':'Combined'}</span></button>)}</div>
      <label className="field-label">GUIDANCE</label>
      <div className="method-options"><button className={method==='classical'?'chosen':''} onClick={()=>props.onMission(mission,'classical',level)}><Gauge size={15}/>Classical</button><button className={method==='rl'?'chosen':''} onClick={()=>props.onMission(mission,'rl',level)}><Sparkles size={15}/>RL agent</button></div>
      <div className="field-heading"><label className="field-label">{method==='rl'?'CHECKPOINT LEVEL':'CONTROLLER LEVEL'}</label><span>0{level} / 04</span></div>
      <div className="levels">{(method==='rl'?rlLevels:levels).map((label,index)=><button key={label} className={level===index+1?'chosen':''} onClick={()=>props.onLevel(index+1)}><span className="level-number">0{index+1}</span><span>{label}</span>{level===index+1?<span className="level-check"><Check size={12}/></span>:<ChevronRight size={13}/>}</button>)}</div>
      {method==='rl'?<><label className="field-label">SAVED CHECKPOINT</label><select aria-label="Saved checkpoint" className="full-select" value={checkpoint} onChange={e=>props.onCheckpoint(e.target.value)}><option value="">Automatic measured checkpoint</option>{props.selectedCps.map(value=><option key={value.id} value={value.id}>{value.algorithm} · {compact(value.steps)} steps · {value.successes||0}/{value.evaluation_episodes} successes</option>)}</select><p className="subtle small">Automatic slots use each compatible checkpoint’s largest sample and Wilson lower bound. A saved checkpoint can still be experimental.</p></>:<p className="controller-note"><ShieldCheck size={14}/>{level===1?'Untuned altitude + attitude PID':level===2?'Tuned cascaded feedback':level===3?'Convex guidance + attitude tracking':'LQR + descent feedforward'}</p>}
      <FlightPlanEditor/>
      <RetargetCard targetX={props.targetX} targetY={props.targetY} setTargetX={props.setTargetX} setTargetY={props.setTargetY} time={time} ready={props.retargetReady} onRetarget={()=>props.onRetarget(time,[props.targetX,props.targetY])} lastRetarget={props.lastRetarget} mission={telemetry?.run.mission||mission} plan={telemetry?.run.flight_plan}/>
      <button className="btn primary full" disabled={busy} onClick={props.onRun}>{busy?<LoaderCircle size={16} className="spin"/>:<Play size={14} fill="currentColor"/>}Run flight<ArrowUpRight size={15}/></button>
      <details className="advanced"><summary>Seed, playback &amp; sound<ChevronDown size={13}/></summary><label>Fixed start seed<input aria-label="Start seed" type="number" min={0} max={2147483647} value={seed} onChange={e=>props.onSeed(Math.max(0,Math.trunc(+e.target.value)))}/></label><label>Listening perspective<select aria-label="Listening perspective" value={audioPerspective} onChange={e=>{useLab.getState().set({audioPerspective:e.target.value as 'Exterior'|'Onboard'});missionAudio.update();}}><option>Exterior</option><option>Onboard</option></select></label><label>Sound volume<input aria-label="Sound volume" type="range" min={0} max={1} step={.05} value={volume} onChange={e=>{useLab.getState().set({volume:+e.target.value});missionAudio.update();}}/></label><p className="subtle small">Synthesized audio follows the engine clock. Exterior listening adds distance delay and altitude attenuation; onboard mode retains structural sound. Plumes and audio are illustrative, not recordings or CFD.</p></details>
      <details className="comparison-settings"><summary>Compare flights<ChevronDown size={13}/></summary><div className="compare-row"><select aria-label="Comparison type" value={compare} onChange={e=>props.onCompare(e.target.value)}><option>Level 1 vs current</option><option>RL vs classical</option></select><button aria-label="Load comparison" disabled={busy||!online||!!telemetry?.run.training_mode} onClick={props.onGhost}><Layers size={16}/></button></div><button className="story-button" onClick={props.onStory} disabled={story}><Clapperboard size={15}/><span>{story?'Playing the learning journey':'Play the learning journey'}</span><Play size={12}/></button></details>
      <p className="setup-footer"><span className="status-dot on"/>SAME PHYSICS · DIFFERENT APPROACHES</p>
    </div>
  </aside>;
}

function RetargetCard({targetX,targetY,setTargetX,setTargetY,time,ready,onRetarget,lastRetarget,mission,plan}:{targetX:number;targetY:number;setTargetX:(v:number)=>void;setTargetY:(v:number)=>void;time:number;ready:boolean;onRetarget:()=>void;lastRetarget:Retarget|undefined;mission:Mission;plan?:{landing:[number,number]}|null}){
  const clamp=(value:number)=>Number.isFinite(value)?Math.max(-10000,Math.min(10000,value)):0;
  return <section className={`retarget-card ${ready?'ready':''}`}>
    <div className="retarget-head"><span><Crosshair size={15}/>IN-FLIGHT RETARGET</span><span className="chip">{formatTime(time)}</span></div>
    <p>Command a new landing site from the current playback time. Classical guidance diverts while holding a shallow descent; a learned policy receives the new goal in its observation. The branch is re-simulated from the same seed with the command applied at this time.</p>
    <div className="retarget-inputs">
      <label>X · east<span><NumberField label="Retarget X" value={targetX} min={-10000} max={10000} step={5} onCommit={setTargetX}/>m</span></label>
      <label>Y · north<span><NumberField label="Retarget Y" value={targetY} min={-10000} max={10000} step={5} onCommit={setTargetY}/>m</span></label>
    </div>
    <div className="retarget-presets"><button onClick={()=>setTargetX(clamp(targetX-20))}>−20 X</button><button onClick={()=>setTargetX(clamp(targetX+20))}>+20 X</button><button onClick={()=>setTargetY(clamp(targetY-20))}>−20 Y</button><button onClick={()=>setTargetY(clamp(targetY+20))}>+20 Y</button><button onClick={()=>{if(plan){setTargetX(plan.landing[0]);setTargetY(plan.landing[1]);}}} aria-label="Reset retarget to applied target">Reset</button></div>
    <button className="btn primary full" disabled={!ready} onClick={onRetarget}><Crosshair size={15}/>Retarget at T+{time.toFixed(1)} s</button>
    {mission==='takeoff'&&<p className="retarget-note">Takeoff has no landing target to move.</p>}
    {lastRetarget&&<p className="retarget-note good"><CircleCheck size={13}/>Last command at T+{lastRetarget.t.toFixed(1)} s → {lastRetarget.landing.map(v=>v.toFixed(0)).join(', ')} m</p>}
    {!ready&&mission!=='takeoff'&&<p className="retarget-note">Retargeting needs the local engine, an unfinished flight and at least 20 m above ground. Scrub to an earlier powered-descent point.</p>}
  </section>;
}

function ProfileChart({data,time,duration,currentAltitude,currentSpeed,mission,tolerance}:{data:{t:number;altitude:number;speed:number}[];time:number;duration:number;currentAltitude:number;currentSpeed:number;mission:Mission;tolerance:number}){
  return <section className="chart-card">
    <div className="chart-head"><div><h3>Flight profile</h3><p>Altitude above ground and total speed over mission time</p></div><div className="chart-legend"><span><i className="dot purple"/>Altitude <b>{currentAltitude.toFixed(0)} m</b></span><span><i className="dot coral"/>Speed <b>{currentSpeed.toFixed(1)} m/s</b></span></div></div>
    {data.length?<div className="chart-body"><ResponsiveContainer width="100%" height={260}><ComposedChart data={data} margin={{top:12,right:6,left:-12,bottom:0}}>
      <defs><linearGradient id="profileFill" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor="#7a5cf6" stopOpacity={.22}/><stop offset="100%" stopColor="#7a5cf6" stopOpacity={0}/></linearGradient><pattern id="profileHatch" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" x2="0" y1="0" y2="7" stroke="#c9bfff" strokeWidth="1" opacity=".5"/></pattern></defs>
      <CartesianGrid stroke="#ece9f5" vertical={false}/><XAxis dataKey="t" tick={{fill:'#8d879f',fontSize:11}} axisLine={false} tickLine={false} unit="s" minTickGap={28}/><YAxis yAxisId="alt" tick={{fill:'#8d879f',fontSize:11}} axisLine={false} tickLine={false} width={44}/><YAxis yAxisId="speed" orientation="right" tick={{fill:'#b3a7a5',fontSize:11}} axisLine={false} tickLine={false} width={38}/>
      <Tooltip contentStyle={{background:'#ffffff',border:'1px solid #e9e5f4',borderRadius:12,boxShadow:'0 12px 30px -12px rgba(35,26,70,.25)',fontSize:12}} labelFormatter={value=>`T+ ${Number(value).toFixed(1)} s`} formatter={(value,name)=>[`${Number(value).toFixed(1)} ${name==='Altitude'?'m':'m/s'}`,name]}/>
      <Area isAnimationActive={false} yAxisId="alt" type="monotone" dataKey="altitude" name="Altitude" stroke="#7a5cf6" strokeWidth={2.2} fill="url(#profileFill)"/>
      <Line isAnimationActive={false} yAxisId="speed" type="monotone" dataKey="speed" name="Speed" stroke="#ef7f89" strokeWidth={2} strokeDasharray="3 5" dot={false}/>
      <ReferenceLine x={data.reduce((closest,p)=>Math.abs(p.t-time)<Math.abs(closest.t-time)?p:closest,data[0]).t} yAxisId="alt" stroke="#b8aed3" strokeDasharray="3 4"/>
    </ComposedChart></ResponsiveContainer></div>:<div className="empty-chart"><Activity size={28}/><p>Run a flight to draw the profile.</p></div>}
    <div className="chart-foot"><span>{mission==='takeoff'?'Ascent criteria: reach separation altitude · vertical speed within ±8 m/s of target · tilt < 5° · offset ≤ 5 m':`Landing criteria: COM and contact speed < 2 m/s · tilt < 5° · offset ≤ ${tolerance} m`}</span><span>{mission==='takeoff'?'Ascent flight':'Powered descent'} · {formatTime(duration)}</span></div>
  </section>;
}

function EngineChart({data,time,throttle,minimum}:{data:{t:number;throttle:number;fuel:number}[];time:number;throttle:number;minimum:number}){
  return <section className="chart-card">
    <div className="chart-head"><div><h3>Engine performance</h3><p>Mean throttle in recorded time buckets</p></div><div className="chart-legend"><span><i className="dot purple"/>Throttle <b>{throttle.toFixed(0)}%</b></span><span><i className="dot line"/>Min throttle {minimum.toFixed(0)}%</span></div></div>
    {data.length?<div className="chart-body"><ResponsiveContainer width="100%" height={260}><BarChart data={data} margin={{top:12,right:6,left:-12,bottom:0}}>
      <CartesianGrid stroke="#ece9f5" vertical={false}/><XAxis dataKey="t" tick={{fill:'#8d879f',fontSize:11}} axisLine={false} tickLine={false} unit="s" minTickGap={20}/><YAxis domain={[0,100]} tick={{fill:'#8d879f',fontSize:11}} axisLine={false} tickLine={false} width={44} tickFormatter={value=>`${value}%`}/>
      <Tooltip cursor={{fill:'#f5f2ff'}} contentStyle={{background:'#ffffff',border:'1px solid #e9e5f4',borderRadius:12,boxShadow:'0 12px 30px -12px rgba(35,26,70,.25)',fontSize:12}} labelFormatter={value=>`T+ ${Number(value).toFixed(1)} s`} formatter={(value,name)=>[name==='throttle'?`${Number(value).toFixed(1)}%`:`${Number(value).toFixed(2)} t`,name==='throttle'?'Throttle':'Propellant']}/>
      <ReferenceLine y={minimum} stroke="#c7bdd4" strokeDasharray="4 5" label={{value:`MIN ${minimum.toFixed(0)}%`,fill:'#9a90ab',fontSize:10,position:'insideTopRight'}}/>
      <Bar isAnimationActive={false} dataKey="throttle" radius={[6,6,2,2]} maxBarSize={30}>{data.map((value,index)=><Cell key={`${value.t}-${index}`} fill={value.throttle>minimum?'#7a5cf6':'#cbc3e6'} opacity={value.t<=time?1:.35}/>)}</Bar>
    </BarChart></ResponsiveContainer></div>:<div className="empty-chart"><Flame size={28}/><p>Run a flight to record engine telemetry.</p></div>}
    <div className="chart-foot"><span>Engine can switch fully off; {minimum.toFixed(0)}% is the steady on-throttle floor. Ignition and cutoff ramp through it.</span><span>Gimbal ±8°</span></div>
  </section>;
}

function MiniCharts({data,time}:{data:{t:number;altitude:number;speed:number;throttle:number;fuel:number}[];time:number}){
  const series=[{key:'altitude',label:'Altitude',unit:'m',color:'#7a5cf6'},{key:'speed',label:'Speed',unit:'m/s',color:'#ef7f89'},{key:'fuel',label:'Propellant',unit:'t',color:'#2aa48a'},{key:'throttle',label:'Throttle',unit:'%',color:'#e9a23b'}] as const;
  return <div className="mini-grid">{series.map(item=><div className="mini-card" key={item.key}><div className="mini-head"><span>{item.label}</span><b>{data.length?Number(data.at(-1)![item.key]).toFixed(item.key==='speed'?1:0):'—'} <small>{item.unit}</small></b></div><ResponsiveContainer width="100%" height={92}><ComposedChart data={data} margin={{top:6,right:0,left:-40,bottom:0}}><XAxis dataKey="t" hide/><YAxis hide domain={['auto','auto']}/><Tooltip contentStyle={{background:'#fff',border:'1px solid #e9e5f4',borderRadius:10,fontSize:11}} labelFormatter={value=>`T+ ${Number(value).toFixed(1)} s`} formatter={value=>[Number(value).toFixed(2),item.label]}/><Line type="monotone" dataKey={item.key} stroke={item.color} strokeWidth={1.8} dot={false}/><ReferenceLine x={time} stroke="#d4cce8" strokeDasharray="2 3"/></ComposedChart></ResponsiveContainer></div>)}</div>;
}

function InstrumentRow({metrics,frame,fuelPercent,initialFuel}:{metrics:ReturnType<typeof frameMetrics>|null;frame:Telemetry['frames'][number]|null;fuelPercent:number;initialFuel:number}){
  const items=[
    {label:'HORIZONTAL SPEED',value:metrics?.horizontalSpeed||0,unit:'m/s',extra:'ground-relative lateral velocity',icon:Wind,bar:undefined},
    {label:'ATTITUDE',value:metrics?.tilt||0,unit:'°',extra:'angle from the local vertical',icon:Compass,bar:undefined},
    {label:'PROPELLANT',value:fuelPercent,unit:'%',extra:`${(frame?.fuel_mass||0)/1000>0?((frame?.fuel_mass||0)/1000).toFixed(2):'0.00'} t of ${(initialFuel/1000).toFixed(1)} t`,icon:Fuel,bar:fuelPercent/100},
    {label:'ENGINE THROTTLE',value:(frame?.throttle||0)*100,unit:'%',extra:`gimbal ${((frame?.gimbal[0]||0)*180/Math.PI).toFixed(1)}° / ${((frame?.gimbal[1]||0)*180/Math.PI).toFixed(1)}°`,icon:Zap,bar:frame?.throttle||0},
  ];
  return <div className="instruments">{items.map(item=><article className="instrument panel" key={item.label}><div className="instrument-label"><item.icon size={14}/>{item.label}</div><div className="instrument-value">{fixed(item.value,2)}<span>{item.unit}</span>{item.bar!==undefined&&<div className="meter"><i style={{width:`${Math.max(0,Math.min(100,item.bar*100))}%`}}/></div>}</div><small>{item.extra}</small></article>)}</div>;
}

function SitePanel({plan,transfer,retargets,onEdit}:{plan?:Telemetry['run']['flight_plan']|null;transfer:number;retargets:Retarget[];onEdit:()=>void}){
  return <section className="site-card">
    <div className="card-title"><div><h3>Mission sites</h3><p>Prepared pads follow the applied plan</p></div><button className="btn subtle small-btn" onClick={onEdit}>Edit plan <ArrowRight size={13}/></button></div>
    <div className="site-visual">
      <svg viewBox="0 0 520 96" role="img" aria-label="Plan view from launch to landing site">
        <defs><linearGradient id="routeGrad" x1="0" x2="1"><stop offset="0" stopColor="#7a5cf6"/><stop offset="1" stopColor="#ef9a7f"/></linearGradient></defs>
        <path d="M40 70 C 170 20, 330 20, 470 64" fill="none" stroke="#e6e2f1" strokeWidth="10" strokeLinecap="round"/>
        <path d="M40 70 C 170 20, 330 20, 470 64" fill="none" stroke="url(#routeGrad)" strokeWidth="2.4" strokeDasharray="5 6" strokeLinecap="round"/>
        <circle cx="40" cy="70" r="11" fill="#efeaff" stroke="#7a5cf6" strokeWidth="2"/><circle cx="40" cy="70" r="3.4" fill="#7a5cf6"/>
        <circle cx="470" cy="64" r="11" fill="#fff0e8" stroke="#ef7f6f" strokeWidth="2"/><circle cx="470" cy="64" r="3.4" fill="#ef7f6f"/>
        <text x="40" y="92" textAnchor="middle" fontSize="10" fill="#8d879f">TAKEOFF</text><text x="470" y="88" textAnchor="middle" fontSize="10" fill="#8d879f">LANDING</text>
        {retargets.length>0&&<text x="470" y="30" textAnchor="middle" fontSize="10" fill="#ef7f6f">TARGET MOVED ×{retargets.length}</text>}
      </svg>
    </div>
    <div className="site-pair">
      <div className="site-tile"><span className="site-icon launch"><Rocket size={15}/></span><div><span>TAKEOFF SITE</span><strong>{plan?plan.launch.map(v=>v.toFixed(0)).join(', '):'—'}<small>m</small></strong><small>X east · Y north (Pad 01)</small></div></div>
      <div className="site-tile"><span className="site-icon landing"><Target size={15}/></span><div><span>LANDING SITE</span><strong>{plan?plan.landing.map(v=>v.toFixed(0)).join(', '):'—'}<small>m</small></strong><small>{retargets.length?`Retargeted ${retargets.length}×`:'Selected Pad 01'}</small></div></div>
    </div>
    <div className="site-facts"><span><ArrowRight size={13}/>{(transfer/1000).toFixed(2)} km surface transfer {transfer>=1000?'(> 1 km nominal)':'(< 1 km error)'}</span><span><ArrowUp size={13}/>{plan?`${plan.separation_altitude} m separation`:'—'}</span>{retargets.at(-1)&&<span className="retarget-pill"><Crosshair size={13}/>Target moved at T+{retargets.at(-1)!.t.toFixed(1)} s</span>}</div>
  </section>;
}

function FlightLog({events,onJump,onAll}:{events:{t:number;label:string;detail:string;icon:'engine'|'target'|'stage'|'complete'}[];onJump:(t:number)=>void;onAll?:()=>void}){
  return <section className="log-card">
    <div className="card-title"><div><h3>Flight log</h3><p>Recorded events, not a scripted sequence</p></div>{onAll&&<button className="btn subtle small-btn" onClick={onAll}>See all <ArrowRight size={13}/></button>}</div>
    <div className="log-list">{events.length?events.map(event=><button className="log-row" key={`${event.label}-${event.t}`} onClick={()=>onJump(event.t)}><span className={`log-icon ${event.icon}`}>{event.icon==='engine'?<Flame size={15}/>:event.icon==='target'?<Crosshair size={15}/>:event.icon==='stage'?<Layers size={15}/>:<CircleCheck size={15}/>}</span><span className="log-copy"><strong>{event.label}</strong><small>{event.detail}</small></span><span className="log-time">T+{event.t.toFixed(1)} s</span><Play size={13} className="log-play"/></button>):<p className="empty-message">Run a flight to record its events.</p>}</div>
  </section>;
}

function OutcomeCard({telemetry}:{telemetry:Telemetry}){
  const success=telemetry.run.outcome==='success';
  return <div role="status" className={`outcome flight-outcome ${success?'success':'failure'}`}><span>{success?<Check size={18}/>:<Activity size={18}/>}</span><div><strong>{success?(telemetry.run.mission==='takeoff'?'Separation target reached':'Touchdown confirmed'):telemetry.run.failure_reason?.replaceAll('_',' ')}</strong><small>{telemetry.run.touchdown_speed.toFixed(2)} m/s · {telemetry.run.tilt.toFixed(2)}° tilt · {telemetry.run.pad_distance.toFixed(2)} m offset</small></div></div>;
}
