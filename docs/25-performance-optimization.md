# PC responsiveness and performance — 21 October 2026

The long campaign was gracefully stopped at **2,098,848 aggregate environment steps**. Saved models, optimizer state, normalization, logs and evidence remain on disk. Training does not restart when the dashboard opens. The campaign is stopped, not qualified or complete.

## Measured changes

| Cost | Before | Optimized |
| --- | ---: | ---: |
| Flight-page periodic API traffic | 133,919,240 bytes/minute | 25,224 bytes/minute |
| Terrain texture downloads at default quality | 8,971,337 bytes | 519,395 bytes |
| Production HTTP servers | Python API + Node/Vite preview | One Python server |
| Default playback frame budget | 60 FPS | 30 FPS |
| Default terrain texture dimensions | 2048 × 2048 | 1024 × 1024 |
| Default exhaust particles / grass instances | 96 / 600 | 48 / 200 |
| Pad perimeter draw submissions | 48 per pad | 2 per pad |

The traffic reduction is **99.98%** for the periodic flight-page payload. Before measurements requested uncompressed API responses, matching the previous API's lack of compression. After measurements explicitly request gzip and count received bytes. Frequency changed from every 3 seconds to every 60 seconds. This is a traffic calculation, not a measurement of whole-PC speed or browser FPS.

The original dashboard repeatedly fetched all historical jobs, full checkpoint configurations, results and run metadata on every page. New page-specific snapshots omit unused datasets and histories. Selected job history and configuration remain available on demand. Metadata caching is bounded to 4 MiB of source JSON and 2,048 entries; parsed Python overhead is additional. File identity participates in freshness because NTFS can retain timestamps across rapid same-size atomic replacements. A regression caught and verifies that case.

The new production server serves `/api` and built frontend assets together on `127.0.0.1:5180`. It no longer requires a Node process at runtime. Development still uses Vite. HTTP gzip is enabled. Initial dashboard load uses the recorded demo instead of running and saving a new simulation on every reload.

Default **Performance** quality caps the drawing buffer at approximately 1280 × 720 pixels, disables dynamic shadows, reduces terrain density and loads only the low rock geometry. Pad lights are instanced. Instrument/chart updates use 10 Hz while 3D playback retains its exact clock. Interpolated frames are reused through a bounded weak cache; exhaust emission timestamps remain stable. Hidden tabs stop playback and polling. Muted/paused audio releases its timer and suspends the audio context. Trajectory and road GPU resources are explicitly disposed. Higher-quality modes and 4K export remain selectable.

Future background workers use one numerical CPU thread, below-normal Windows process priority and best-effort 50% cooperative pacing. Training and evaluation yield wall time without changing simulation dt, guidance, rewards or actions. Training status writes occur every five seconds. These controls trade training throughput for responsiveness; they are not a hard OS CPU/GPU quota. The existing memory-headroom gate remains active. New campaign forms default to 1 million steps; larger budgets require selection.

## Verification and limits

- **90 Python tests, 46 frontend tests, TypeScript build and ESLint passed.**
- Live API/replay validation passed after switching to the single-server runtime. The custom-coordinate combined flight retained the same final result: 0.057250 m target offset and 0.187661 m/s touchdown speed.
- Dynamics identity remains `05d6ce3a455c4bbc0d0cb5df846fae29a755c6e21dd4684a0d7e5479bf6c22dd`; no physical integration or controller behavior was weakened for this optimization.
- A five-second idle process sample observed approximately 159 MiB combined working set for the preview/supervisor and Windows Python launchers, with zero training workers and zero Node preview processes. This excludes the browser, GPU allocations and unrelated applications. A short idle sample is not a soak test or a load measurement.
- Browser control returned “Local browser use is disabled in Work settings.” Actual WebGL frame rate, browser heap, GPU cost and final visual appearance remain unmeasured. The 30 FPS value is a tested scheduling cap, not a measured sustained rate.

Refresh the open dashboard to load the rebuilt frontend. Changing source files does not replace JavaScript already loaded in an existing tab.

Evidence: [before API measurement](evidence/2026-10-21/performance-before.json), [after API measurement](evidence/2026-10-21/performance-after.json), [idle runtime sample](evidence/2026-10-21/performance-runtime.json). Reproduce HTTP measurements with `.venv\Scripts\python.exe scripts/benchmark_dashboard.py`; it expects campaigns to be stopped. `scripts/prepare_performance_assets.py` rebuilds the small derivatives of the existing terrain textures.
