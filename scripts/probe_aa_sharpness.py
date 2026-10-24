"""Empirically pick the anti-aliasing mode for offline renders.

Renders a resolution test chart (thin line grid) through the same render
product + annotator path the cinematic renderer uses, for every plausible
/rtx/post/aa/op value and DLSS exec mode, and writes PNGs for measurement.
"""
import json
from pathlib import Path
import numpy as np
from isaacsim import SimulationApp

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/probes/aa';OUT.mkdir(parents=True,exist_ok=True)
app=SimulationApp({'headless':True,'width':1280,'height':720,
    'extra_args':['--enable','omni.replicator.core',
        '--ext-folder','D:/AppInstalled/NVIDIA/IsaacSim/6.2.0/extscache',
        '--ext-folder','D:/AppInstalled/NVIDIA/IsaacSim/6.2.0/extsDeprecated'],
    'experience':str(ROOT/'config/isaac-visual.kit')})
import carb
import omni.replicator.core as rep
import omni.usd
from pxr import Gf,Sdf,UsdGeom,UsdLux,UsdShade

report={}
try:
    stage=omni.usd.get_context().get_stage()
    # Chart: alternating 0.5 m black/white stripes on a 40x40 m board.
    board=UsdGeom.Cube.Define(stage,'/World/Board');board.AddScaleOp().Set(Gf.Vec3f(20.,20.,.01))
    board.AddTranslateOp().Set(Gf.Vec3d(0.,0.,20.))
    stripes=[]
    for index in range(14):
        bar=UsdGeom.Cube.Define(stage,f'/World/Bar{index}')
        bar.AddTranslateOp().Set(Gf.Vec3d(-13.+2.*index,0,20.06));bar.AddScaleOp().Set(Gf.Vec3f(.5,20.,.01))
        stripes.append(bar)
    white=UsdShade.Material.Define(stage,'/World/Looks/W');ws=UsdShade.Shader.Define(stage,'/World/Looks/W/S')
    ws.CreateIdAttr('UsdPreviewSurface');ws.CreateInput('diffuseColor',Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(.95,.95,.95))
    white.CreateSurfaceOutput().ConnectToSource(ws.ConnectableAPI(),'surface')
    black=UsdShade.Material.Define(stage,'/World/Looks/K');ks=UsdShade.Shader.Define(stage,'/World/Looks/K/S')
    ks.CreateIdAttr('UsdPreviewSurface');ks.CreateInput('diffuseColor',Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(.03,.03,.03))
    black.CreateSurfaceOutput().ConnectToSource(ks.ConnectableAPI(),'surface')
    UsdShade.MaterialBindingAPI.Apply(board.GetPrim()).Bind(white)
    for bar in stripes:UsdShade.MaterialBindingAPI.Apply(bar.GetPrim()).Bind(black)
    sun=UsdLux.DistantLight.Define(stage,'/World/Sun');sun.CreateIntensityAttr(3000.)
    dome=UsdLux.DomeLight.Define(stage,'/World/Sky');dome.CreateIntensityAttr(900.)

    from isaacsim.core.utils.viewports import set_camera_view
    set_camera_view(eye=np.array([0.,-40.,20.]),target=np.array([0.,0.,20.]))
    settings=carb.settings.get_settings()
    product=rep.create.render_product('/OmniverseKit_Persp',(1920,1080))
    annotator=rep.AnnotatorRegistry.get_annotator('rgb');annotator.attach(product)

    def grab(name):
        rep.orchestrator.step(rt_subframes=10,pause_timeline=True)
        data=np.asarray(annotator.get_data())
        if data.dtype!=np.uint8:data=np.clip(data,0,255).astype(np.uint8)
        from PIL import Image
        Image.fromarray(data[...,:3]).save(OUT/f'{name}.png')

    report['cases']=[]
    for op in (0,1,2,3,4,5):
        settings.set('/rtx/post/aa/op',op)
        for mode in ((None,) if op!=3 else (0,1,2,3)):
            if mode is not None:settings.set('/rtx/post/dlss/execMode',mode)
            name=f'op{op}' if mode is None else f'op{op}-mode{mode}'
            grab(name)
            report['cases'].append(dict(name=name,op=op,mode=mode))
            print('PROBE grabbed',name,flush=True)
    annotator.detach();product.destroy()
    report['status']='passed'
except BaseException:
    import traceback;report['status']='failed';report['error']=traceback.format_exc();print(report['error'],flush=True)
finally:
    (OUT/'report.json').write_text(json.dumps(report,indent=2))
    app.close()
