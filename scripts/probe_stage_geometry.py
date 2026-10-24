"""Probe: build the visual stage headless and print world-space bboxes for
prims above 25 m near the pad, to identify the floating checkered artifact."""
import sys
sys.path.insert(0, 'rocket_lab')
from isaacsim import SimulationApp
app = SimulationApp({'headless': True, 'width': 320, 'height': 240})
import numpy as np
from pxr import Usd, UsdGeom, Gf
from rocket_lab.config import load_config
from rocket_lab.isaac.physics import IsaacRocketPhysics
from rocket_lab.isaac.visuals import NativeVisuals

cfg = load_config()
visuals = NativeVisuals()
physics = IsaacRocketPhysics(cfg, headless=True, visuals=visuals)
physics.reset(0)

stage = visuals.stage
cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_, UsdGeom.Tokens.render])
print('--- prims with bbox center z > 25 and xy within 60 m of launch pad ---')
for prim in stage.Traverse():
    if not prim.IsA(UsdGeom.Xformable):
        continue
    try:
        bbox = cache.ComputeWorldBound(prim)
    except Exception:
        continue
    rng = bbox.ComputeAlignedRange()
    center = rng.GetMidpoint()
    if center[2] > 15. and abs(center[0]) < 80 and abs(center[1]) < 80:
        s = rng.GetSize()
        print(f'{prim.GetPath()} center=({center[0]:.1f},{center[1]:.1f},{center[2]:.1f}) size=({s[0]:.1f},{s[1]:.1f},{s[2]:.1f})')
app.close()
