import {useCallback,useEffect,useState} from 'react';
import {Activity,ArrowUpRight,BookOpen,ChartNoAxesCombined,Check,Cpu,FlaskConical,Layers,Play,Radio,Rocket,Search,Settings2,ShieldCheck,Square,Terminal,X} from 'lucide-react';
import {ResponsiveContainer,AreaChart,Area,XAxis,YAxis,Tooltip,CartesianGrid,BarChart,Bar,Cell} from 'recharts';
import {useLab} from './store';
import {useShallow} from 'zustand/react/shallow';
import {useVisiblePoll} from './useVisiblePoll';
import CurriculumProbes from './CurriculumProbes';
import FullTaskChecks from './FullTaskChecks';
import FlightPlanEditor from './FlightPlanEditor';
import CampaignPanel from './CampaignPanel';
import NativeMonitor from './NativeMonitor';
import MissionControl from './MissionControl';
import {largestClassicalSamples,resultSampleId} from './resultSamples';
import {compact,parseTelemetry} from './telemetry';
import type {Checkpoint,Job,Mission,Method,Result,Run,SystemInfo,Telemetry} from './types';

const pageSuggestions=[
  {label:'3D Aerospace Flight Simulator',hint:'Real-time 6-DOF WebGL rocket physics and camera controls',page:'Flight lab'},
  {label:'Isaac Sim real-time flight',hint:'PhysX 6-DOF simulation, guidance and RTX views',page:'Isaac Sim'},
  {label:'Training observatory',hint:'PPO and SAC jobs, checkpoints and curves',page:'Training'},
  {label:'Evaluation results',hint:'Fixed-seed evidence and failure modes',page:'Results'},
  {label:'Field notes',hint:'Physics, guidance and hardware reference',page:'Field notes'}
];
const formatTime=(t:number)=>`${Math.floor(t/60).toString().padStart(2,'0')}:${(t%60).toFixed(1).padStart(4,'0')}`;
async function api<T>(path:string,body?:unknown):Promise<T>{const r=await fetch(`/api${path}`,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:undefined);if(!r.ok){const e=await r.json().catch(()=>({detail:`HTTP ${r.status}`}));throw new Error(typeof e.detail==='string'?e.detail:Array.isArray(e.detail)?e.detail.map((x:{msg:string})=>x.msg).join('; '):'Request failed');}return r.json();}

export default function App({initialPage='Flight lab'}:{initialPage?:string}){
  const [page,setPage]=useState(initialPage);
  const [online,setOnline]=useState(false),[error,setError]=useState('');
  const [runs,setRuns]=useState<Run[]>([]),[jobs,setJobs]=useState<Job[]>([]),[checkpoints,setCheckpoints]=useState<Checkpoint[]>([]),[results,setResults]=useState<Result[]>([]),[system,setSystem]=useState<SystemInfo|null>(null);
  const [query,setQuery]=useState('');
  const [mission,setMission]=useState<Mission>('landing');
  const [method,setMethod]=useState<Method>('classical');
  const [level,setLevel]=useState(4);
  const [seed,setSeed]=useState(42);
  const [checkpoint,setCheckpoint]=useState('');
  const [story,setStory]=useState(false);
  const [compare,setCompare]=useState('RL vs classical');
  const [busy,setBusy]=useState(false);

  const lab=useLab(useShallow(state=>({recording:state.recording,telemetry:state.telemetry,playing:state.playing})));

  const refresh=useCallback(async()=>{
    try{
      const view=page==='Training'?'training':page==='Results'?'results':'flight';
      const snapshot=await api<{runs?:Run[];jobs?:Job[];checkpoints?:Checkpoint[];results?:Result[]}>(`/dashboard?view=${view}`);
      if(snapshot.runs)setRuns(snapshot.runs);
      if(snapshot.jobs)setJobs(snapshot.jobs);
      if(snapshot.checkpoints)setCheckpoints(snapshot.checkpoints);
      if(snapshot.results)setResults(snapshot.results);
      setOnline(true);
    }catch{
      setOnline(false);
    }
  },[page]);

  useVisiblePoll(refresh,page==='Training'?10000:60000,page!=='Field notes');

  useEffect(()=>{
    let active=true;
    async function boot(){
      try{
        await api('/health');
        if(!active)return;
        setOnline(true);
        const s=await api<SystemInfo>('/system');
        if(active)setSystem(s);
      }catch{
        if(active)setOnline(false);
      }finally{
        if(active)setBusy(false);
      }
    }
    void boot();
    return()=>{active=false;};
  },[]);

  const loadRun=useCallback(async(m:Mission,me:Method,l:number,cp?:string,s=42,options?:{seek?:number})=>{
    setBusy(true);setError('');
    try{
      let t:Telemetry;
      if(!online){
        const response=await fetch('/demo.json');
        t=await response.json() as Telemetry;
      }else{
        const plan=useLab.getState().flightPlan;
        const body={mission:m,method:me,level:l,seed:s,checkpoint_id:cp||null,flight_plan:plan};
        t=await api<Telemetry>('/simulate',body);
      }
      const playback=useLab.getState();
      playback.load(parseTelemetry(t));
      playback.set({ghost:null,...(options?.seek!==undefined?{time:options.seek,playing:true}:{})});
      setCheckpoint(me==='rl'?(t.run.checkpoint_id||''):'');
    }catch(e){
      setError((e as Error).message);
      const shown=useLab.getState().telemetry?.run;
      if(shown){setMission(shown.mission);setMethod(shown.method);setLevel(shown.level);}
    }finally{
      setBusy(false);
    }
  },[online]);

  useEffect(()=>{
    if(page!=='Flight lab'||useLab.getState().telemetry)return;
    let active=true;
    if(online){
      void loadRun(mission,method,level,checkpoint,seed);
    }else{
      setBusy(true);
      void fetch('/demo.json').then(response=>response.json()).then(value=>{
        if(active){
          useLab.getState().load(parseTelemetry(value));
          useLab.getState().set({playing:false});
        }
      }).catch(problem=>{
        if(active)setError((problem as Error).message);
      }).finally(()=>{
        if(active)setBusy(false);
      });
    }
    return()=>{active=false;};
  },[page,online,loadRun,mission,method,level,checkpoint,seed]);

  useEffect(()=>{
    if(!story||lab.playing||!lab.telemetry)return;
    const next=lab.telemetry.run.level+1;
    if(next>4){setStory(false);return;}
    const timer=setTimeout(()=>{
      setLevel(next);
      void loadRun(mission,method,next,'',seed);
    },1800);
    return()=>clearTimeout(timer);
  },[story,lab.playing,lab.telemetry,loadRun,mission,method,seed]);

  useEffect(()=>{
    const key=(e:KeyboardEvent)=>{
      if((e.target as HTMLElement).matches('input,select,textarea'))return;
      if(e.code==='Space'){
        e.preventDefault();
        const s=useLab.getState();
        s.set({playing:!s.playing});
      }
      if(e.key==='Escape')useLab.getState().set({recording:false});
    };
    window.addEventListener('keydown',key);
    return()=>window.removeEventListener('keydown',key);
  },[]);

  useEffect(()=>{
    if(page!=='Flight lab'){
      useLab.getState().set({playing:false});
    }
  },[page]);

  const choice=(m:Mission,me:Method,l:number)=>{setMission(m);setMethod(me);setLevel(l);setCheckpoint('');setStory(false);};

  const ghostRun=async()=>{
    setBusy(true);setError('');
    try{
      let t:Telemetry;
      if(!online){
        const demos=await fetch('/demo-runs.json').then(r=>r.json()) as Telemetry[];
        t=demos[0];
      }else{
        const compareMethod=compare==='RL vs classical'?(method==='rl'?'classical':'rl'):method;
        const compareLevel=compare==='Level 1 vs current'?1:level;
        t=await api<Telemetry>('/simulate',{mission,method:compareMethod,level:compareLevel,seed,checkpoint_id:null,flight_plan:useLab.getState().telemetry?.run.flight_plan||useLab.getState().flightPlan});
      }
      useLab.getState().set({ghost:parseTelemetry(t),time:0,playing:true});
    }catch(e){
      setError((e as Error).message);
    }finally{
      setBusy(false);
    }
  };

  const loadRecordedRun=async(url:string)=>{
    setBusy(true);setError('');
    try{
      const response=await fetch(url);
      if(!response.ok)throw new Error('Recorded development flight is unavailable');
      const telemetry=parseTelemetry(await response.json());
      setStory(false);setPage('Flight lab');setMission(telemetry.run.mission);setMethod(telemetry.run.method);setLevel(telemetry.run.level);setSeed(telemetry.run.seed);setCheckpoint(telemetry.run.checkpoint_id||'');
      if(telemetry.run.flight_plan)useLab.getState().set({flightPlan:telemetry.run.flight_plan});
      useLab.getState().load(telemetry);
      useLab.getState().set({ghost:null});
    }catch(e){setError((e as Error).message);}finally{setBusy(false);}
  };

  const startStory=()=>{setStory(true);setLevel(1);void loadRun(mission,method,1,'',seed);};

  const exportData=()=>{
    if(!lab.telemetry)return;
    const url=URL.createObjectURL(new Blob([JSON.stringify(lab.telemetry,null,2)],{type:'application/json'}));
    const a=document.createElement('a');
    a.href=url;
    a.download=`${lab.telemetry.run.id}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const commandRetarget=async(t:number,landing:[number,number])=>{
    setBusy(true);setError('');
    const applied=useLab.getState().telemetry?.run;
    try{
      if(!online)throw new Error('Start the local engine to command an in-flight retarget.');
      if(!applied)throw new Error('Run a flight before commanding a new landing site.');
      const plan=applied.initial_flight_plan||applied.flight_plan||useLab.getState().flightPlan;
      const retargets=(applied.retargets||[]).filter(event=>event.t<t-1e-6).map(event=>({time:event.t,landing:event.landing}));
      retargets.push({time:t,landing});
      const body={mission:applied.mission,method:applied.method,level:applied.level,seed:applied.seed,checkpoint_id:applied.checkpoint_id||null,flight_plan:plan,retargets};
      const result=parseTelemetry(await api<Telemetry>('/simulate',body));
      setMission(applied.mission);setMethod(applied.method);setLevel(applied.level);setSeed(applied.seed);setCheckpoint(applied.checkpoint_id||'');
      const playback=useLab.getState();
      playback.load(result);
      playback.set({time:t,playing:true,ghost:null,flightPlan:{...plan,landing}});
    }catch(e){setError((e as Error).message);}finally{setBusy(false);}
  };

  return <div className={`shell ${lab.recording?'recording':''}`}>
    <header className="topnav">
      <a className="brand" href="#" onClick={e=>{e.preventDefault();setPage('Flight lab');}}>
        <span className="brand-mark"><Rocket size={20}/></span>
        <span className="brand-copy">ISS Orbital Systems<small>Omniverse Rocket Simulator</small></span>
      </a>
      <nav className="main-nav" aria-label="Primary navigation">
        {[
          {id:'Flight lab',label:'3D Flight Lab'},
          {id:'Isaac Sim',label:'Isaac Sim RTX'},
          {id:'Training',label:'Training'},
          {id:'Results',label:'Results'},
          {id:'Field notes',label:'Field notes'}
        ].map(item=>(
          <button key={item.id} className={page===item.id?'active':''} onClick={()=>setPage(item.id)}>
            {item.label}
          </button>
        ))}
      </nav>
      <div className="nav-tools">
        <div className={`nav-search ${query?'open':''}`}>
          <Search size={15}/>
          <input aria-label="Search mission controls" placeholder="Search missions, training, results…" value={query} onChange={e=>setQuery(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'&&query){const match=pageSuggestions.find(value=>value.label.toLowerCase().includes(query.toLowerCase()));if(match){setPage(match.page);setQuery('');}}if(e.key==='Escape')setQuery('');}}/>
          {query&&<div className="search-results">{pageSuggestions.filter(value=>value.label.toLowerCase().includes(query.toLowerCase())||value.hint.toLowerCase().includes(query.toLowerCase())).map(value=><button key={value.label} onClick={()=>{setPage(value.page);setQuery('');}}><span><strong>{value.label}</strong><small>{value.hint}</small></span><ArrowUpRight size={13}/></button>)}</div>}
        </div>
        <span className={`engine-pill ${online?'online':''}`} title={online?'Dashboard backend reachable; native engine connection is active':'Dashboard backend offline'}><span className="status-dot on"/>{online?'Backend online':'Backend offline'}</span>
        <button className="icon-button" aria-label="Read the flight manual" title="Flight manual" onClick={()=>setPage('Field notes')}><BookOpen size={17}/></button>
        <span className="avatar" aria-hidden="true">IA</span>
      </div>
    </header>
    <main className="shell-main">
      {error&&<div role="alert" className="error-banner"><span>{error}</span><button aria-label="Dismiss error" onClick={()=>setError('')}><X size={16}/></button></div>}
      {page==='Flight lab'&&<MissionControl mission={mission} method={method} level={level} seed={seed} checkpoint={checkpoint} checkpoints={checkpoints} busy={busy} online={online} story={story} compare={compare} onMission={choice} onLevel={value=>choice(mission,method,value)} onCheckpoint={setCheckpoint} onSeed={setSeed} onRun={()=>{setStory(false);void loadRun(mission,method,level,checkpoint,seed);}} onRetarget={commandRetarget} onGhost={()=>void ghostRun()} onStory={startStory} onCompare={setCompare} onExport={exportData} onError={setError} onOpenNotes={()=>setPage('Field notes')}/>}
      {page==='Isaac Sim'&&<NativeMonitor/>}
      {page!=='Flight lab'&&page!=='Isaac Sim'&&<div className="content-page">
        <div className="page-head">
          <div><div className="breadcrumb"><span className="live-dot"/>{page==='Training'?'HEADLESS REINFORCEMENT LEARNING':page==='Results'?'MEASURED PERFORMANCE':'ENGINEERING REFERENCE'}</div><h1>{page==='Training'?'Watch a policy learn to fly.':page==='Results'?'Every flight leaves evidence.':'Understand what makes it fly.'}</h1><p className="page-sub">{page==='Training'?'Real PPO and SAC jobs run locally. Curves and checkpoints are measured on fixed evaluation seeds.':page==='Results'?'Failure modes, confidence intervals and fixed-seed evaluations from the recorded evidence register.':'The physics, controllers, hardware and evidence model behind every flight.'}</p></div>
          <button className="btn subtle" onClick={()=>setPage('Flight lab')}><Rocket size={15}/>Open 3D Flight Lab<ArrowUpRight size={14}/></button>
        </div>
        {page==='Training'&&<TrainingView jobs={jobs} checkpoints={checkpoints} online={online} onRefresh={refresh} onError={setError} onWatchReplay={url=>void loadRecordedRun(url)} onWatch={async(c)=>{setPage('Flight lab');setMethod('rl');setMission(c.mission as Mission);setCheckpoint(c.id);await loadRun(c.mission as Mission,'rl',4,c.id,42);}}/>}
        {page==='Results'&&<ResultsView results={results} runs={runs} currentConfigHash={lab.telemetry?.config_hash||system?.config_hash} currentDynamicsHash={system?.dynamics_hash} currentMission={lab.telemetry?.run.mission}/>}
        {page==='Field notes'&&<NotesView system={system}/>}
        <footer className="page-footer"><span><FlaskConical size={13}/>Educational flight research · approximate vehicle parameters</span><span>z-up physics · quaternion attitude · SI units <b>/</b> v1.1</span></footer>
      </div>}
    </main>
    {lab.recording&&<button className="exit-recording" onClick={()=>useLab.getState().set({recording:false})}><X size={14}/>Exit recording view · Esc</button>}
  </div>;
}


function TrainingView({jobs,checkpoints,online,onRefresh,onError,onWatch,onWatchReplay}:{jobs:Job[];checkpoints:Checkpoint[];online:boolean;onRefresh:()=>Promise<void>;onError:(s:string)=>void;onWatch:(c:Checkpoint)=>void;onWatchReplay:(url:string)=>void}){
 const [mission,setMission]=useState('landing'),[algorithm,setAlgorithm]=useState('PPO'),[steps,setSteps]=useState(100000),[device,setDevice]=useState('auto'),[busy,setBusy]=useState(false),[selectedJob,setSelectedJob]=useState('');
 const summary=jobs.find(j=>j.id===selectedJob)||jobs[0];const [detail,setDetail]=useState<Job|null>(null);
 const jobId=summary?.id;
 const refreshDetail=useCallback(async()=>{if(jobId)try{setDetail(await api<Job>(`/training/${jobId}`));}catch{/* connection status is reported by the parent */}},[jobId]);
 useVisiblePoll(refreshDetail,10000,!!jobId);
 const job=detail?.id===jobId?detail:summary;const runningJob=jobs.find(j=>['running','starting','waiting_for_memory'].includes(j.status)&&Date.now()/1000-j.updated_at<120);const active=!!runningJob;
 const progress=job?Math.max(0,Math.min(100,(job.steps-(job.initial_steps??0))/Math.max(1,job.total_steps-(job.initial_steps??0))*100)):0;
 const jobConfig=job?.config||checkpoints.find(value=>value.job_id===job?.id)?.config;
 const goalSettings=jobConfig?.training as {takeoff_goal_curriculum?:boolean;takeoff_curriculum_altitude?:number;takeoff_curriculum_velocity?:number}|undefined;
 const missionSettings=jobConfig?.mission as {takeoff_altitude?:number;takeoff_velocity?:number}|undefined;
 const practiceGoal=job?.mission==='takeoff'&&goalSettings?.takeoff_goal_curriculum&&missionSettings?.takeoff_altitude&&missionSettings?.takeoff_velocity?{
  altitude:(goalSettings.takeoff_curriculum_altitude??5)+(job.difficulty??0)*(missionSettings.takeoff_altitude-(goalSettings.takeoff_curriculum_altitude??5)),
  velocity:(goalSettings.takeoff_curriculum_velocity??3)+(job.difficulty??0)*(missionSettings.takeoff_velocity-(goalSettings.takeoff_curriculum_velocity??3)),
 }:null;
 const launch=async()=>{setBusy(true);try{await api('/training',{mission,algorithm,steps,seed:42,device,flight_plan:useLab.getState().flightPlan});await onRefresh();}catch(e){onError((e as Error).message);}finally{setBusy(false);}};
 const stop=async()=>{if(!runningJob)return;try{await api(`/training/${runningJob.id}/stop`,{});await onRefresh();}catch(e){onError((e as Error).message);}};
 return <><CampaignPanel online={online} onError={onError}/><div className="training-layout"><section className="panel training-main"><div className="panel-title"><span><Activity size={15}/>TRAINING OBSERVATORY</span><span className={`job-status ${job?.status==='running'?'running':''}`}><span className="status-dot on"/>{job?.status||'NO ACTIVE JOB'}</span></div>
 <div className="training-summary"><div><span className="eyebrow">{job?.mission?.toUpperCase()||'LANDING'} / {job?.algorithm||'PPO'} POLICY</span><h2>{job?`${compact(job.steps)} environment steps`:'Your first policy starts here.'}</h2><p>Physical state in. Throttle and gimbal out. No expert actions.</p>{job&&<p className="subtle small">{job.id}{(job.initial_steps??0)>0&&` · ${(job.initial_steps||0).toLocaleString()} inherited steps · progress shows this run's additional budget`}</p>}</div><div className="training-device"><Cpu size={24}/><span>{job?.device?.toUpperCase()||'LOCAL'}<small>POLICY OPTIMIZER</small></span></div></div>
 <div className="training-progress"><i style={{width:`${progress}%`}}/></div>
 {practiceGoal&&<p className="qualification"><Rocket size={15}/>Practice goal at this stage: {practiceGoal.altitude.toFixed(1)} m altitude, {practiceGoal.velocity.toFixed(1)} m/s ascent. Full-task evaluation still requires {missionSettings?.takeoff_altitude} m and {missionSettings?.takeoff_velocity} m/s.</p>}
 <div className="training-stats"><div><span>TARGET</span><strong>{compact(job?.total_steps||steps)}</strong></div><div><span>THROUGHPUT</span><strong>{Math.round(job?.steps_per_second||0).toLocaleString()}<small>steps/s</small></strong></div><div><span>EPISODES</span><strong>{(job?.episode_count||0).toLocaleString()}</strong></div><div><span>CURRICULUM</span><strong>{((job?.difficulty??0)*100).toFixed(0)}<small>/ 100</small></strong></div><div><span>ELAPSED</span><strong>{formatTime(job?.elapsed_seconds||0)}</strong></div></div>
 <p className="training-window">Current-stage rolling successes: <strong>{job?.recent_successes??0} / {job?.recent_episodes??0}</strong>. Full-task results are evaluated separately below.</p><div className="learning-chart"><div className="chart-heading"><h3>Held-out evaluation reward</h3><span><i/>FULL START DISTRIBUTION</span></div>{job?.curve?.length?<ResponsiveContainer width="100%" height={255}><AreaChart data={job.curve} margin={{left:0,right:25,top:15,bottom:10}}><defs><linearGradient id="learning" x1="0" y1="0" x2="0" y2="1"><stop stopColor="#7a5cf6" stopOpacity={.22}/><stop offset="100%" stopColor="#7a5cf6" stopOpacity={0}/></linearGradient></defs><CartesianGrid stroke="#ece9f5" strokeDasharray="2 5"/><XAxis dataKey="steps" tickFormatter={compact} tick={{fill:'#8d879f',fontSize:11}} axisLine={false} tickLine={false}/><YAxis tick={{fill:'#8d879f',fontSize:11}} axisLine={false} tickLine={false}/><Tooltip contentStyle={{background:'#ffffff',border:'1px solid #e9e5f4',borderRadius:12,boxShadow:'0 12px 30px -12px rgba(35,26,70,.22)',fontSize:12}}/><Area dataKey="reward" stroke="#7a5cf6" fill="url(#learning)" strokeWidth={2} isAnimationActive={false}/></AreaChart></ResponsiveContainer>:<div className="empty-chart"><ChartNoAxesCombined size={32}/><h3>No evaluation points yet</h3><p>A real learning curve appears after the first saved checkpoint.</p></div>}</div>
 <div className="chart-heading second"><h3>Successes on fixed evaluation seeds</h3><span>COUNT / SAMPLE SIZE</span></div><div className="checkpoint-strip">{job?.curve?.map(p=><div key={p.steps}><span>{compact(p.steps)} steps</span><strong>{p.successes}<small> / {p.episodes}</small></strong><div className="tiny-bar"><i style={{width:`${p.success_rate*100}%`}}/></div></div>)}</div>
 {job?.error&&<pre className="error-log">{job.error}</pre>}<p className="qualification"><ShieldCheck size={14}/>Checkpoint samples are pilot evaluations. A full qualification requires 10,000 fixed seeds per checkpoint and robustness tests.</p>
 </section><aside className="panel train-config"><div className="panel-title"><span><Settings2 size={15}/>TRAINING CONFIGURATION</span></div><div className="setup-body"><label className="field-label">MISSION</label><select className="full-select" aria-label="Training mission" value={mission} onChange={e=>setMission(e.target.value)}><option value="landing">Landing policy</option><option value="takeoff">Takeoff policy</option><option value="combined">Combined launch & return policy</option></select><label className="field-label">ALGORITHM</label><div className="method-options">{['PPO','SAC'].map(a=><button key={a} className={a===algorithm?'chosen':''} onClick={()=>setAlgorithm(a)}>{a}</button>)}</div><p className="subtle small">{algorithm==='PPO'?'Clipped on-policy updates. Small state networks usually train efficiently on CPU.':'Off-policy learning with entropy regularization and twin Q networks. CUDA is available for updates.'}</p><label className="field-label">ENVIRONMENT STEPS</label><select aria-label="Training steps" className="full-select" value={steps} onChange={e=>setSteps(+e.target.value)}>{[10000,100000,500000,1000000,5000000,10000000,25000000,50000000,100000000].map(n=><option key={n} value={n}>{n.toLocaleString()} steps</option>)}</select><FlightPlanEditor mode="training"/><label className="field-label">COMPUTE DEVICE</label><select aria-label="Compute device" className="full-select" value={device} onChange={e=>setDevice(e.target.value)}><option value="auto">Automatic · CPU PPO / CUDA SAC</option><option value="cpu">CPU</option><option value="cuda">NVIDIA CUDA</option></select><div className="training-facts"><span><Check size={13}/>4 vectorized environments</span><span><Check size={13}/>Fixed seed 42</span><span><Check size={13}/>Adaptive difficulty curriculum</span><span><Check size={13}/>Seeded mid-flight landing retargets</span><span><Check size={13}/>Model + normalization snapshots</span><span><Check size={13}/>TensorBoard logs saved locally</span></div><button className="primary full" disabled={!online||busy||active} onClick={()=>void launch()}><Play size={14} fill="currentColor"/>{active?'Training in progress':'Start real training'}</button>{active&&<button className="quiet full stop" onClick={()=>void stop()}><Square size={12}/>Stop & save checkpoint</button>}<p className="subtle small">Jobs continue in the backend when you switch tabs. Closing this page does not request a stop.</p><div className="divider"/><label className="field-label">JOB HISTORY</label><select aria-label="Training job history" className="full-select" value={job?.id||''} onChange={e=>setSelectedJob(e.target.value)}>{jobs.map(j=><option key={j.id} value={j.id}>{j.mission} · {j.algorithm} · {compact(j.steps)} · {j.status}</option>)}</select></div></aside></div>
 <details className="archive-details panel"><summary>Archived experiments & previous qualification batches</summary><p className="qualification">Historical measurements use earlier dynamics and mission settings. They do not qualify the current controller, custom targets, or newly trained policies.</p><FullTaskChecks onWatch={onWatchReplay}/><CurriculumProbes onWatch={onWatchReplay}/></details><section className="panel checkpoint-table"><div className="panel-title"><span><Layers size={15}/>CHECKPOINT LIBRARY</span><span className="micro">{checkpoints.length} SAVED POLICIES</span></div><div className="table-scroll"><table><thead><tr><th>MISSION / ALGORITHM</th><th>STEPS</th><th>EVALUATION</th><th>MEAN REWARD</th><th>QUALIFICATION</th><th/></tr></thead><tbody>{[...checkpoints].sort((a,b)=>Date.parse(b.created_at||'')-Date.parse(a.created_at||'')||b.steps-a.steps).slice(0,40).map(c=><tr key={c.id}><td><strong>{c.mission}</strong><span className="table-muted"> / {c.algorithm}</span><small className="table-muted"> · {c.job_id}</small></td><td className="mono">{c.steps.toLocaleString()}</td><td>{c.successes||0} / {c.evaluation_episodes} successes</td><td className="mono">{c.mean_reward.toFixed(1)}</td><td><span className="tag">{c.evaluation_episodes>=10000?'FULL BATCH':'PILOT'}</span></td><td><button className="watch-button" onClick={()=>onWatch(c)}><Play size={12}/>Watch flight</button></td></tr>)}</tbody></table>{!checkpoints.length&&<p className="empty-message">Train a policy to create your first checkpoint.</p>}</div></section></>;
}

function ResultsView({results,runs,currentConfigHash,currentDynamicsHash,currentMission}:{results:Result[];runs:Run[];currentConfigHash?:string;currentDynamicsHash?:string;currentMission?:Mission}){
 const [filter,setFilter]=useState<string>(currentMission||'landing'),[configFilter,setConfigFilter]=useState('current'),[failureSample,setFailureSample]=useState('');
 const configHash=configFilter==='current'?currentConfigHash:configFilter;
 const filtered=results.filter(value=>value.mission===filter&&(configFilter==='all'||value.config_hash===configHash)&&(configFilter!=='current'||value.dynamics_hash===currentDynamicsHash));
 const classical=largestClassicalSamples(configFilter==='current'?filtered:results,filter,configFilter==='all'?currentConfigHash:configHash);
 const failureResult=filtered.find(value=>resultSampleId(value)===failureSample)||filtered.find(value=>value.method==='rl'&&value.episodes>=10000)||[...filtered].sort((a,b)=>b.episodes-a.episodes)[0];
 const hashes=[...new Set(results.filter(value=>value.mission===filter).map(value=>value.config_hash).filter((value):value is string=>!!value))];
 return <><div className="results-intro panel"><div><span className="eyebrow">REPRODUCIBLE COMPARISONS</span><h2>Identical physics. Fixed seeds. Measured outcomes.</h2><p>Current landing runs require center and contact speed &lt; 2 m/s, tilt &lt; 5°, and coordinate error ≤ 1 m. Archived configurations retain their recorded tolerances. Takeoff uses separate altitude and velocity targets.</p></div><select aria-label="Results mission" className="full-select" value={filter} onChange={e=>setFilter(e.target.value)}><option value="landing">Landing</option><option value="takeoff">Takeoff</option><option value="combined">Combined</option></select></div><div className="qualification"><label>Configuration <select aria-label="Results configuration" className="full-select" value={configFilter} onChange={event=>{setConfigFilter(event.target.value);setFailureSample('');}}><option value="current">Applied flight · {currentConfigHash||'loading'}</option>{hashes.filter(hash=>hash!==currentConfigHash).map(hash=><option key={hash} value={hash}>{hash}</option>)}<option value="all">All archived configurations</option></select></label><span>Current view requires matching dynamics code and configuration. Custom flight plans have their own configuration hashes. Each register row is a separate sample. Reused seeds and checkpoint batches are not pooled. The controller chart uses the largest nominal batch per level for the selected configuration; in archive view it keeps the current configuration.</span></div>
 <div className="results-charts"><section className="panel"><div className="panel-title"><span><ChartNoAxesCombined size={15}/>CLASSICAL CONTROLLER EVALUATION</span></div>{classical.length?<ResponsiveContainer width="100%" height={240}><BarChart data={classical.map(r=>({...r,name:`Level ${r.level}`,observed:r.success_rate*100}))} margin={{top:25,right:25,left:10,bottom:15}}><CartesianGrid stroke="#ece9f5" vertical={false}/><XAxis dataKey="name" tick={{fill:'#8d879f'}} axisLine={false} tickLine={false}/><YAxis domain={[0,100]} tick={{fill:'#8d879f'}} axisLine={false} tickLine={false}/><Tooltip contentStyle={{background:'#ffffff',border:'1px solid #e9e5f4',borderRadius:12,boxShadow:'0 12px 30px -12px rgba(35,26,70,.22)',fontSize:12}} formatter={(_,__,p)=>[`${p.payload.successes}/${p.payload.episodes}`,'Successes']}/><Bar dataKey="observed" radius={[6,6,0,0]}>{classical.map((r,i)=><Cell key={i} fill={r.level===4?'#7a5cf6':'#cbc3e6'}/>)}</Bar></BarChart></ResponsiveContainer>:<div className="empty-chart"><p>No batch evaluation saved for this mission yet.</p><code>python -m rocket_lab.evaluate --mission {filter}</code></div>}</section><section className="panel"><div className="panel-title"><span><Activity size={15}/>FAILURE MODES / ONE BATCH</span></div><div className="qualification"><select className="full-select" aria-label="Failure-mode evaluation" value={failureResult?resultSampleId(failureResult):''} onChange={event=>setFailureSample(event.target.value)}>{filtered.map(value=><option key={resultSampleId(value)} value={resultSampleId(value)}>{value.checkpoint_id||`Classical L${value.level}`} · {value.scenario} · {value.episodes.toLocaleString()} episodes · {value.seeds?.join('–')||'recorded seeds'}</option>)}</select></div><div className="failure-list">{Object.entries(failureResult?.failures||{}).map(([reason,count])=><div key={reason}><span>{reason.replaceAll('_',' ')}</span><strong>{count.toLocaleString()}</strong></div>)}{!failureResult&&<p className="subtle">No measured evaluation data yet.</p>}{failureResult&&!Object.keys(failureResult.failures).length&&<p className="subtle">No failures observed in this batch.</p>}</div></section></div>
 <section className="panel"><div className="panel-title"><span><Terminal size={15}/>EVALUATION REGISTER</span><span className="micro">95% WILSON CONFIDENCE INTERVALS</span></div><div className="table-scroll"><table><thead><tr><th>METHOD</th><th>LEVEL / STEPS</th><th>SCENARIO</th><th>SUCCESSES</th><th>95% INTERVAL</th><th>SPEED</th><th>OFFSET</th><th>SAMPLE</th></tr></thead><tbody>{filtered.map((r,i)=><tr key={i}><td>{r.method==='rl'?'RL agent':'Classical'}</td><td className="mono">{r.checkpoint_id?compact(Number(r.checkpoint_id.match(/step-(\d+)/)?.[1]||0)):`Level ${r.level}`}</td><td>{r.scenario.replaceAll('_',' ')}<span className="table-muted"><br/>{r.config_hash||'unknown configuration'}</span></td><td>{r.successes}/{r.episodes}</td><td className="mono">{(r.confidence_interval[0]*100).toFixed(2)}–{(r.confidence_interval[1]*100).toFixed(2)}%</td><td>{r.mean_touchdown_speed.toFixed(2)} m/s</td><td>{r.mean_pad_distance.toFixed(2)} m</td><td><span className="tag">{r.episodes>=10000?'FULL BATCH':'PILOT'}</span></td></tr>)}</tbody></table></div></section><section className="panel replay-register"><div className="panel-title"><span><Radio size={15}/>RECORDED FLIGHTS</span><span className="micro">FIXED SEED 42</span></div><div className="run-cards">{runs.filter(r=>r.mission===filter&&r.seed===42).map(r=><div key={r.id}><span className="micro">{r.method==='rl'?r.algorithm:'CLASSICAL'} · L{r.level}</span><strong className={r.outcome==='success'?'good-text':'orange-text'}>{r.outcome.replaceAll('_',' ')}</strong><span>{r.touchdown_speed.toFixed(2)} m/s · {r.tilt.toFixed(1)}° · {r.pad_distance.toFixed(1)} m</span></div>)}</div></section></>;
}

function NotesView({system}:{system:SystemInfo|null}){
 const topics=[['01','Six degrees of freedom','MuJoCo integrates translation and quaternion attitude. Thrust acts along a gimballed body axis; its engine lever creates torque. Drag uses relative air velocity.','m v̇ = R F + m g + Fdrag'],['02','Fuel and specific impulse','Mass flow follows thrust divided by specific impulse and standard gravity. Dry mass is retained, and the engine stops when propellant is exhausted.','ṁ = −T / (Isp g₀)'],['03','Classical guidance','Untuned and tuned feedback expose the effect of gains. A convex, constant-mass trajectory approximation is tracked by a gimbal controller. The minimum-thrust bound is relaxed in planning and enforced by physics.','u = Kp e + Kd ė'],['04','Pure reinforcement learning','PPO and SAC receive physical state and mission goals. No expert actions or controller hints are used. The shaped reward balances progress, speed, tilt, propellant and terminal success.','π(a | s) → throttle, gimbal x, gimbal y'],['05','Curriculum and randomization','Starts widen only after a measured rolling success threshold. Fuel mass, engine thrust, wind gusts and sensor noise are randomized from seeded generators.','easy starts → wider distribution → disturbances'],['07','Recovery hardware','Four lower hinges carry fixed-length leg shells. Telescopic braces connect body hardpoints to the feet; the deployed soles match the ground plane and keep the nozzle above it. This is a visual mechanism, not a leg-load or tip-over solver.','4 legs · 6.2 m radial stance · 0.6 m nozzle clearance'],['08','Booster anatomy','The restored shell includes panel seams, circumferential joints, service lines, a lower engine skirt, and a gimballed nozzle. The combined flight has an interstage and released upper-stage preview. These are generic proportions rather than exact Falcon 9 CAD.','tank shell → engine section → interstage'],['06','Evidence and uncertainty','Each saved checkpoint includes its normalization statistics and a held-out pilot evaluation. Full 10,000-seed qualification is tracked separately. A checkpoint label does not prove maturity.','p̂ ± uncertainty · Wilson 95% interval']];
 return <><div className="notes-layout"><section className="notes-top panel"><span className="eyebrow">ROCKET MISSION LAB / ENGINEERING NOTES</span><h2>A simulator you can inspect and explain.</h2><p>This is an educational, generic rocket simulation with approximate parameters. It is not a real vehicle model, an orbital simulator, or flight-certified guidance. Upper grid fins are omitted from the drawing at your request. Four hinged landing legs unfold before final descent; their braces are visual hardware, while first sole contact includes the tilted foot positions and impact speed. Compliant contact and post-touchdown toppling are not simulated. Combined missions release a generic 2.5 t unpowered stage, integrated independently with gravity and drag. Archived replays retain a labelled ideal ballistic preview. The separate suborbital study uses a generic 140 t propellant, 3.2 MN, 360 s Isp vehicle and inverse-square vertical gravity. Aerodynamic lift, slosh, structural flexibility, upper-stage propulsion and orbital flight are outside this model.</p><div className="note-tags"><span className="tag">OPEN SOURCE STACK</span><span className="tag">HEADLESS TRAINING</span><span className="tag">LOCAL DATA</span></div></section><section className="panel runtime"><div className="panel-title"><span><Cpu size={15}/>VERIFIED LOCAL RUNTIME</span></div><dl><dt>GPU</dt><dd>{system?.runtime.gpu||'Runtime unavailable offline'}</dd><dt>PyTorch</dt><dd>{system?.runtime.packages?.torch||'—'}</dd><dt>CUDA</dt><dd>{system?.runtime.cuda||'—'}</dd><dt>MuJoCo</dt><dd>{system?.runtime.packages?.mujoco||'—'}</dd><dt>Python</dt><dd>{system?.runtime.python||'—'}</dd></dl></section></div><div className="topic-grid">{[...topics].sort((a,b)=>a[0].localeCompare(b[0])).map(([n,title,description,formula])=><article className="panel topic" key={n}><span className="topic-number">{n}</span><h3>{title}</h3><p>{description}</p><code>{formula}</code></article>)}</div><section className="panel research"><div className="panel-title"><span><BookOpen size={15}/>RESEARCH SOURCES</span><span className="micro">PRIMARY DOCUMENTATION & PAPERS</span></div>{system?.research.map(r=><a href={r.url} key={r.url} target="_blank" rel="noreferrer"><div><strong>{r.title}</strong><p>{r.application}</p></div><ArrowUpRight size={17}/></a>)||<p className="empty-message">See docs/RESEARCH.md in the project for sources and implementation decisions.</p>}</section></>;
}
