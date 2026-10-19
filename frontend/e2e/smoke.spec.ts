import {test,expect} from '@playwright/test';
test('loads real telemetry, renders canvas, plays and scrubs',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 const all=await (await page.request.get('/api/runs')).json();
 const run=all.find((r:{mission:string;method:string;level:number;seed:number})=>r.mission==='landing'&&r.method==='classical'&&r.level===4&&r.seed===42);
 const telemetry=await (await page.request.get(`/api/runs/${run.id}/telemetry`)).json();
 await page.goto('/');await expect(page.getByTestId('altitude')).toHaveText((telemetry.frames[0].position[2]-telemetry.rocket_length/2).toFixed(1));
 await expect(page.locator('canvas')).toBeVisible();await page.getByRole('button',{name:'Play playback',exact:true}).click();
 await expect(page.getByRole('button',{name:'Pause playback',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Pause playback',exact:true}).click();
 await page.getByRole('slider',{name:'Playback position'}).fill('5');
 await expect(page.getByTestId('altitude')).not.toHaveText((telemetry.frames[0].position[2]-telemetry.rocket_length/2).toFixed(1));
 await page.getByRole('button',{name:'Training',exact:true}).first().click();await expect(page.getByText('TRAINING OBSERVATORY')).toBeVisible();
 expect(errors).toEqual([]);
});
test('mobile interface has no horizontal overflow',async({page})=>{await page.setViewportSize({width:390,height:844});await page.goto('/');await expect(page.getByTestId('altitude')).toBeVisible();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);});
