"""Standalone plots derived only from measured JSON/CSV artifacts."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from rocket_lab.config import DATA
from rocket_lab.storage import training_jobs,read_json

def main():
    target=DATA/"plots";target.mkdir(parents=True,exist_ok=True)
    plt.style.use("dark_background")
    fig,axes=plt.subplots(1,2,figsize=(13,4.5),constrained_layout=True)
    for job in training_jobs():
        curve=job.get("curve",[])
        if not curve:continue
        label=job["id"]
        axes[0].plot([p["steps"] for p in curve],[p["reward"] for p in curve],marker=".",label=label)
        axes[1].plot([p["steps"] for p in curve],[p["success_rate"] for p in curve],marker=".",label=label)
    axes[0].set(title="Recorded development reward (reward versions differ)",xlabel="environment steps",ylabel="mean return")
    axes[1].set(title="Actual held-out successes",xlabel="environment steps",ylabel="observed success fraction",ylim=(-.02,1.02))
    for ax in axes:ax.grid(alpha=.15);ax.legend(fontsize=6)
    fig.savefig(target/"learning-curves.png",dpi=170);plt.close(fig)
    rows=[x for p in (DATA/"results").glob("*.json") if (x:=read_json(p)) and x["method"]=="classical" and x["scenario"]=="nominal"]
    if rows:
        fig,axes=plt.subplots(1,3,figsize=(13,4),constrained_layout=True)
        for ax,mission in zip(axes,["landing","takeoff","combined"]):
            values=sorted([r for r in rows if r["mission"]==mission],key=lambda r:r["level"])
            if not values:continue
            p=[r["success_rate"] for r in values]
            errors=[[r["success_rate"]-r["confidence_interval"][0] for r in values],[r["confidence_interval"][1]-r["success_rate"] for r in values]]
            ax.bar([str(r["level"]) for r in values],p,color="#b7a184",yerr=errors,capsize=4)
            ax.set(title=mission,xlabel="controller level",ylabel="success fraction",ylim=(0,1.1));ax.grid(axis="y",alpha=.15)
            for i,r in enumerate(values):ax.text(i,.03,f"{r['successes']}/{r['episodes']}",ha="center",fontsize=9,color="#d9e5e6")
        fig.suptitle("Measured controller evaluation with 95% Wilson intervals")
        fig.savefig(target/"classical-comparison.png",dpi=170);plt.close(fig)
    print(target)
if __name__=="__main__":main()
