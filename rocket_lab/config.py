from pathlib import Path
import copy
import yaml

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

def load_config():
    return copy.deepcopy(yaml.safe_load((ROOT / "config.yaml").read_text()))
