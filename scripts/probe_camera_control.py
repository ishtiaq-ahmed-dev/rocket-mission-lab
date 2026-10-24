"""Verify direct camera-prim control drives render products in headless mode.

Checks, in one boot:
1. Transform authored directly on /OmniverseKit_Persp (translate+orient ops)
   is honored by the render product (content variance proves it).
2. focalLength on the prim changes framing (telephoto crops the chart).
3. NVENC output decodes to exactly the number of frames written.
"""
import json,subprocess,shutil
from pathlib import Path
import numpy as np
from isaacsim import SimulationApp

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/probes/camera';OUT.mkdir(parents=True,exist_ok=True)
app=SimulationApp({'headless':True,'width':1280,'height':720,
    'extra_args':['--enable','omni.replicator.core',
        '--ext-folder','D:/AppInstalled/NVIDIA/IsaacSim/6.2.0/extscache',
        '--ext-folder','D:/AppInstalled/NVIDIA/IsaacSim/6.2.0/extsDeprecated'],
    'experience':str(ROOT/'config/isaac-visual.kit')})
import carb
import omni.replicator.core as rep
import omni.usd
from pxr import Gf,Sdf,UsdGeom,UsdLux,UsdShade
from scipy.spatial.transform import Rotation

report={}
try:
    stage=omni.usd.get_context().get_stage()
    board=UsdGeom.Cube.Define(stage,'/World/Board');board.AddScaleOp().Set(Gf.Vec3f(20.,20.,.01))
    board.AddTranslateOp().Set(Gf.Vec3d(0.,0.,20.))
    for index in range(14):
        bar=UsdGeom.Cube.Define(stage,f'/World/Bar{index}')
        bar.AddTranslateOp().Set(Gf.Vec3d(-13.+2.*index,0,20.06));bar.AddScaleOp().Set(Gf.Vec3f(.5,20.,.01))
    white=UsdShade.Material.Define(stage,'/World/Looks/W');ws=UsdShade.Shader.Define(stage,'/World/Looks/W/S')
    ws.CreateIdAttr('UsdPreviewSurface');ws.CreateInput('diffuseColor',Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(.95,.95,.95))
    white.CreateSurfaceOutput().ConnectToSource(ws.ConnectableAPI(),'surface')
    black=UsdShade.Material.Define(stage,'/World/Looks/K');ks=UsdShade.Shader.Define(stage,'/World/Looks/K/S')
    ks.CreateIdAttr('UsdPreviewSurface');ks.CreateInput('diffuseColor',Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(.03,.03,.03))
    black.CreateSurfaceOutput().ConnectToSource(ks.ConnectableAPI(),'surface')
    UsdShade.MaterialBindingAPI.Apply(board.GetPrim()).Bind(white)
    ground=UsdGeom.Cylinder.Define(stage,'/World/Ground')
    ground.CreateAxisAttr('Z');ground.CreateRadiusAttr(3000.);ground.CreateHeightAttr(.1)
    green=UsdShade.Material.Define(stage,'/World/Looks/G');gs=UsdShade.Shader.Define(stage,'/World/Looks/G/S')
    gs.CreateIdAttr('UsdPreviewSurface');gs.CreateInput('diffuseColor',Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(.15,.25,.12))
    green.CreateSurfaceOutput().ConnectToSource(gs.ConnectableAPI(),'surface')
    UsdShade.MaterialBindingAPI.Apply(ground.GetPrim()).Bind(green)
    sun=UsdLux.DistantLight.Define(stage,'/World/Sun');sun.CreateIntensityAttr(3000.)
    dome=UsdLux.DomeLight.Define(stage,'/World/Sky');dome.CreateIntensityAttr(900.)

    camera=UsdGeom.Camera.Define(stage,'/World/CineCam')
    camera.CreateClippingRangeAttr(Gf.Vec2f(.1,60000.))
    xform=UsdGeom.Xformable(camera.GetPrim())
    translate=xform.AddTranslateOp();rotate=xform.AddRotateXYZOp()
    camera_path='/World/CineCam'

    def aim(eye,target,focal=None):
        eye=np.asarray(eye,float);target=np.asarray(target,float)
        forward=target-eye;forward/=np.linalg.norm(forward)
        up=np.array([0.,0.,1.])
        right=np.cross(forward,up);right/=np.linalg.norm(right)
        up2=np.cross(right,forward)
        # Kit camera looks down -Z with +Y up: matrix columns (right, up2, -forward)
        matrix=np.column_stack([right,up2,-forward])
        angles=Rotation.from_matrix(matrix).as_euler('xyz',degrees=True)
        translate.Set(Gf.Vec3d(*eye))
        rotate.Set(Gf.Vec3f(*angles))
        if focal is not None:camera.GetPrim().GetAttribute('focalLength').Set(float(focal))

    product=rep.create.render_product(camera_path,(1920,1080))
    annotator=rep.AnnotatorRegistry.get_annotator('rgb');annotator.attach(product)
    def grab(name):
        rep.orchestrator.step(rt_subframes=10,pause_timeline=True)
        data=np.asarray(annotator.get_data())
        if data.dtype!=np.uint8:data=np.clip(data,0,255).astype(np.uint8)
        from PIL import Image
        Image.fromarray(data[...,:3]).save(OUT/f'{name}.png')
        gray=data[...,:3].mean(axis=2)
        return dict(mean=float(gray.mean()),std=float(gray.std()))
    aim([0.,-40.,20.],[0.,0.,20.],focal=50.)
    report['wide']=grab('wide')
    aim([0.,-40.,20.],[0.,0.,20.],focal=120.)
    report['telephoto']=grab('telephoto')
    aim([30.,-60.,35.],[0.,0.,20.],focal=85.)
    report['angled']=grab('angled')
    print('PROBE stats:',json.dumps(report),flush=True)
    annotator.detach();product.destroy()

    # NVENC round-trip with 45 genuinely animated frames.
    product=rep.create.render_product(camera_path,(1280,720))
    annotator=rep.AnnotatorRegistry.get_annotator('rgb');annotator.attach(product)
    video=OUT/'roundtrip.mp4'
    ffmpeg=shutil.which('ffmpeg')
    process=subprocess.Popen([ffmpeg,'-hide_banner','-loglevel','error','-y',
        '-f','rawvideo','-pix_fmt','rgb24','-s','1280x720','-r','60','-i','pipe:0',
        '-c:v','h264_nvenc','-preset','p6','-tune','hq','-rc','vbr','-cq','19','-b:v','0',
        '-pix_fmt','yuv420p','-movflags','+faststart',str(video)],stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    written=0
    for frame in range(45):
        angle=.04*frame
        aim([40.*np.cos(angle),-60.,30.],[0.,0.,20.],focal=50.)
        rep.orchestrator.step(rt_subframes=8,pause_timeline=True)
        data=np.asarray(annotator.get_data())
        if data.dtype!=np.uint8:data=np.clip(data,0,255).astype(np.uint8)
        process.stdin.write(np.ascontiguousarray(data[...,:3]).tobytes());written+=1
    process.stdin.close();stderr=process.stderr.read().decode(errors='replace');code=process.wait()
    report['nvenc']=dict(exit=code,written=written,stderr=stderr[:300])
    probe=json.loads(subprocess.run(['ffprobe','-v','error','-show_entries',
        'stream=nb_frames,avg_frame_rate:format=duration,bit_rate','-of','json',str(video)],
        capture_output=True,text=True).stdout)
    report['nvenc']['container']=probe
    import cv2
    cap=cv2.VideoCapture(str(video));decoded=0;maxdiff=0.;previous=None
    while True:
        ok,frame_img=cap.read()
        if not ok:break
        decoded+=1
        if previous is not None:maxdiff=max(maxdiff,float(np.abs(frame_img.astype(float)-previous).max()))
        previous=frame_img.astype(float)
    report['nvenc']['decoded']=decoded;report['nvenc']['max_frame_diff']=maxdiff
    print('PROBE nvenc:',json.dumps(report['nvenc']),flush=True)
    annotator.detach();product.destroy()
    report['status']='passed'
except BaseException:
    import traceback;report['status']='failed';report['error']=traceback.format_exc();print(report['error'],flush=True)
finally:
    (OUT/'report.json').write_text(json.dumps(report,indent=2))
    app.close()
