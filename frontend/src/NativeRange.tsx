export default function NativeRange({launch,landing,position}:{launch:[number,number];landing:[number,number];position?:number[]}){
 // Fix the site's coordinate frame; a moving rocket must not rescale the pads.
 const sites=[launch,landing];
 const minX=Math.min(...sites.map(site=>site[0])),maxX=Math.max(...sites.map(site=>site[0]));
 const minY=Math.min(...sites.map(site=>site[1])),maxY=Math.max(...sites.map(site=>site[1]));
 const scale=Math.min(700/Math.max(100,maxX-minX),300/Math.max(100,maxY-minY));
 const project=(site:number[])=>[100+(site[0]-minX)*scale,390-(site[1]-minY)*scale];
 const a=project(launch),b=project(landing),rocket=position?project(position):null;
 const distance=Math.hypot(landing[0]-launch[0],landing[1]-launch[1]);
 return <svg viewBox="0 0 900 500" className="radar-svg" role="img" aria-label={`Takeoff and landing sites ${distance.toFixed(2)} meters apart`}>
  <rect width="900" height="500" fill="#0c0a17"/>
  <text x="30" y="30" fill="#a493f7" fontSize="16">N ↑ · X EAST / Y NORTH · {(distance/1000).toFixed(3)} KM BETWEEN PADS</text>
  <line x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} stroke="#6f56e8" strokeDasharray="6 6"/>
  {[[a,launch,'TAKEOFF','#f59e0b'],[b,landing,'LANDING','#10b981']].map(([point,site,label,color])=>{
   const [cx,cy]=point as number[],xy=site as number[];
   return <g key={label as string} transform={`translate(${cx},${cy})`}>
    <circle r="24" fill="none" stroke={color as string} strokeWidth="2"/>
    <path d="M -10 0 H 10 M 0 -10 V 10" stroke={color as string}/>
    <text y="-40" fill={color as string} fontSize="16" textAnchor="middle">{label as string}</text>
    <text y="44" fill="#c1bacd" fontSize="13" textAnchor="middle">[{xy[0].toFixed(0)}, {xy[1].toFixed(0)}] m</text>
   </g>;
  })}
  {rocket&&<circle cx={rocket[0]} cy={rocket[1]} r="7" fill="#ef4444"><title>Live vehicle position</title></circle>}
 </svg>;
}
