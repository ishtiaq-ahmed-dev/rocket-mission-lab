const smooth=(a:number,b:number,x:number)=>{const t=Math.max(0,Math.min(1,(x-a)/(b-a)));return t*t*(3-2*t);};
export const shoreline=(z:number)=>320+110*Math.sin(z/440)+80*Math.cos(z/250);
/** One shared surface for geometry, roads, rocks, buildings and vegetation. */
export function terrainHeight(x:number,z:number,sites:readonly [number,number][]=[]){
  const land=smooth(0,140,shoreline(z)-x),distance=Math.hypot(x,z);
  // Preserve a flat engineered complex so roads and facilities cannot be buried.
  const range=Math.max(smooth(430,720,Math.abs(x)),smooth(180,400,Math.abs(z)));
  const hills=(Math.sin(x*.009)*Math.cos(z*.006)*13+20+Math.sin(x*.026+z*.018)*3)*smooth(190,800,distance)*range;
  // Fine relief outside the paved range leaves every foundation level.
  const unpaved=Math.max(smooth(20,32,Math.abs(z)),smooth(335,360,-x),smooth(34,48,x));
  const foundations=(1-smooth(110,130,Math.abs(z)))*(1-smooth(-100,-85,x))*smooth(-350,-335,x);
  const relief=(.085*Math.sin(x*.72+z*.16)*Math.cos(z*.61)+.035*Math.sin(x*1.7-z*1.1))*unpaved*(1-foundations);
  const height=-4+land*(4+hills+relief);
  // Prepared sites stay at the simulation's Z=0 contact plane, including
  // relocated pads. Blend the earthwork edge into the original coastline.
  const blend=sites.reduce((value,[sx,sz])=>{
    // Distant mesh cells are larger. Prepare enough ground that their
    // interpolated triangles also stay beneath the complete pad footprint.
    const range=Math.max(Math.abs(sx),Math.abs(sz)),radius=range>2300?205:range>450?70:40;
    return Math.min(value,smooth(radius,radius+32,Math.hypot(x-sx,z-sz)));
  },1);
  return height*blend;
}
