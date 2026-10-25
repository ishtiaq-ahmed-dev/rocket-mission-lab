const { chromium } = require('@playwright/test');
const path = require('path');
const os = require('os');

async function main() {
  console.log('1. Launching headless Chromium to test Isaac Sim Web UI...');
  const tempProfileDir = path.join(os.tmpdir(), 'chromium-isaac-profile-' + Date.now());
  const browser = await chromium.launch({
    headless: true,
    args: [
      `--user-data-dir=${tempProfileDir}`,
      '--no-first-run',
      '--no-default-browser-check',
      '--no-sandbox',
      '--disable-gpu-sandbox',
      '--disable-setuid-sandbox',
      '--ignore-gpu-blocklist',
      '--enable-webgl',
      '--use-gl=angle',
      '--use-angle=d3d11'
    ]
  });
  const context = await browser.newContext({ viewport: { width: 1480, height: 960 } });
  const page = await context.newPage();

  console.log('2. Navigating to http://127.0.0.1:5180...');
  await page.goto('http://127.0.0.1:5180', { waitUntil: 'networkidle', timeout: 15000 });

  console.log('3. Waiting for Isaac Sim UI components...');
  await page.waitForSelector('.isaac-super-deck', { timeout: 10000 });

  const screenshotPath = path.resolve(__dirname, '../data/isaac/ui_isaac_deck.png');
  await page.screenshot({ path: screenshotPath, fullPage: true });
  console.log(`4. Saved UI screenshot to ${screenshotPath}`);

  // Also test clicking the RTX Camera Previews tab
  console.log('5. Clicking RTX Camera Previews tab...');
  await page.click('button:has-text("RTX Camera Previews")');
  await page.waitForTimeout(1000);
  const screenshotPreviews = path.resolve(__dirname, '../data/isaac/ui_isaac_previews.png');
  await page.screenshot({ path: screenshotPreviews, fullPage: true });
  console.log(`6. Saved Previews tab screenshot to ${screenshotPreviews}`);

  // Also test clicking 2D Range Radar tab
  console.log('7. Clicking 2D Range Radar tab...');
  await page.click('button:has-text("2D Range Radar")');
  await page.waitForTimeout(1000);
  const screenshotRadar = path.resolve(__dirname, '../data/isaac/ui_isaac_radar.png');
  await page.screenshot({ path: screenshotRadar, fullPage: true });
  console.log(`8. Saved Radar tab screenshot to ${screenshotRadar}`);

  await browser.close();
  console.log('Done testing!');
}

main().catch(err => {
  console.error('Test error:', err);
  process.exit(1);
});
