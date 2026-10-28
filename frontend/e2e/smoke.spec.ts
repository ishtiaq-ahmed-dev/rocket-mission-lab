import {test,expect} from '@playwright/test';

test('model flight deck plays a real MuJoCo run and re-runs the engine',async({page})=>{
 const errors:string[]=[];
 page.on('pageerror',e=>errors.push(e.message));
 page.on('console',m=>{if(m.type()==='error'||m.text().includes('INVALID_OPERATION'))errors.push(m.text());});
 await page.goto('/');
 await page.waitForFunction(()=>Boolean((window as any).__sim?.run),null,{timeout:60000});
 const first=await page.evaluate(()=>{
  const s=(window as any).__sim;(window as any).__manual=true;s.setPlaying(false);
  const sample=(t:number)=>{s.seek(t);s.draw(.016);return {t,alt:s.ST.alt,speed:s.ST.speed,thr:s.ST.thr,phase:s.phases[s.ST.phase].s,x:s.dbg.rocket.position.x,y:s.dbg.rocket.position.y,z:s.dbg.rocket.position.z};};
  const start=sample(0),mid=sample(s.end*0.5),end=sample(s.end);
  const pads={launch:s.dbg.launchGroup.children[0].geometry.type,landing:s.dbg.lzGroup.children[0].geometry.type,launchRadius:s.dbg.launchGroup.children[0].geometry.parameters.radius,landingRadius:s.dbg.lzGroup.children[0].geometry.parameters.radius,launchChildren:s.dbg.launchGroup.children.length,landingChildren:s.dbg.lzGroup.children.length,towerDistance:Math.hypot(s.dbg.towerGroup.position.x,s.dbg.towerGroup.position.z)};
  const run={mission:s.run.mission,method:s.run.method,outcome:s.run.outcome,source:s.run.source,duration:s.end,frames:s.telemetry.frames.length};
  const lz={x:s.dbg.lzGroup.position.x,z:s.dbg.lzGroup.position.z};
  const phases=s.phases.map((p:any)=>p.s);
  s.seek(0);s.draw(.016);
  return {start,mid,end,pads,run,lz,phases,calls:s.renderer.info.render.calls,stage:s.dbg.upperStage.visible};
 });
 expect(first.run.source).toContain('MuJoCo');
 expect(first.run.mission).toBe('landing');
 expect(first.run.method).toBe('classical');
 expect(first.run.outcome).toBe('success');
 expect(first.run.frames).toBeGreaterThan(100);
 expect(first.run.duration).toBeGreaterThan(10);
 expect(first.start.alt).toBeGreaterThan(100);
 expect(first.start.alt).toBeLessThan(400);
 expect(first.end.alt).toBeLessThan(1);
 expect(Math.abs(first.end.x-first.lz.x)).toBeLessThan(2);
 expect(Math.abs(first.end.z-first.lz.z)).toBeLessThan(2);
 expect(first.stage).toBe(false);
 expect(first.phases).toContain('TOUCHDOWN');
 expect(first.calls).toBeGreaterThan(50);
 expect(first.pads.launch).toBe('CircleGeometry');expect(first.pads.launch).toBe(first.pads.landing);expect(first.pads.launchRadius).toBe(first.pads.landingRadius);expect(first.pads.launchChildren).toBe(first.pads.landingChildren);expect(first.pads.towerDistance).toBeGreaterThan(first.pads.launchRadius+10);
 const canvas=page.locator('#stage canvas'),box=(await canvas.boundingBox())!;
 const beforeDrag=await page.evaluate(()=>(window as any).__sim.camera.position.toArray());
 await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.down();
 await page.mouse.move(box.x+box.width/2+100,box.y+box.height/2+50,{steps:5});await page.mouse.up();
 await page.evaluate(()=>(window as any).__sim.draw(.016));
 const afterDrag=await page.evaluate(()=>(window as any).__sim.camera.position.toArray());
 expect(Math.hypot(...afterDrag.map((x:number,i:number)=>x-beforeDrag[i]))).toBeGreaterThan(1);
 for(const rate of ['4x','5x']){
  await page.getByRole('button',{name:rate,exact:true}).click();await expect(page.getByRole('button',{name:rate,exact:true})).toHaveClass('on');
  const [elapsed,advanced]=await page.evaluate(async()=>{const s=(window as any).__sim;s.seek(0);s.setPlaying(true);(window as any).__manual=false;const frame=()=>new Promise<number>(r=>requestAnimationFrame(r));const start=await frame(),t=s.t;const end=await frame(),delta=s.t-t;s.setPlaying(false);(window as any).__manual=true;return [(end-start)/1000,delta];});
  expect(advanced/elapsed).toBeGreaterThan(Number.parseInt(rate)-.5);expect(advanced/elapsed).toBeLessThan(Number.parseInt(rate)+.5);
 }
 await page.selectOption('#mMission','takeoff');
 await page.click('#mRun');
 await page.waitForFunction(()=> (window as any).__sim.run.mission==='takeoff',null,{timeout:60000});
 const second=await page.evaluate(()=>{const s=(window as any).__sim;s.setPlaying(false);return {mission:s.run.mission,outcome:s.run.outcome,end:s.end,last:s.telemetry.frames.at(-1).position[2],phases:s.phases.map((p:any)=>p.s)};});
 expect(second.mission).toBe('takeoff');
 expect(second.end).not.toBe(first.run.duration);
 expect(second.last).toBeGreaterThan(1000);
 expect(second.phases).toContain('LIFTOFF');
 expect(errors).toEqual([]);
});
test('loads real telemetry, renders canvas, plays and scrubs',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 // Use the exact simulation the app boots with, so the expected altitude comes
 // from this page's response instead of an archived run that may use an older
 // configuration.
 const booted=page.waitForResponse(r=>r.url().includes('/api/simulate')&&r.request().method()==='POST');
 await page.goto('/lab/');
 const telemetry=await (await booted).json();
 const startAltitude=Math.max(0,telemetry.frames[0].clearance??telemetry.frames[0].position[2]-telemetry.rocket_length/2).toFixed(1);await expect(page.getByTestId('altitude')).toHaveText(`${startAltitude}m`);
 await expect(page.locator('canvas')).toBeVisible();
 await expect(page.getByRole('button',{name:'Pause playback',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Pause playback',exact:true}).click();
 await expect(page.getByRole('button',{name:'Play playback',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Play playback',exact:true}).click();
 await expect(page.getByRole('button',{name:'Pause playback',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Pause playback',exact:true}).click();
 await page.getByRole('slider',{name:'Playback position'}).fill('5');
 await expect(page.getByTestId('altitude')).not.toHaveText(`${startAltitude}m`);
 await page.getByRole('button',{name:'Training',exact:true}).first().click();await expect(page.getByText('TRAINING OBSERVATORY')).toBeVisible();
 expect(errors).toEqual([]);
});
test('mid-flight retarget is applied and recorded',async({page})=>{
 await page.goto('/lab/');
 await page.getByRole('slider',{name:'Playback position'}).fill('3');
 await page.getByLabel('Retarget X').fill('95');
 await page.getByLabel('Retarget Y').fill('55');
 await page.getByRole('button',{name:/Retarget at T\+/}).click();
 const flag=page.locator('.retarget-flag');
 await expect(flag).toContainText('RETARGET T+3.');
 await expect(flag).toContainText('95, 55');
 await expect(page.locator('.retarget-note.good')).toContainText('Last command at T+3.');
 await expect(page.locator('.retarget-note.good')).toContainText('95, 55 m');
});
test('mobile interface has no horizontal overflow',async({page})=>{await page.setViewportSize({width:390,height:844});await page.goto('/lab/');await expect(page.getByTestId('altitude')).toBeVisible();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);});
