"""Render one face-on striped board through the quat-aimed CineCam.

The board plane is perpendicular to the view axis: stripes must appear
centered and large if the camera aim is exact. This is the end-to-end proof
for the OfflineRenderer camera path (op order + quaternion encoding).
"""
import json
from pathlib import Path
import numpy as np
from isaacsim import SimulationApp

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/probes/camera';OUT.mkdir(parents=True,exist_ok=True)
app=SimulationApp({'headless':True,'width':640,'height':360,
    'extra_args':['--enable','omni.replicator.core',
        '--ext-folder','D:/AppInstalled/NVIDIA/IsaacSim/6.2.0/extscache',
        '--ext-folder','D:/AppInstalled/NVIDIA/IsaacSim/6.2.0/extsDeprecated'],
    'experience':str(ROOT/'config/isaac-visual.kit')})
import omni.replicator.core as rep
import omni.usd
from pxr import Gf,Sdf,UsdGeom,UsdLux,UsdShade
from scipy.spatial.transform import Rotation

report={}
try:
    stage=omni.usd.get_context().get_stage()
    board=UsdGeom.Cube.Define(stage,'/World/Board');board.AddScaleOp().Set(Gf.Vec3f(16.,.1,9.))
    board.AddTranslateOp().Set(Gf.Vec3d(0.,0.,9.))
    for index in range(8):
        bar=UsdGeom.Cube.Define(stage,f'/World/Bar{index}')
        bar.AddTranslateOp().Set(Gf.Vec3d(-7.+2.*index,0,9.));bar.AddScaleOp().Set(Gf.Vec3f(.6,.2,9.))
    white=UsdShade.Material.Define(stage,'/World/Looks/W');ws=UsdShade.Shader.Define(stage,'/World/Looks/W/S')
    ws.CreateIdAttr('UsdPreviewSurface');ws.CreateInput('diffuseColor',Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(.95,.95,.95))
    white.CreateSurfaceOutput().ConnectToSource(ws.ConnectableAPI(),'surface')
    black=UsdShade.Material.Define(stage,'/World/Looks/K');ks=UsdShade.Shader.Define(stage,'/World/Looks/K/S')
    ks.CreateIdAttr('UsdPreviewSurface');ks.CreateInput('diffuseColor',Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(.02,.02,.02))
    black.CreateSurfaceOutput().ConnectToSource(ks.ConnectableAPI(),'surface')
    UsdShade.MaterialBindingAPI.Apply(board.GetPrim()).Bind(white)
    for bar_ in stage.GetPrimAtPath('/World').GetChildren():
        if bar_.GetName().startswith('Bar'):UsdShade.MaterialBindingAPI.Apply(bar_).Bind(black)
    sun=UsdLux.DistantLight.Define(stage,'/World/Sun');sun.CreateIntensityAttr(2500.)
    dome=UsdLux.DomeLight.Define(stage,'/World/Sky');dome.CreateIntensityAttr(700.)

    camera=UsdGeom.Camera.Define(stage,'/World/CinematicCamera')
    camera.CreateClippingRangeAttr(Gf.Vec2f(.05,120000.))
    xf=UsdGeom.Xformable(camera.GetPrim())
    cam_t=xf.AddTranslateOp();cam_o=xf.AddOrientOp()

    def aim(eye,target,focal):
        eye=np.asarray(eye,float);target=np.asarray(target,float)
        forward=target-eye;forward/=np.linalg.norm(forward)
        up=np.array([0.,0.,1.])
        right=np.cross(forward,up);right/=np.linalg.norm(right)
        up2=np.cross(right,forward)
        matrix=np.column_stack([right,up2,-forward])
        quat=Rotation.from_matrix(matrix).as_quat()
        cam_t.Set(Gf.Vec3d(*eye));cam_o.Set(Gf.Quatf(float(quat[3]),Gf.Vec3f(*quat[:3])))
        camera.GetPrim().GetAttribute('focalLength').Set(float(focal))

    product=rep.create.render_product('/World/CinematicCamera',(960,540))
    annotator=rep.AnnotatorRegistry.get_annotator('rgb');annotator.attach(product)
    import omni.kit.app
    def grab():
        rep.orchestrator.step(rt_subframes=8,pause_timeline=True)
        data=np.asarray(annotator.get_data())
        if data.dtype!=np.uint8:data=np.clip(data,0,255).astype(np.uint8)
        return data
    import omni.kit.app
    def report_camera(tag):
        m=UsdGeom.Xformable(camera.GetPrim()).GetLocalTransformation()
        m4=np.array(m)
        # Gf row-major: rotation = m4[:3,:3], translation = m4[3,:3]
        rot=m4[:3,:3];tr=m4[3,:3]
        view=-rot[:,2]
        print(f'PROBE {tag}: pos=({tr[0]:.1f},{tr[1]:.1f},{tr[2]:.1f}) view=({view[0]:.3f},{view[1]:.3f},{view[2]:.3f})',flush=True)
    def raw_attrs(tag):
        p=camera.GetPrim()
        t=p.GetAttribute('xformOp:translate').Get()
        o=p.GetAttribute('xformOp:orient').Get()
        print(f'PROBE raw {tag}: translate={t} orient={o}',flush=True)
    xf2=UsdGeom.Xformable(camera.GetPrim())
    xf2.ClearXformOpOrder()
    cam_t2=xf2.AddTranslateOp();cam_r2=xf2.AddRotateXYZOp()
    def aim_matrix(eye,target,focal):
        eye=np.asarray(eye,float);target=np.asarray(target,float)
        forward=target-eye;forward/=np.linalg.norm(forward)
        up=np.array([0.,0.,1.])
        right=np.cross(forward,up);right/=np.linalg.norm(right)
        up2=np.cross(right,forward)
        matrix=np.column_stack([right,up2,-forward])
        angles=Rotation.from_matrix(matrix).as_euler('XYZ',degrees=True)
        cam_t2.Set(Gf.Vec3d(*eye));cam_r2.Set(Gf.Vec3f(*angles))
        camera.GetPrim().GetAttribute('focalLength').Set(float(focal))

    for tag,eye,tgt in (('M-at-board',[0.,-30.,9.],[0.,0.,9.]),('M-away',[0.,-30.,9.],[100.,-30.,9.]),('M-back',[0.,-30.,9.],[0.,0.,9.])):
        aim_matrix(eye,tgt,50.)
        data=grab()
        gray=data[...,:3].mean(axis=2)
        report_camera(tag)
        print(f'PROBE {tag}: mean={gray.mean():.1f} std={gray.std():.1f}',flush=True)
        if tag=='M-at-board':
            from PIL import Image
            Image.fromarray(data[...,:3]).save(OUT/'quat-aim-board.png')
    for tag,eye,tgt in (('M-at-board',[0.,-30.,9.],[0.,0.,9.]),('M-away',[0.,-30.,9.],[100.,-30.,9.])):
        aim_matrix(eye,tgt,50.)
        data=grab()
        gray=data[...,:3].mean(axis=2)
        report_camera(tag)
        print(f'PROBE {tag}: mean={gray.mean():.1f} std={gray.std():.1f}',flush=True)
        if gray.std()>40:
            from PIL import Image
            Image.fromarray(data[...,:3]).save(OUT/f'{tag}.png')
    if data.dtype!=np.uint8:data=np.clip(data,0,255).astype(np.uint8)
    from PIL import Image
    Image.fromarray(data[...,:3]).save(OUT/'quat-aim-board.png')
    gray=data[...,:3].mean(axis=2)
    report['std']=float(gray.std());report['mean']=float(gray.mean())
    annotator.detach();product.destroy()
    report['status']='passed'
except BaseException:
    import traceback;report['status']='failed';report['error']=traceback.format_exc();print(report['error'],flush=True)
finally:
    (OUT/'quat-aim-report.json').write_text(json.dumps(report,indent=2))
    app.close()
