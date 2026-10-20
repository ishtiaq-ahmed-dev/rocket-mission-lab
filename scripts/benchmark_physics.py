"""Compare a native quaternion conversion and explicit engine-lever cross product."""
from pathlib import Path
import hashlib
import json
import statistics
import sys
import time
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from rocket_lab.config import ROOT,DATA,load_config
from rocket_lab.storage import atomic_json

def classes(source):
    changed=source.replace('from scipy.spatial.transform import Rotation\n','')
    old='''        q = self.data.qpos[3:7]
        return Rotation.from_quat([q[1], q[2], q[3], q[0]]).as_matrix()'''
    new='''        quaternion = self.data.qpos[3:7].copy()
        norm = mujoco.mju_normalize4(quaternion)
        if not 0 < norm < np.inf:
            raise ValueError("Quaternion must have finite nonzero norm")
        matrix = np.empty(9)
        mujoco.mju_quat2Mat(matrix, quaternion)
        return matrix.reshape(3, 3)'''
    assert old in changed
    changed=changed.replace(old,new)
    old='rotation @ np.cross([0., 0., -self.half], force_body)'
    new='rotation @ np.array([self.half*force_body[1], -self.half*force_body[0], 0.])'
    assert old in changed;changed=changed.replace(old,new)
    variants=[]
    for name,text in [('reference',source),('native',changed)]:
        namespace={'__name__':f'rocket_lab._benchmark_{name}','__package__':'rocket_lab'}
        exec(compile(text,f'<physics-{name}>','exec'),namespace)
        variants.append(namespace['RocketPhysics'])
    return variants,changed

def run():
    current=(ROOT/'rocket_lab'/'physics.py').read_text(encoding='utf-8')
    folder=DATA/'performance';folder.mkdir(exist_ok=True)
    reference_path=folder/'physics-reference.txt'
    # Once applied, retain the pre-change source as the comparison reference.
    source=current if 'from scipy.spatial.transform import Rotation' in current else reference_path.read_text(encoding='utf-8')
    (reference,native),changed=classes(source);cfg=load_config()
    if source!=current and changed!=current:
        raise ValueError('Live physics differs from both measured variants; review before benchmarking')
    actions=np.random.default_rng(219).normal([.2,0,0],[.2,.025,.025],(600,3))
    maximum={key:0. for key in ('position','velocity','quaternion','angular_velocity','fuel_mass','wind','tilt')}
    for seed in range(32):
        first,second=reference(cfg),native(cfg)
        for physics in (first,second):physics.reset(seed,position=[0,0,5020],velocity=[2,-1,-20])
        for action in actions[:120]:
            a,b=first.step(action),second.step(action)
            for key in maximum:
                difference=float(np.max(np.abs(np.asarray(a[key])-np.asarray(b[key]))));maximum[key]=max(maximum[key],difference)
                np.testing.assert_allclose(a[key],b[key],atol=1e-8,rtol=0)
    timings={name:[] for name in ('reference','native')}
    for iteration in range(6):
        for name,cls in ([('reference',reference),('native',native)] if iteration%2==0 else [('native',native),('reference',reference)]):
            physics=cls(cfg);start=time.perf_counter()
            for index,action in enumerate(actions):
                if index%120==0:physics.reset(index,position=[0,0,5020],velocity=[2,-1,-20])
                physics.step(action)
            timings[name].append(time.perf_counter()-start)
    speedup=statistics.median(timings['reference'])/statistics.median(timings['native'])
    report=dict(scope='CPU headless dynamics microbenchmark during concurrent training; not GPU, browser FPS or end-to-end training throughput',
                hash_kind='UTF-8 source text with normalized newlines',
                source_hash=hashlib.sha256(source.encode()).hexdigest(),variant_hash=hashlib.sha256(changed.encode()).hexdigest(),
                trajectories=32,steps_per_trajectory=120,maximum_absolute_differences=maximum,
                control_steps_per_timing=600,timings_seconds=timings,median_speedup=speedup,
                reference_steps_per_second=600/statistics.median(timings['reference']),native_steps_per_second=600/statistics.median(timings['native']),
                source_url='https://mujoco.readthedocs.io/en/stable/APIreference/APIfunctions.html#mju-quat2mat',applied=current==changed)
    atomic_json(DATA/'physics-performance-validation.json',report)
    (folder/'physics-reference.txt').write_text(source,encoding='utf-8')
    (folder/'physics-native-candidate.txt').write_text(changed,encoding='utf-8')
    print(json.dumps(report,indent=2))
    return report

if __name__=='__main__':run()
