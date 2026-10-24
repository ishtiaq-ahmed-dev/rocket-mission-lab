"""Probe what the rgb annotator really returns in the visual kit experience.

Fastest way to find why the recorder sees zero frames without guessing.
"""
import sys
from isaacsim import SimulationApp

app = SimulationApp({'headless': True, 'width': 640, 'height': 360,
                     'extra_args': ['--enable', 'omni.replicator.core',
                                    '--ext-folder', 'D:/AppInstalled/NVIDIA/IsaacSim/6.2.0/extscache',
                                    '--ext-folder', 'D:/AppInstalled/NVIDIA/IsaacSim/6.2.0/extsDeprecated'],
                     'experience': 'D:/AI SIDE PROJECTS/ROCKET LANDER + LAUNCHER/config/isaac-visual.kit'})
import numpy as np
import omni.kit.app
import omni.replicator.core as rep
import omni.usd
from pathlib import Path

stage = omni.usd.get_context().get_stage()
from pxr import UsdGeom, Gf
box = UsdGeom.Cube.Define(stage, '/World/Box')
box.AddTranslateOp().Set(Gf.Vec3d(.0, .0, .5))
box.AddScaleOp().Set(Gf.Vec3f(2., 2., 2.))

prod = rep.create.render_product('/OmniverseKit_Persp', (640, 360))
ann = rep.AnnotatorRegistry.get_annotator('rgb')
ann.attach(prod)

def drain(tag):
    data = ann.get_data()
    kind = type(data).__name__
    print(f'PROBE {tag}: size={getattr(data, "size", None)} kind={kind}', flush=True)
    if getattr(data, 'size', 0):
        a = np.asarray(data)
        print('  dtype', a.dtype, 'shape', a.shape, 'mean', a.mean(), flush=True)
    else:
        try:
            cpu = ann.get_data(device='cpu')
            print(f'  cpu size={getattr(cpu, "size", None)} kind={type(cpu).__name__}', flush=True)
            if getattr(cpu, 'size', 0):
                a = np.asarray(cpu.numpy() if hasattr(cpu, 'numpy') else cpu)
                print('  dtype', a.dtype, 'shape', a.shape, 'mean', a.mean(), flush=True)
        except BaseException as e:
            print('  cpu failed:', repr(e)[:120], flush=True)

for i in range(5):
    app.update()
drain('after app.update x5')

try:
    rt = rep.orchestrator.step(rt_subframes=0, pause_timeline=False, flush_data_on_stop=True)
    print('PROBE orchestrator.step ->', rt, flush=True)
except BaseException as e:
    print('PROBE orchestrator.step kwargs failed:', repr(e)[:120], flush=True)
    try:
        rep.orchestrator.step()
        print('PROBE orchestrator.step() plain ok', flush=True)
    except BaseException as e2:
        print('PROBE step plain failed:', repr(e2)[:120], flush=True)
for i in range(3):
    app.update()
drain('after orchestrator.step')

for i in range(3):
    try:
        rep.orchestrator.step(rt_subframes=0, pause_timeline=False)
    except BaseException as e:
        print('step loop failed:', repr(e)[:100], flush=True)
        break
    app.update()
    drain(f'loop {i}')
app.close()
