from pathlib import Path
import copy
import yaml

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

def load_config(path=None):
    return copy.deepcopy(yaml.safe_load((Path(path) if path else ROOT / "config.yaml").read_text()))
