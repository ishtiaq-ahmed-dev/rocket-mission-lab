let capture:(()=>void)|null=null;
export const registerCapture=(fn:(()=>void)|null)=>{capture=fn;};
export function capture4k(){if(!capture)throw new Error('The 3D scene is still loading. Wait for the world to appear.');capture();}
export function pixelRatioForQuality(quality:string,width:number,height:number){
 if(quality==='4K')return Math.min(4,Math.max(1,Math.min(3840/Math.max(1,width),2160/Math.max(1,height))));
 return quality==='Ultra'?1.5:quality==='High'?1.25:1;
}
