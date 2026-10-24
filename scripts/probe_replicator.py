"""Probe: import omni.replicator under the project's lean visual Kit experience."""
import sys
from isaacsim import SimulationApp
app = SimulationApp({
    'headless': True,
    'extra_args': ['--enable', 'omni.replicator.core',
                   '--ext-folder', 'D:/AppInstalled/NVIDIA/IsaacSim/6.2.0/extscache',
                   '--ext-folder', 'D:/AppInstalled/NVIDIA/IsaacSim/6.2.0/extsDeprecated'],
    'experience': 'D:/AI SIDE PROJECTS/ROCKET LANDER + LAUNCHER/config/isaac-visual.kit',
})
import omni.kit.app
try:
    import omni.replicator.core as rep
    print('PROBE: omni.replicator.core OK', rep)
except BaseException as e:
    print('PROBE: failed import:', e)
    import omni
    print('omni package:', omni.__path__ if hasattr(omni, '__path__') else omni)
    print('paths containing replicator:', [p for p in sys.path if 'replic' in p.lower()])
    print('omni module file:', getattr(omni, '__file__', None))
app.close()
