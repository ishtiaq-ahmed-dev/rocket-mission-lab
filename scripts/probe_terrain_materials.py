"""Probe: which material and shader colour each terrain prim actually binds."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from isaacsim import SimulationApp

app = SimulationApp({'headless': True, 'width': 320, 'height': 240})
import omni.usd
from pxr import UsdShade

from rocket_lab.config import load_config
from rocket_lab.isaac.visuals import NativeVisuals

cfg = load_config()
cfg['mission']['landing'] = [1200.0, 400.0]
cfg['mission']['pad'] = [1200.0, 400.0, 0.0]


class FakePhysics:
    pass


physics = FakePhysics()
physics.cfg = cfg
physics.v = cfg['vehicle']
physics.half = cfg['vehicle']['length'] / 2
physics.engine_lever = cfg['vehicle']['engine_lever']
physics.rest = physics.half + 3.0
physics.position = __import__('numpy').array([0., 0., physics.rest])
physics.release_time = None
physics.throttle = 0.
physics.data = type('D', (), {'time': 0.})()
physics.wind = __import__('numpy').zeros(3)
physics.fuel = 1.
physics.mass = 1.
physics.rotation = lambda: __import__('numpy').eye(3)
physics.detached = False
physics.quaternion = __import__('numpy').array([1., 0., 0., 0.])
physics.payload = None
physics.on_pad = True
physics.gimbal = __import__('numpy').zeros(2)

visuals = NativeVisuals(False, False)
visuals.setup(physics)
stage = omni.usd.get_context().get_stage()
for path in ('/World/Terrain/PlainInner', '/World/Terrain/PlainMid', '/World/Terrain/PlainOuter',
             '/World/Terrain/RidgeNear', '/World/Terrain/RidgeFar', '/World/Terrain/Ocean',
             '/World/LaunchSite/Apron', '/World/LaunchSite/Pad', '/World/Ground'):
    prim = stage.GetPrimAtPath(path)
    if not prim or not prim.IsValid():
        print(f'{path:34s} MISSING')
        continue
    binding = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()[0]
    colour = '?'
    if binding:
        shader = UsdShade.Shader(binding.GetPrim().GetChild('Surface'))
        if shader:
            value = shader.GetInput('diffuseColor').Get()
            colour = tuple(round(c, 3) for c in value) if value else 'none'
    print(f'{path:34s} visible={prim.GetAttribute("visibility").Get()} mat={binding.GetPath() if binding else None} colour={colour}')
app.close()
