import {test,expect} from '@playwright/test';
test('loads real telemetry, renders canvas, plays and scrubs',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 // Use the exact simulation the app boots with, so the expected altitude comes
 // from this page's response instead of an archived run that may use an older
 // configuration.
 const booted=page.waitForResponse(r=>r.url().includes('/api/simulate')&&r.request().method()==='POST');
 await page.goto('/');
 const telemetry=await (await booted).json();
 const startAltitude=Math.max(0,telemetry.frames[0].clearance??telemetry.frames[0].position[2]-telemetry.rocket_length/2).toFixed(1);await expect(page.getByTestId('altitude')).toHaveText(`${startAltitude}m`);
 await expect(page.locator('canvas')).toBeVisible();await page.getByRole('button',{name:'Play playback',exact:true}).click();
 await expect(page.getByRole('button',{name:'Pause playback',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Pause playback',exact:true}).click();
 await page.getByRole('slider',{name:'Playback position'}).fill('5');
 await expect(page.getByTestId('altitude')).not.toHaveText(`${startAltitude}m`);
 await page.getByRole('button',{name:'Training',exact:true}).first().click();await expect(page.getByText('TRAINING OBSERVATORY')).toBeVisible();
 expect(errors).toEqual([]);
});
test('mid-flight retarget is applied and recorded',async({page})=>{
 await page.goto('/');
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
test('mobile interface has no horizontal overflow',async({page})=>{await page.setViewportSize({width:390,height:844});await page.goto('/');await expect(page.getByTestId('altitude')).toBeVisible();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);});
