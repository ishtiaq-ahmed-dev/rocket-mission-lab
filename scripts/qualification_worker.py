"""Durable evaluation with a resumable per-seed journal and local log."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from rocket_lab.config import ROOT

def main():
    log=(ROOT/"logs"/"qualification.log").open("a",buffering=1)
    sys.stdout=sys.stderr=log
    from rocket_lab.resources import configure_background_worker
    configure_background_worker()
    from rocket_lab.evaluate import evaluate,save_result
    result,rows=evaluate("landing",4,episodes=10000,progress_id="landing-classical-final-10000-v1")
    save_result(result,rows)
    print(result,flush=True)

if __name__=="__main__":main()
