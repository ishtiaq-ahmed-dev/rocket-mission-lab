const { chromium } = require('@playwright/test');
const path = require('path');
const fs = require('fs');
const os = require('os');
const http = require('http');
const { execSync, spawn } = require('child_process');

function checkServer() {
  return new Promise((resolve) => {
    const req = http.get('http://127.0.0.1:5180', (res) => {
      resolve(res.statusCode >= 200 && res.statusCode < 500);
    });
    req.on('error', () => resolve(false));
    req.setTimeout(1000, () => {
      req.destroy();
      resolve(false);
    });
  });
}

async function ensureServerRunning() {
  if (await checkServer()) {
    console.log('✓ Detected active Rocket Mission Lab server on http://127.0.0.1:5180');
    return null;
  }

  console.log('No server detected on http://127.0.0.1:5180. Auto-launching local dev server...');
  const npmCmd = process.platform === 'win32' ? 'npm.cmd' : 'npm';
  const server = spawn(npmCmd, ['run', 'dev'], {
    cwd: __dirname,
    stdio: 'ignore',
    shell: true
  });

  for (let i = 0; i < 30; i++) {
    await new Promise((r) => setTimeout(r, 1000));
    if (await checkServer()) {
      console.log('✓ Auto-launched server is ready on http://127.0.0.1:5180');
      return server;
    }
  }
  try { server.kill(); } catch (e) { /* ignore */ }
  throw new Error('Timed out waiting for local server to become ready on http://127.0.0.1:5180');
}

async function recordFlight() {
  let serverProcess = null;
  const videoDir = path.resolve(__dirname, '../videos');
  if (!fs.existsSync(videoDir)) fs.mkdirSync(videoDir, { recursive: true });

  const tempProfileDir = path.join(os.tmpdir(), 'chromium-test-profile-' + Date.now());

  try {
    serverProcess = await ensureServerRunning();

    console.log('1. Launching Chromium with WebGL GPU acceleration & isolated profile...');
    const browser = await chromium.launch({
      headless: true,
      args: [
        `--user-data-dir=${tempProfileDir}`,
        '--no-first-run',
        '--no-default-browser-check',
        '--enable-webgl',
        '--ignore-gpu-blocklist',
        '--use-gl=angle',
        '--use-angle=d3d11',
        '--enable-gpu-rasterization',
        '--no-sandbox',
        '--disable-gpu-sandbox',
        '--disable-setuid-sandbox'
      ]
    });

    const context = await browser.newContext({
      recordVideo: {
        dir: videoDir,
        size: { width: 1920, height: 1080 }
      },
      viewport: { width: 1920, height: 1080 },
      deviceScaleFactor: 1
    });

    const page = await context.newPage();
    console.log('2. Navigating to ISS Orbital Systems Flight Lab (http://127.0.0.1:5180)...');
    await page.goto('http://127.0.0.1:5180', { waitUntil: 'networkidle', timeout: 30000 });

    console.log('3. Waiting for WebGL canvas and store initialization...');
    await page.waitForSelector('canvas', { timeout: 15000 });
    await page.waitForFunction(() => typeof window.useLab !== 'undefined', { timeout: 15000 });

    console.log('4. Loading 104-second Combined Flight (Takeoff -> Detach -> Landing)...');
    const flightInfo = await page.evaluate(async () => {
      const res = await fetch('/combined-flight.json');
      const telemetry = await res.json();
      window.useLab.getState().load(telemetry);
      // Set 2x playback speed for crisp ~52s video duration
      window.useLab.getState().set({ playing: true, speed: 2.0, time: 0 });
      return {
        duration: telemetry.run.duration,
        frames: telemetry.frames.length,
        launch: telemetry.run.flight_plan.launch,
        landing: telemetry.run.flight_plan.landing,
        separation: telemetry.run.flight_plan.separation_altitude
      };
    });
    console.log('Loaded combined flight geometry:', flightInfo);

    console.log('5. Recording playback of active flight in real-time...');
    let completed = false;
    let lastLoggedSec = -5;
    const startWall = Date.now();

    while (!completed) {
      await page.waitForTimeout(1000);
      const status = await page.evaluate(() => {
        const state = window.useLab.getState();
        const frame = state.telemetry?.frames?.find((f) => Math.abs(f.t - state.time) < 0.5) || state.telemetry?.frames?.at(-1);
        return {
          time: state.time,
          playing: state.playing,
          altitude: frame?.position?.[2] || 0,
          speed: frame?.velocity ? Math.hypot(...frame.velocity) : 0,
          phase: frame?.phase || 'unknown',
          upper_stage: !!frame?.upper_stage
        };
      });

      const wallSec = Math.floor((Date.now() - startWall) / 1000);
      if (wallSec >= lastLoggedSec + 5) {
        lastLoggedSec = wallSec;
        console.log(`[Recording t=${status.time.toFixed(1)}s / ${flightInfo.duration.toFixed(1)}s | Wall: ${wallSec}s] Alt: ${status.altitude.toFixed(1)}m, Speed: ${status.speed.toFixed(1)}m/s, Phase: ${status.phase}, Staging: ${status.upper_stage}`);
      }

      if (status.time >= flightInfo.duration - 0.5 || !status.playing) {
        console.log('Flight reached touchdown! Capturing landing rollout...');
        await page.waitForTimeout(2500); // 2.5s post-touchdown pause
        completed = true;
      }

      // Safety timeout (max 75s wall time)
      if (wallSec > 75) {
        console.log('Reached recording max duration limit.');
        completed = true;
      }
    }

    console.log('6. Finalizing video recording session...');
    await context.close();
    await browser.close();

    // Find the recorded webm video
    const files = fs.readdirSync(videoDir).filter((f) => f.endsWith('.webm'));
    if (files.length === 0) {
      console.error('No webm video produced!');
      return;
    }
    files.sort((a, b) => fs.statSync(path.join(videoDir, b)).mtimeMs - fs.statSync(path.join(videoDir, a)).mtimeMs);
    const newestWebm = path.join(videoDir, files[0]);
    const mp4Output = path.join(videoDir, 'rocket_mission_takeoff_detach_landing.mp4');

    console.log(`7. Encoding high-bitrate MP4 (${mp4Output}) via FFmpeg...`);
    try {
      execSync(`ffmpeg -y -i "${newestWebm}" -c:v libx264 -pix_fmt yuv420p -preset medium -crf 18 "${mp4Output}"`, { stdio: 'inherit' });
      console.log('MP4 encoding complete!');

      // Clean up temporary intermediate raw WebM recording to conserve disk space
      if (fs.existsSync(mp4Output) && fs.statSync(mp4Output).size > 1000) {
        console.log('Cleaning up intermediate raw WebM recording...');
        try { fs.unlinkSync(newestWebm); } catch (e) { /* ignore */ }
      }
    } catch (err) {
      console.error('FFmpeg encoding error:', err.message);
    }

    console.log('8. Extracting milestone analysis frames for multi-phase verification...');
    try {
      // 1. Takeoff frame (~3-4s in video, liftoff from TAKEOFF PAD 01)
      execSync(`ffmpeg -y -ss 00:00:04 -i "${mp4Output}" -vframes 1 "${path.join(videoDir, 'analysis_1_takeoff.png')}"`, { stdio: 'ignore' });
      // 2. Ascent frame (~12s in video, climb through atmosphere)
      execSync(`ffmpeg -y -ss 00:00:12 -i "${mp4Output}" -vframes 1 "${path.join(videoDir, 'analysis_2_ascent.png')}"`, { stdio: 'ignore' });
      // 3. Staging/Detach frame (~18s in video, stage separation at 600m)
      execSync(`ffmpeg -y -ss 00:00:18 -i "${mp4Output}" -vframes 1 "${path.join(videoDir, 'analysis_3_detach.png')}"`, { stdio: 'ignore' });
      // 4. Descent/Grid fin guidance frame (~36s in video)
      execSync(`ffmpeg -y -ss 00:00:36 -i "${mp4Output}" -vframes 1 "${path.join(videoDir, 'analysis_4_descent.png')}"`, { stdio: 'ignore' });
      // 5. Landing burn & Touchdown frame (~50s in video, landing on LANDING PAD 01)
      execSync(`ffmpeg -y -ss 00:00:50 -i "${mp4Output}" -vframes 1 "${path.join(videoDir, 'analysis_5_touchdown.png')}"`, { stdio: 'ignore' });
      console.log('Analysis frames extracted successfully!');
    } catch (err) {
      console.error('Frame extraction error:', err.message);
    }
  } finally {
    if (serverProcess) {
      console.log('Stopping temporary local server...');
      try {
        if (process.platform === 'win32') {
          execSync(`taskkill /pid ${serverProcess.pid} /T /F`, { stdio: 'ignore' });
        } else {
          serverProcess.kill('SIGTERM');
        }
      } catch (e) {
        /* ignore */
      }
    }
    // Clean up temporary browser profile
    try {
      if (fs.existsSync(tempProfileDir)) {
        fs.rmSync(tempProfileDir, { recursive: true, force: true });
      }
    } catch (e) {
      /* ignore */
    }
  }
}

recordFlight().catch(console.error);
