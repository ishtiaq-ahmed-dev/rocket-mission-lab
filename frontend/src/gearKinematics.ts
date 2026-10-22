/** Visual hinge geometry in meters; not a compliant multi-contact physics model. */
export const LEG_HINGE: [number,number,number]=[1.84,-17.4,0];
export const LEG_LENGTH=Math.hypot(4.36,2.45);
export const LEG_OPEN_ANGLE=Math.atan2(4.36,-2.45);
const smooth=(x:number)=>{const t=Math.max(0,Math.min(1,x));return t*t*(3-2*t);};

export function gearDeployment(phase:string,clearance:number){
  // The launch structure supports the skirt. Recovery legs remain stowed
  // throughout ascent and deploy once for final descent.
  return phase==='landing'?1-smooth((clearance-35)/65):0;
}
export function legAngle(deployment:number){return .035+(LEG_OPEN_ANGLE-.035)*Math.max(0,Math.min(1,deployment));}
export function legFoot(deployment:number):[number,number,number]{
  const angle=legAngle(deployment);
  return [LEG_HINGE[0]+Math.sin(angle)*LEG_LENGTH,LEG_HINGE[1]+Math.cos(angle)*LEG_LENGTH,0];
}
