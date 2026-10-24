"""Probe the offline cinematic pipeline building blocks in one Isaac boot.

Answers, with measured numbers:
1. Which RTX settings exist for fog/haze, AA/DLSS, motion blur, tone mapping,
   path tracing samples, denoising, shadows, AO.
2. Per-frame cost of render product + rgb annotator + orchestrator.step at
   1920x1080 and 3840x2160 (the offline replay render loop).
3. Whether an ffmpeg NVENC pipe accepts 60 real rendered frames and produces a
   valid, correctly-timestamped MP4 (cv2-decoded frame count + fps + bitrate).
"""
import subprocess,sys,time,json
from pathlib import Path
import numpy as np
from isaacsim import SimulationApp

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/probes/cinematic-pipeline';OUT.mkdir(parents=True,exist_ok=True)
app=SimulationApp({'headless':True,'width':1280,'height':720,
    'extra_args':['--enable','omni.replicator.core',
        '--ext-folder','D:/AppInstalled/NVIDIA/IsaacSim/6.2.0/extscache',
        '--ext-folder','D:/AppInstalled/NVIDIA/IsaacSim/6.2.0/extsDeprecated'],
    'experience':str(ROOT/'config/isaac-visual.kit')})
import carb
import omni.replicator.core as rep
import omni.usd
from pxr import Gf,UsdGeom,UsdLux

report={}
try:
    stage=omni.usd.get_context().get_stage()
    # A small scene: ground + lit sphere so frames exercise shading and AA.
    ground=UsdGeom.Cylinder.Define(stage,'/World/Ground')
    ground.CreateAxisAttr('Z');ground.CreateRadiusAttr(4000.);ground.CreateHeightAttr(.1)
    ball=UsdGeom.Sphere.Define(stage,'/World/Ball');ball.CreateRadiusAttr(60.)
    ball.AddTranslateOp().Set(Gf.Vec3d(0,0,120.))
    light=UsdLux.DistantLight.Define(stage,'/World/Sun');light.CreateIntensityAttr(2000.)
    dome=UsdLux.DomeLight.Define(stage,'/World/Sky');dome.CreateIntensityAttr(800.)

    settings=carb.settings.get_settings()
    keywords=('fog','aa/','dlss','antialiasing','motionblur','motion_blur','tonemap',
              'exposure','pathtracing','denois','ambientoccl','directlighting','shadows','samplecount',
              'transient/fog','hydra/materialChannel','post/colcorrection','raytracing')
    found={}
    candidates=[
        '/rtx/post/aa/op','/rtx/post/aa/taaa/staticOffset','/rtx/post/dlss/execMode','/rtx/post/dlss/preferredEngine',
        '/rtx/post/dlss/execUseAutoSharpness','/rtx/post/motionblur/enabled','/rtx/post/motionblur/op',
        '/rtx/post/motionblur/maxMotionVectors','/rtx/post/tonemap/op','/rtx/post/tonemap/whitepoint',
        '/rtx/post/exposure/exposureCompensation','/rtx/post/exposure/filmIso','/rtx/post/exposure/ev',
        '/rtx/post/exposure/enableAutoExposure','/rtx/sceneDb/fog/fogEnabled','/rtx/transient/fog/fogAmount',
        '/rtx/transient/fog/fogHeightFalloff','/rtx/transient/fog/fogColor','/rtx/transient/fog/fogGroundOffset',
        '/rtx/transient/fog/fogStartDist','/rtx/transient/fog/fogEndDist','/rtx/transient/fog/fogYawStart','/rtx/transient/fog/fogColorDensity',
        '/rtx/pathtracing/spp','/rtx/pathtracing/totalSpp','/rtx/pathtracing/maxClaudeSamples','/rtx/pathtracing/maxBounces',
        '/rtx/pathtracing/maxSpecularTransmitsBounces','/rtx/pathtracing/maxDiffuseBounces','/rtx/pathtracing/furnaceTest',
        '/rtx/pathtracing/sceneScale','/rtx/pathtracing/antiAliasMethod','/rtx/pathDenoiser/enabled',
        '/rtx/denoiser/blend','/rtx/ambientOcclusion/enabled','/rtx/ambientOcclusion/rayCount','/rtx/ambientOcclusion/aggregateMode',
        '/rtx/directLighting/enabled','/rtx/directLighting/sampledLighting','/rtx/directLighting/shadows','/rtx/directLighting/shadowSampleCount',
        '/rtx/directLighting/caustics','/rtx/indirectDiffuse/enabled','/rtx/indirectDiffuse/groundTruthMode','/rtx/indirectDiffuse/sampleCount',
        '/rtx/indirectDiffuse/bounceCount','/rtx/indirectDiffuse/accumulationMode','/rtx/reflections/enabled','/rtx/reflections/halfRes',
        '/rtx/reflections/maxRoughness','/rtx/reflections/maxTraversalIterations','/rtx/transitions/enabled','/rtx/fog/enabled',
        '/rtx/fog/fogAmount','/rtx/fog/fogColor','/rtx/fog/fogHeightFalloff','/rtx/fog/fogStartDist','/rtx/fog/fogEndDist',
        '/rtx/post/colorcorrection/op','/rtx/post/colorcorrection/gamma','/rtx/post/rescale/enable','/rtx/post/cameraLagOp',
        '/renderer/serialization/version','/renderer/active/gpuCount','/renderer/multiGpu/enabled','/renderer/active/gpuIterations',
        '/persistent/renderer/rtx/realtime/aaMode','/persistent/app/viewport/rtx/realtime/dlssMode',
        'rtx-post-aa-op','/rtx/realtime/aaMode','/rtx/realtime/dlssMode','/rtx/realtime/motionBlur','/rtx/realtime/dlssMode',
        '/rtx/post/taa/staticOffset','/rtx/post/aa/tdaa/op','/rtx/post/aa/taaa/op','/rtx/post/aa/taaa/sharpness',
        '/rtx/post/histogram/exposureScale','/rtx/transient/resourceallocator/maxSizes','/rtx/newDenoiser/enabled',
        '/rtx/post/volumetrictransmittance/enabled','/rtx/post/volumetrictransmittance/maxHistoryClamp',
        '/rtx/eyeAdaptation/exposure','/rtx/eyeAdaptation/enabled',
    ]
    for path in candidates:
        try:value=settings.get(path)
        except BaseException:value='<err>'
        if value is not None:found[path]=value
    # Also ask the settings schema for a few wildcard enumerations.
    report['settings_matched']={k:str(v)[:120] for k,v in sorted(found.items())}
    print(f"PROBE: matched {len(found)} settings leaves",flush=True)

    from isaacsim.core.utils.viewports import set_camera_view
    set_camera_view(eye=np.array([260.,-340.,90.]),target=np.array([0.,0.,60.]))

    product=rep.create.render_product('/OmniverseKit_Persp',(1920,1080))
    annotator=rep.AnnotatorRegistry.get_annotator('rgb');annotator.attach(product)

    def render_once(tag,warm=False):
        t0=time.perf_counter()
        rep.orchestrator.step(rt_subframes=8,pause_timeline=True)
        data=annotator.get_data()
        ms=(time.perf_counter()-t0)*1000.
        if not warm:
            print(f'PROBE render {tag}: {ms:.1f} ms dtype={data.dtype} shape={data.shape} mean={float(np.asarray(data,dtype=float).mean()):.1f}',flush=True)
        return ms,np.asarray(data)
    render_once('warm',warm=True)
    timings={}
    for tag,(w,h) in (('1080p',(1920,1080)),):
        samples=[render_once(tag) for _ in range(12)][2:]
        timings[tag]=float(np.median([s[0] for s in samples]))
    report['render_ms_1080p']=timings['1080p']

    # ffmpeg NVENC pipe with 60 genuine frames (orbit the camera slightly).
    video=OUT/'nvenc-test.mp4'
    cmd=['ffmpeg','-hide_banner','-loglevel','error','-y',
         '-f','rawvideo','-pix_fmt','rgb24','-s','1920x1080','-r','60','-i','pipe:0',
         '-c:v','h264_nvenc','-preset','p6','-tune','hq','-rc','vbr','-cq','19','-b:v','0',
         '-pix_fmt','yuv420p','-movflags','+faststart',str(video)]
    print('PROBE: launching ffmpeg',flush=True)
    ffmpeg=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    for frame in range(60):
        _,data=render_once(f'pipe{frame}',warm=frame==0)
        if data.dtype!=np.uint8:data=np.clip(data,0,255).astype(np.uint8)
        ffmpeg.stdin.write(np.ascontiguousarray(data).tobytes())
    ffmpeg.stdin.close();stderr=ffmpeg.stderr.read().decode(errors='replace');code=ffmpeg.wait()
    print(f'PROBE: ffmpeg exit={code} stderr={stderr[:400]}',flush=True)
    report['nvenc_exit']=code;report['nvenc_stderr']=stderr[:400]
    if code==0:
        import cv2
        cap=cv2.VideoCapture(str(video));n=0
        while cap.read() is not None and cap.read()[0]:n+=1
        cap.release()
        probe=subprocess.run(['ffprobe','-v','error','-show_entries',
            'format=duration,bit_rate:stream=avg_frame_rate,nb_frames',
            '-of','json',str(video)],capture_output=True,text=True)
        report['nvenc_output']=json.loads(probe.stdout)
        report['nvenc_frames_decoded']=n
    annotator.detach();product.destroy()

    # Second resolution probe without annotator copy cost breakdown — 4K timing.
    product4=rep.create.render_product('/OmniverseKit_Persp',(3840,2160))
    ann4=rep.AnnotatorRegistry.get_annotator('rgb');ann4.attach(product4)
    def render4():
        t0=time.perf_counter();rep.orchestrator.step(rt_subframes=8,pause_timeline=True)
        data=ann4.get_data();return (time.perf_counter()-t0)*1000.,data
    render4();ms=[render4()[0] for _ in range(10)]
    report['render_ms_2160p']=float(np.median(ms[2:]))
    print(f"PROBE: 2160p median {report['render_ms_2160p']:.1f} ms",flush=True)
    ann4.detach();product4.destroy()
    report['status']='passed'
except BaseException as exc:
    import traceback;report['status']='failed';report['error']=traceback.format_exc();print(report['error'],flush=True)
finally:
    (OUT/'report.json').write_text(json.dumps(report,indent=2))
    print('PROBE REPORT:',json.dumps({k:v for k,v in report.items() if k!='settings_matched'},indent=1)[:1500],flush=True)
    app.close()
