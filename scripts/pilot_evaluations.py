"""Bounded controller/robustness pilots. Does not claim full qualification."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from rocket_lab.evaluate import evaluate,save_result

def main():
    for mission in ["landing","takeoff","combined"]:
        for level in range(1,5):
            result,rows=evaluate(mission,level,episodes=32,start_seed=20000)
            save_result(result,rows)
            print(mission,level,f"{result['successes']}/32",result["failures"],flush=True)
    for scenario in ["gusts","noise","thrust_loss","extreme_starts"]:
        result,rows=evaluate("landing",4,episodes=32,start_seed=20000,scenario=scenario)
        save_result(result,rows)
        print("robustness",scenario,f"{result['successes']}/32",result["failures"],flush=True)

if __name__=="__main__":main()
