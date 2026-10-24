"""Determine the correct xformOp order for authoring a look-at camera.

Boots Isaac, builds a CineCam, sets the same aim ops used by the offline
renderer, and reads back the world transform. Verifies which op ordering
yields the camera exactly at `eye` looking at `target`.
"""
import numpy as np
from isaacsim import SimulationApp
app=SimulationApp({'headless':True,'width':640,'height':360,
    'extra_args':['--ext-folder','D:/AppInstalled/NVIDIA/IsaacSim/6.2.0/extscache',
                  '--ext-folder','D:/AppInstalled/NVIDIA/IsaacSim/6.2.0/extsDeprecated'],
    'experience':'D:/AI SIDE PROJECTS/ROCKET LANDER + LAUNCHER/config/isaac-visual.kit'})
import omni.usd
from pxr import Gf,UsdGeom,UsdLux
from scipy.spatial.transform import Rotation

stage=omni.usd.get_context().get_stage()
light=UsdLux.DistantLight.Define(stage,'/World/Sun');light.CreateIntensityAttr(2000.)

eye=np.array([-23.4,20.3,5.3]);target=np.array([0.,0.,14.4])
forward=target-eye;forward/=np.linalg.norm(forward)
up=np.array([0.,0.,1.])
right=np.cross(forward,up);right/=np.linalg.norm(right)
up2=np.cross(right,forward)
matrix=np.column_stack([right,up2,-forward])
angles=Rotation.from_matrix(matrix).as_euler('xyz',degrees=True)

results={}
for order in ('identity','rotX90','quat_orient'):
    path=f'/World/Cam{order}'
    cam=UsdGeom.Camera.Define(stage,path)
    xf=UsdGeom.Xformable(cam.GetPrim())
    quat=Rotation.from_matrix(matrix).as_quat()  # xyzw
    if order=='translate_first':
        t=xf.AddTranslateOp();r=xf.AddRotateXYZOp()
        t.Set(Gf.Vec3d(*eye));r.Set(Gf.Vec3f(*angles))
    elif order=='rotX90':
        t=xf.AddTranslateOp();o=xf.AddOrientOp()
        t.Set(Gf.Vec3d(*eye));o.Set(Gf.Quatf(float(np.cos(np.pi/4)),Gf.Vec3f(np.sin(np.pi/4),0,0)))
    elif order=='quat_orient':
        t=xf.AddTranslateOp();o=xf.AddOrientOp()
        t.Set(Gf.Vec3d(*eye));o.Set(Gf.Quatf(float(quat[3]),Gf.Vec3f(*quat[:3])))
    else:
        t=xf.AddTranslateOp();o=xf.AddOrientOp()
        t.Set(Gf.Vec3d(*eye));o.Set(Gf.Quatf(1.,Gf.Vec3f(0,0,0)))
    import omni.kit.app
    for _ in range(5):omni.kit.app.get_app().update()
    local=cam.GetLocalTransformation()
    position=np.array(local.ExtractTranslation())
    rot=np.array(local)[:3,:3]
    world_z=np.array([0.,0.,1.])
    view=-rot[:,2]
    print(f'ORDER {order}: pos={np.round(position,3)}  view={np.round(view,4)}')
    results[order]=dict(position=position.tolist(),view=view.tolist())
import json
print('RESULTS',json.dumps(results))
app.close()
