import {lazy,Suspense,useState} from 'react';
import {Rocket} from 'lucide-react';
import NativeMonitor from './NativeMonitor';

const LegacyWorkspace=lazy(()=>import('./App'));

/** Keep charts, legacy replay, Three and training tools out of native startup. */
export default function NativeApp(){
 const [legacyPage,setLegacyPage]=useState<string|null>(null);
 if(legacyPage)return <Suspense fallback={<main className="content-page" role="status">Loading research workspace…</main>}><LegacyWorkspace initialPage={legacyPage}/></Suspense>;
 return <div className="shell native-shell"><header className="topnav">
  <a className="brand" href="#" onClick={event=>event.preventDefault()}><span className="brand-mark"><Rocket size={20}/></span><span className="brand-copy">Rocket Mission Lab<small>Flight dynamics &amp; control</small></span></a>
  <nav className="main-nav" aria-label="Primary navigation"><button className="active">Isaac Sim</button>{[['Flight lab','Legacy replay'],['Training','Training'],['Results','Results'],['Field notes','Field notes']].map(([page,label])=><button key={page} onClick={()=>setLegacyPage(page)}>{label}</button>)}</nav>
  <div className="nav-tools"><span className="tag">Native flight control</span></div>
 </header><main className="shell-main"><NativeMonitor/></main></div>;
}
