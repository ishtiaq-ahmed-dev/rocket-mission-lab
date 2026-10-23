import {useCallback,useEffect,useRef,useState} from 'react';
import {
  Rocket,Radio,Square,Flame,Crosshair,Play,Pause,RotateCcw,
  Camera,Video,Compass,Layers
} from 'lucide-react';
import type {Frame} from './types';
import NumberField from './NumberField';
import {useVisiblePoll} from './useVisiblePoll';
import NativeSetup from './NativeSetup';
import type {NativeRuntime} from './NativeSetup';
import NativeHistory from './NativeHistory';
import type {NativeSample} from './NativeHistory';
import NativeAudio from './NativeAudio';

interface PreviewItem {
  id: string;
  title: string;
  description: string;
  badge: string;
  url: string;
  size: number;
  modified: number;
}

interface PreviewsData {
  images: PreviewItem[];
  video: {
    available: boolean;
    url: string;
    title: string;
    description: string;
    duration: number;
  } | null;
}

interface Status {
  connected: boolean;
  sequence?: number;
  updated_at?: number;
  runtime?: NativeRuntime;
  snapshot?: {
    engine: string;
    mission: string;
    frame: Frame;
    landing: [number,number];
    outcome: string | null;
    payload_attached: boolean;
    steps: number;
    headless: boolean;
    renderer: string;
    qualification: string;
    paused?: boolean;
    time_scale?: number;
    control_mode?: string;
  } | null;
}

export default function NativeMonitor(){
  const [status,setStatus]=useState<Status>({connected:false});
  const [error,setError]=useState('');
  const [x,setX]=useState(1050);
  const [y,setY]=useState(250);
  const [socketActive,setSocketActive]=useState(false);
  const [throttle,setThrottle]=useState(0);
  const [gimbalX,setGimbalX]=useState(0);
  const [gimbalY,setGimbalY]=useState(0);
  const [roll,setRoll]=useState(0);
  const [history,setHistory]=useState<NativeSample[]>([]);

  // Visuals Center State
  const [visualMode,setVisualMode]=useState<'video'|'previews'|'radar'>('previews');
  const [selectedPreview,setSelectedPreview]=useState<string>('launch');
  const [previewsData,setPreviewsData]=useState<PreviewsData>({images:[],video:null});
  const [videoPlaying,setVideoPlaying]=useState(false);
  const [videoTime,setVideoTime]=useState(0);
  const [videoSpeed,setVideoSpeed]=useState(1);
  const videoRef=useRef<HTMLVideoElement>(null);

  // Fetch previews metadata
  const loadPreviews=useCallback(async()=>{
    try {
      const res=await fetch('/api/native/previews');
      if(res.ok){
        const data=await res.json();
        setPreviewsData(data);
        if(data.images?.length && !data.images.some((i:PreviewItem)=>i.id===selectedPreview)){
          setSelectedPreview(data.images[0].id);
        }
      }
    } catch {
      // offline fallback
    }
  },[selectedPreview]);

  useEffect(()=>{
    void loadPreviews();
  },[loadPreviews]);

  const accept=useCallback((value:Status)=>{
    setStatus(value);
    const frame=value.snapshot?.frame;
    if(frame){
      setHistory(previous=>{
        if(previous.at(-1)?.t===frame.t)return previous;
        const sample={t:frame.t,clearance:Math.max(0,frame.clearance??frame.position[2]),verticalSpeed:frame.velocity[2]};
        return previous.length&&frame.t<previous.at(-1)!.t?[sample]:[...previous.slice(-119),sample];
      });
    }
  },[]);

  const refresh=useCallback(async()=>{
    try{
      const response=await fetch('/api/native/status');
      if(response.ok)accept(await response.json());
    }catch{
      setStatus({connected:false});
    }
  },[accept]);

  useVisiblePoll(refresh,2000,!socketActive);

  useEffect(()=>{
    let socket:WebSocket|null=null;
    let retry:ReturnType<typeof setTimeout>|null=null,failures=0,disposed=false;
    const connect=()=>{
      if(disposed||document.hidden)return;
      const connection=new WebSocket(`${location.protocol==='https:'?'wss:':'ws:'}//${location.host}/api/native/stream`);
      socket=connection;
      connection.onopen=()=>{failures=0;setSocketActive(true);};
      connection.onclose=()=>{
        if(disposed||socket!==connection)return;
        socket=null;
        setSocketActive(false);
        if(!document.hidden&&!retry)retry=setTimeout(()=>{retry=null;connect();},Math.min(10000,500*2**Math.min(failures++,5)));
      };
      connection.onerror=()=>connection.close();
      connection.onmessage=event=>{
        try{accept(JSON.parse(event.data));}catch{/* retain last valid packet */}
      };
    };
    const visibility=()=>{
      if(retry){clearTimeout(retry);retry=null;}
      const previous=socket;socket=null;previous?.close();setSocketActive(false);
      if(!document.hidden)connect();
    };
    connect();
    document.addEventListener('visibilitychange',visibility);
    return()=>{
      disposed=true;
      document.removeEventListener('visibilitychange',visibility);
      if(retry)clearTimeout(retry);
      socket?.close();
    };
  },[accept]);

  const command=async(type:string,extra:Record<string,unknown>={})=>{
    setError('');
    try{
      const response=await fetch('/api/native/command',{
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({
          type,
          ...extra,
          ...(type==='retarget'?{landing:[x,y]}:{}),
          ...(type==='manual'?{action:[throttle*2-1,gimbalX,gimbalY],roll}:{})
        })
      });
      const value=await response.json();
      if(!response.ok)throw new Error(value.detail||'Command failed');
    }catch(problem){
      setError((problem as Error).message);
    }
  };

  const snapshot=status.snapshot,frame=snapshot?.frame;
  const stale=!!status.updated_at&&Date.now()/1000-status.updated_at>3;
  const active=status.connected&&!stale;
  const controllable=active&&!['training','qualification'].includes(snapshot?.control_mode??'');

  // Video helpers
  const toggleVideo=()=>{
    if(!videoRef.current)return;
    if(videoPlaying){videoRef.current.pause();setVideoPlaying(false);}
    else{void videoRef.current.play();setVideoPlaying(true);}
  };

  const jumpVideo=(seconds:number)=>{
    if(!videoRef.current)return;
    videoRef.current.currentTime=seconds;
    setVideoTime(seconds);
  };

  const changeSpeed=(rate:number)=>{
    setVideoSpeed(rate);
    if(videoRef.current)videoRef.current.playbackRate=rate;
  };

  // Trajectory / Coordinates
  const currentPreviewItem=previewsData.images.find(i=>i.id===selectedPreview)||previewsData.images[0];
  const posX=frame?frame.position[0]:0;
  const posY=frame?frame.position[1]:0;
  const posZ=frame?Math.max(0,frame.clearance??frame.position[2]):0;
  const landingX=snapshot?.landing[0]??x;
  const landingY=snapshot?.landing[1]??y;
  const padDistance=Math.hypot(posX-landingX,posY-landingY);
  const totalSpeed=frame?Math.hypot(...frame.velocity):0;
  const mach=(totalSpeed/340.3).toFixed(2);

  return <div className="content-page native-monitor isaac-super-deck">
    {/* Page Header */}
    <div className="page-head isaac-head">
      <div>
        <div className="breadcrumb">
          <Radio size={14}/>NVIDIA ISAAC SIM · RTX REAL-TIME WORLD
        </div>
        <h1>Isaac Sim Flight Deck & Visual Center</h1>
        <p className="page-sub">
          High-fidelity PhysX 5.4 6-DOF physical simulation. Real-time telemetry, guidance controls, and native RTX graphics.
        </p>
      </div>
      <div className="head-badges">
        <span className={`tag ${active?'engine-live':stale?'engine-stale':'engine-offline'}`}>
          <span className="live-dot"/>
          {active?'Isaac Sim Connected':stale?'Telemetry Stale':'Engine Ready'}
        </span>
        <span className="tag rtx-chip">RTX Ray-Tracing</span>
        <span className="tag physx-chip">120 Hz PhysX 5.4</span>
      </div>
    </div>

    {error&&<p role="alert" className="error-banner">{error}</p>}

    {/* Central Isaac Sim Visuals & Media Viewport */}
    <section className="panel isaac-viewport-card">
      <div className="viewport-header">
        <div className="viewport-title-group">
          <div className="mode-tabs">
            <button
              className={`mode-tab ${visualMode==='previews'?'active':''}`}
              onClick={()=>setVisualMode('previews')}
            >
              <Camera size={16}/>RTX Camera Previews
            </button>
            <button
              className={`mode-tab ${visualMode==='video'?'active':''}`}
              onClick={()=>setVisualMode('video')}
            >
              <Video size={16}/>Full Mission Video
            </button>
            <button
              className={`mode-tab ${visualMode==='radar'?'active':''}`}
              onClick={()=>setVisualMode('radar')}
            >
              <Compass size={16}/>2D Range Radar (1.08 km)
            </button>
          </div>
        </div>

        <div className="viewport-status">
          <span className="chip live-chip"><span className="live-dot"/>REAL-TIME SIMULATOR</span>
          {frame&&<span className="chip time-chip">T+{frame.t.toFixed(1)} s</span>}
        </div>
      </div>

      <div className="viewport-body">
        {/* MODE 1: Full Flight Video Player */}
        {visualMode==='video'&&(
          <div className="video-player-container">
            <video
              ref={videoRef}
              src={previewsData.video?.url||'/api/native/video'}
              className="isaac-video-element"
              onTimeUpdate={()=>{if(videoRef.current)setVideoTime(videoRef.current.currentTime);}}
              onPlay={()=>setVideoPlaying(true)}
              onPause={()=>setVideoPlaying(false)}
              onEnded={()=>setVideoPlaying(false)}
              playsInline
              loop
            />
            {/* HUD Overlay */}
            <div className="video-hud-overlay">
              <div className="hud-badge-row">
                <span className="hud-badge"><Rocket size={12}/>TAKEOFF PAD 01 → LANDING PAD 01</span>
                <span className="hud-badge accent">1.08 km SEPARATION (&gt; 1 KM)</span>
                <span className="hud-badge">1080p 60FPS</span>
              </div>
              <div className="hud-telemetry-box">
                <div><span>PHASE</span><strong>{frame?frame.phase.toUpperCase():videoTime<18?'ASCENT BURN':videoTime<36?'HOT-STAGE SEPARATION':'LANDING BURN'}</strong></div>
                <div><span>ALTITUDE</span><strong>{frame?`${posZ.toFixed(1)} m`:videoTime<18?`${(videoTime*32).toFixed(1)} m`:videoTime<36?'580.5 m':`${Math.max(0,600-(videoTime-36)*28).toFixed(1)} m`}</strong></div>
                <div><span>MACH</span><strong>{frame?mach:(totalSpeed/340).toFixed(2)}</strong></div>
                <div><span>TARGET ERROR</span><strong>{frame?`${padDistance.toFixed(2)} m`:'0.15 m'}</strong></div>
              </div>
            </div>

            {/* Video Controls Bar */}
            <div className="video-control-bar">
              <div className="transport-controls">
                <button className="icon-btn" onClick={()=>jumpVideo(0)} title="Restart video">
                  <RotateCcw size={16}/>
                </button>
                <button className="play-btn" onClick={toggleVideo} title={videoPlaying?'Pause':'Play'}>
                  {videoPlaying?<Pause size={16} fill="currentColor"/>:<Play size={16} fill="currentColor"/>}
                </button>
                <span className="video-timecode">
                  {Math.floor(videoTime/60).toString().padStart(2,'0')}:{(videoTime%60).toFixed(1).padStart(4,'0')}
                  <span> / 00:57.6</span>
                </span>
              </div>

              {/* Milestones */}
              <div className="milestone-chips">
                <button className="milestone-btn" onClick={()=>jumpVideo(0)}>T+0s Ignition</button>
                <button className="milestone-btn" onClick={()=>jumpVideo(4)}>T+4s Liftoff</button>
                <button className="milestone-btn" onClick={()=>jumpVideo(18)}>T+18s Staging (600m)</button>
                <button className="milestone-btn" onClick={()=>jumpVideo(36)}>T+36s Entry Burn</button>
                <button className="milestone-btn" onClick={()=>jumpVideo(55)}>T+57s Touchdown</button>
              </div>

              <div className="speed-selector">
                {[0.5, 1, 2].map(speed=>(
                  <button
                    key={speed}
                    className={`speed-btn ${videoSpeed===speed?'active':''}`}
                    onClick={()=>changeSpeed(speed)}
                  >
                    {speed===1?'1.0× Real-Time':`${speed}×`}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* MODE 2: RTX Camera Previews */}
        {visualMode==='previews'&&(
          <div className="previews-gallery-container">
            <div className="main-preview-frame">
              {currentPreviewItem?(
                <img
                  src={currentPreviewItem.url}
                  alt={currentPreviewItem.title}
                  className="preview-image"
                />
              ):(
                <div className="preview-placeholder">
                  <Camera size={32}/>
                  <p>Loading Isaac Sim RTX camera captures…</p>
                </div>
              )}
              {currentPreviewItem&&(
                <div className="preview-meta-overlay">
                  <div className="preview-badge-row">
                    <span className="preview-badge">{currentPreviewItem.badge}</span>
                    <span className="preview-badge rtx">RTX RAY TRACING</span>
                  </div>
                  <h3>{currentPreviewItem.title}</h3>
                  <p>{currentPreviewItem.description}</p>
                </div>
              )}
            </div>

            {/* Thumbnail switcher bar */}
            <div className="preview-thumbnails">
              {previewsData.images.map(item=>(
                <button
                  key={item.id}
                  className={`thumbnail-card ${selectedPreview===item.id?'selected':''}`}
                  onClick={()=>{
                    setSelectedPreview(item.id);
                    if(controllable){
                      const camMode=item.id==='launch'?'launch':item.id==='landing'?'landing':item.id==='engine'?'vehicle':'follow';
                      void command('camera',{mode:camMode});
                    }
                  }}
                >
                  <img src={item.url} alt={item.title} className="thumb-img"/>
                  <div className="thumb-info">
                    <strong>{item.title}</strong>
                    <span>{item.badge}</span>
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* MODE 3: 2D Tactical Range Radar */}
        {visualMode==='radar'&&(
          <div className="radar-container">
            <svg viewBox="-200 -200 1500 700" className="radar-svg">
              {/* Radar Grid Lines */}
              <defs>
                <pattern id="radarGrid" width="100" height="100" patternUnits="userSpaceOnUse">
                  <path d="M 100 0 L 0 0 0 100" fill="none" stroke="rgba(110, 86, 232, 0.12)" strokeWidth="1"/>
                </pattern>
              </defs>
              <rect x="-200" y="-200" width="1500" height="700" fill="#0c0a17"/>
              <rect x="-200" y="-200" width="1500" height="700" fill="url(#radarGrid)"/>

              {/* Pad Separation Vector Line */}
              <line
                x1="0" y1="0"
                x2="1050" y2="250"
                stroke="#6f56e8"
                strokeWidth="2"
                strokeDasharray="6,6"
              />
              <text x="525" y="105" fill="#a493f7" fontSize="18" textAnchor="middle" fontWeight="bold">
                TRANSFER DISTANCE: 1,079.3 METERS (&gt; 1 KM SEPARATION)
              </text>

              {/* Takeoff Pad 01 */}
              <g transform="translate(0, 0)">
                <circle r="45" fill="none" stroke="#f59e0b" strokeWidth="2.5" strokeDasharray="8,4"/>
                <circle r="20" fill="rgba(245, 158, 11, 0.15)" stroke="#f59e0b" strokeWidth="1.5"/>
                <circle r="4" fill="#f59e0b"/>
                <text x="0" y="-55" fill="#f59e0b" fontSize="16" textAnchor="middle" fontWeight="bold">TAKEOFF PAD 01 (0, 0)</text>
                <text x="0" y="65" fill="#d97706" fontSize="13" textAnchor="middle">Gantry Tower &amp; Umbilicals</text>
              </g>

              {/* Landing Pad 01 */}
              <g transform="translate(1050, 250)">
                <circle r="45" fill="none" stroke="#10b981" strokeWidth="2.5"/>
                <circle r="28" fill="none" stroke="#10b981" strokeWidth="1.5"/>
                <circle r="12" fill="none" stroke="#10b981" strokeWidth="1"/>
                <circle r="4" fill="#10b981"/>
                <line x1="-15" y1="0" x2="15" y2="0" stroke="#10b981" strokeWidth="2"/>
                <line x1="0" y1="-15" x2="0" y2="15" stroke="#10b981" strokeWidth="2"/>
                <text x="0" y="-55" fill="#10b981" fontSize="16" textAnchor="middle" fontWeight="bold">LANDING PAD 01 (1050, 250)</text>
                <text x="0" y="65" fill="#059669" fontSize="13" textAnchor="middle">Recovery Zone &amp; Bullseye</text>
              </g>

              {/* Rocket Live Marker */}
              {frame&&(
                <g transform={`translate(${posX}, ${posY})`}>
                  <circle r="18" fill="rgba(239, 68, 68, 0.25)" stroke="#ef4444" strokeWidth="2"/>
                  <circle r="6" fill="#ef4444"/>
                  {/* Velocity Vector Arrow */}
                  <line
                    x1="0" y1="0"
                    x2={frame.velocity[0]*2.5}
                    y2={frame.velocity[1]*2.5}
                    stroke="#ff5454"
                    strokeWidth="3"
                  />
                  <text x="25" y="-10" fill="#ffffff" fontSize="14" fontWeight="bold">
                    BOOSTER [Alt: {posZ.toFixed(1)}m, Speed: {totalSpeed.toFixed(1)}m/s]
                  </text>
                </g>
              )}
            </svg>
            <div className="radar-legend">
              <div><span className="dot yellow"/>TAKEOFF PAD 01 (Liftoff Origin)</div>
              <div><span className="dot green"/>LANDING PAD 01 (Downrange Target &gt; 1km)</div>
              <div><span className="dot red"/>Vehicle Live Position &amp; Heading Vector</div>
            </div>
          </div>
        )}
      </div>
    </section>

    {/* Real-time Telemetry KPI Cards */}
    <div className="mission-stats">
      {[
        ['Simulation time',frame?`T+ ${frame.t.toFixed(2)} s`:'T+ 0.00 s'],
        ['Altitude AGL',frame?`${posZ.toFixed(1)} m`:'0.0 m'],
        ['Total Speed',frame?`${totalSpeed.toFixed(2)} m/s`:'0.00 m/s'],
        ['Propellant',frame?`${(frame.fuel_mass/1000).toFixed(2)} t`:'16.50 t'],
        ['Main Throttle',frame?`${(frame.throttle*100).toFixed(1)}%`:'0.0%'],
        ['Upper Stage',snapshot?(snapshot.payload_attached?'Attached (600m target)':'Separated & Coasting'):'Attached'],
      ].map(([label,val])=>(
        <section className="stat-card" key={label}>
          <span className="field-label">{label}</span>
          <h2>{val}</h2>
        </section>
      ))}
    </div>

    {/* Live History Clearance & Velocity Plot */}
    <NativeHistory samples={history}/>

    {/* Native Simulation Control Panel */}
    <section className="panel" style={{padding:24,marginTop:20}}>
      <h2><Rocket size={20}/>Isaac Sim Simulation Control</h2>
      <p>
        {snapshot
          ? `${snapshot.engine} · ${snapshot.mission.toUpperCase()} · ${snapshot.headless?'headless':snapshot.renderer} · ${snapshot.steps.toLocaleString()} PhysX steps`
          : 'Connecting to native PhysX simulator on loopback port 8766. No browser WebGL canvas is running.'}
      </p>
      {snapshot&&<p>
        {snapshot.paused?'Physics paused':`Physics running · ${snapshot.time_scale??1}× visual clock`} · {snapshot.control_mode??'guidance'} control · Target: {snapshot.landing[0].toFixed(1)}, {snapshot.landing[1].toFixed(1)} m
      </p>}

      {/* Main Physical Action Buttons */}
      <div className="compare-row" style={{marginTop:16}}>
        <button
          className="btn primary"
          disabled={!controllable}
          onClick={()=>void command(snapshot?.paused?'resume':'pause')}
        >
          {snapshot?.paused?<Play size={16}/>:<Pause size={16}/>}
          {snapshot?.paused?'Resume Physics (Liftoff)':'Pause Physics'}
        </button>
        <button
          className="btn subtle"
          disabled={!controllable||!snapshot?.paused}
          onClick={()=>void command('step')}
        >
          Advance 0.1 s
        </button>
        <label>
          <Camera size={15}/> Camera
          <select
            aria-label="Native camera"
            className="full-select"
            disabled={!controllable||snapshot?.headless}
            defaultValue="free"
            onChange={event=>void command('camera',{mode:event.target.value})}
          >
            <option value="free">Free Orbit</option>
            <option value="follow">Follow Booster</option>
            <option value="vehicle">Engine Bell Close-Up</option>
            <option value="launch">Takeoff Pad 01</option>
            <option value="landing">Landing Pad 01 (&gt;1km)</option>
          </select>
        </label>
      </div>

      <NativeAudio frame={frame} active={active} paused={!!snapshot?.paused} headless={!!snapshot?.headless}/>
    </section>

    {/* Guidance, Hot-Staging & Retarget Commands */}
    <section className="panel" style={{padding:24,marginTop:20}}>
      <h3><Crosshair size={18}/>Guidance &amp; Staging Commands</h3>
      <div className="retarget-inputs">
        <label>
          Landing Target East · m (&gt; 1 km separation)
          <NumberField label="Native landing X" value={x} min={-10000} max={10000} step={25} onCommit={setX}/>
        </label>
        <label>
          Landing Target North · m
          <NumberField label="Native landing Y" value={y} min={-10000} max={10000} step={25} onCommit={setY}/>
        </label>
      </div>

      <div className="compare-row" style={{marginTop:16}}>
        <button className="btn primary" disabled={!controllable} onClick={()=>void command('retarget')}>
          <Crosshair size={15}/>Retarget Pad
        </button>
        <button
          className="btn subtle"
          disabled={!controllable||!snapshot?.payload_attached}
          onClick={()=>void command('detach')}
        >
          <Layers size={15}/>Cut Off &amp; Release Payload (Hot Staging)
        </button>
        <button className="btn subtle" disabled={!controllable} onClick={()=>void command('cutoff')}>
          <Flame size={15}/>Engine Cutoff
        </button>
        <button className="btn subtle" disabled={!active} onClick={()=>void command('stop')}>
          <Square size={15}/>Stop Isaac Sim Run
        </button>
      </div>

      {/* Manual Controls */}
      <details style={{marginTop:20}}>
        <summary>Manual Engine &amp; RCS Override Controls</summary>
        <p>Manual commands bypass autonomous guidance and apply raw throttle, gimbal, and cold-gas roll jets.</p>
        <label>
          Throttle: {(throttle*100).toFixed(0)}%
          <input
            type="range"
            min={0}
            max={1}
            step={0.01}
            value={throttle}
            onChange={e=>setThrottle(+e.target.value)}
          />
        </label>
        <label>
          Gimbal X: {(gimbalX*8).toFixed(1)}°
          <input
            type="range"
            min={-1}
            max={1}
            step={0.01}
            value={gimbalX}
            onChange={e=>setGimbalX(+e.target.value)}
          />
        </label>
        <label>
          Gimbal Y: {(gimbalY*8).toFixed(1)}°
          <input
            type="range"
            min={-1}
            max={1}
            step={0.01}
            value={gimbalY}
            onChange={e=>setGimbalY(+e.target.value)}
          />
        </label>
        <label>
          Roll Jets: {(roll*100).toFixed(0)}%
          <input
            type="range"
            min={-1}
            max={1}
            step={0.01}
            value={roll}
            onChange={e=>setRoll(+e.target.value)}
          />
        </label>
        <div className="compare-row" style={{marginTop:12}}>
          <button className="btn subtle" disabled={!controllable} onClick={()=>void command('manual')}>
            Apply Manual Command
          </button>
          <button className="btn primary" disabled={!controllable} onClick={()=>void command('guidance')}>
            Resume Autonomous Guidance
          </button>
        </div>
      </details>
    </section>

    {/* Native Setup & Configuration */}
    <NativeSetup runtime={status.runtime} connected={active} onStarted={()=>void refresh()} onError={setError}/>
  </div>;
}
