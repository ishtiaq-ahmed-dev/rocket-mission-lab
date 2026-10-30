"""Does the viewport render product honour focalLength on /OmniverseKit_Persp?

A 4 x 40 m white slab is framed from 60 m with changing focal lengths. Pixel
measurements of the slab edges say which attribute actually drives the FOV.
"""
import os
import time
from pathlib import Path

import numpy as np
from isaacsim import SimulationApp

ROOT = Path(__file__).resolve().parents[1]
folders = []
for folder in ('extscache', 'extsDeprecated'):
    folders += ['--ext-folder', str(Path(os.environ['ISAAC_PATH']) / folder)]
folders += ['--ext-folder', str(ROOT / 'config')]
app = SimulationApp({'headless': True, 'width': 1280, 'height': 720,
    'extra_args': ['--enable', 'isaacsim.core.api', '--enable', 'isaacsim.core.prims',
                   '--/app/asyncRendering=false', *folders],
    'experience': str(ROOT / 'config/isaac-visual.kit')})

import carb
import omni.replicator.core as rep
import omni.usd
from pxr import Gf, UsdGeom, UsdLux
from isaacsim.core.utils.viewports import set_camera_view

stage = omni.usd.get_context().get_stage()
ground = UsdGeom.Cylinder.Define(stage, '/World/Ground')
ground.CreateAxisAttr('Z'); ground.CreateRadiusAttr(500.); ground.CreateHeightAttr(.1)
slab = UsdGeom.Cube.Define(stage, '/World/Slab')
slab.AddTranslateOp().Set(Gf.Vec3d(0., 0., 20.))
slab.AddScaleOp().Set(Gf.Vec3f(4., 1., 40.))
UsdLux.DistantLight.Define(stage, '/World/Sun').CreateIntensityAttr(1500.)
UsdLux.DomeLight.Define(stage, '/World/Sky').CreateIntensityAttr(500.)

OUT = ROOT / 'data/probes/focal'
OUT.mkdir(parents=True, exist_ok=True)
import cv2


def make_camera(path, eye, target):
    cam = UsdGeom.Camera.Define(stage, path)
    cam.CreateFocalLengthAttr(18.147)
    cam.CreateHorizontalApertureAttr(20.955)
    cam.CreateVerticalApertureAttr(11.787)
    cam.CreateClippingRangeAttr(Gf.Vec2f(.1, 30000.))
    xform = UsdGeom.Xformable(cam)
    matrix = Gf.Matrix4d(1.).SetLookAt(Gf.Vec3d(*map(float, eye)), Gf.Vec3d(*map(float, target)), Gf.Vec3d(0, 0, 1)).GetInverse()
    xform.AddTransformOp().Set(matrix)
    return cam


def measure(tag, data):
    cv2.imwrite(str(OUT / f'{tag}.png'), data[..., :3][..., ::-1])
    sky = data[:20, :20, :3].mean(axis=(0, 1))
    delta = np.abs(data[..., :3].astype(float) - sky).sum(axis=2)
    mask = delta > 25
    columns = np.flatnonzero(mask.any(axis=0))
    rows = np.flatnonzero(mask.any(axis=1))
    width = int(columns[-1] - columns[0]) if columns.size else 0
    height = int(rows[-1] - rows[0]) if rows.size else 0
    print(f'PROBE {tag}: slab_px={width}x{height} of 1280x720', flush=True)


def shot(tag, path, eye, target, focal, aperture=20.955):
    camera = make_camera(path, eye, target)
    camera.GetFocalLengthAttr().Set(float(focal))
    camera.GetHorizontalApertureAttr().Set(float(aperture))
    camera.GetVerticalApertureAttr().Set(float(aperture * 9. / 16.))
    product = rep.create.render_product(path, (1280, 720))
    annotator = rep.AnnotatorRegistry.get_annotator('rgb'); annotator.attach(product)
    rep.orchestrator.step(rt_subframes=4, pause_timeline=True)
    readback = camera.GetFocalLengthAttr().Get()
    print(f'PROBE {tag}: requested_focal={focal} readback={readback:.2f}', flush=True)
    measure(tag, np.asarray(annotator.get_data()))
    annotator.detach(); product.destroy()
    stage.RemovePrim(path)


for focal in (10., 20., 50., 100.):
    shot(f'cam-focal-{focal:g}', f'/World/FilmCamera{int(focal)}', (60., 0., 20.), (0., 0., 20.), focal)
shot('cam-focal-10-wide', '/World/FilmCameraWide', (60., 0., 20.), (0., 0., 20.), 10., aperture=36.)
shot('cam-focal-50-aperture-36', '/World/FilmCameraWide50', (60., 0., 20.), (0., 0., 20.), 50., aperture=36.)
time.sleep(.5)
app.close()
