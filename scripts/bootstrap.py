"""Export actual classical runs, schema and runtime provenance."""
import importlib.metadata
import json
import platform
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from rocket_lab.config import DATA, ROOT
from rocket_lab.storage import atomic_json
from rocket_lab.schemas import Telemetry
from rocket_lab.simulation import simulate

def main():
    import torch
    runtime={"python":platform.python_version(),"platform":platform.platform(),"packages":{x:importlib.metadata.version(x) for x in ["torch","mujoco","stable-baselines3","gymnasium","cvxpy","fastapi","numpy","scipy","tensorboard"]},"cuda":torch.version.cuda,"gpu":torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,"cuda_architectures":torch.cuda.get_arch_list()}
    if torch.cuda.is_available():
        runtime["cuda_matrix_test"]=float((torch.ones(32,32,device="cuda")@torch.ones(32,32,device="cuda")).mean().item())
    atomic_json(DATA/"runtime.json",runtime)
    atomic_json(ROOT/"shared"/"telemetry.schema.json",Telemetry.model_json_schema())
    for mission in ["landing","takeoff","combined"]:
        for level in range(1,5):
            run=simulate(mission,"classical",level,42)
            print(mission,level,run.run.outcome,f"speed={run.run.touchdown_speed:.2f} tilt={run.run.tilt:.2f} distance={run.run.pad_distance:.2f}",flush=True)

if __name__=="__main__": main()
