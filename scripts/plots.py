"""Standalone plots derived only from measured JSON/CSV artifacts."""
import json
from pathlib import Path
import sys
import re
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from rocket_lab.config import DATA
from rocket_lab.storage import training_jobs,read_json,checkpoint_path,atomic_json

def save_figure(fig,path):
    fig.savefig(path,dpi=180)
    if path.suffix=='.svg':
        # Matplotlib adds line-end spaces inside path data; preserve the same
        # SVG tokens while keeping generated files clean in source control.
        path.write_text('\n'.join(line.rstrip() for line in path.read_text(encoding='utf-8').splitlines())+'\n',encoding='utf-8',newline='\n')

def development_plot(target):
    rows=[]
    for path in (DATA/'results').glob('*.json'):
        result=read_json(path,{})
        if not result.get('evaluation_role','').startswith('additional development'):continue
        checkpoint=read_json(checkpoint_path(result['checkpoint_id'])/'checkpoint.json')
        rows.append(result|dict(steps=checkpoint['steps'],algorithm=checkpoint['algorithm'],result_file=path.name))
    if not rows:return
    missions=sorted(set(row['mission'] for row in rows))
    fig,axes=plt.subplots(1,len(missions),figsize=(max(14,len(missions)*8),6),squeeze=False)
    for ax,mission in zip(axes[0],missions):
        values=sorted([row for row in rows if row['mission']==mission],key=lambda row:(row['steps'],row['checkpoint_id']))
        labels=[]
        for row in values:
            version=re.search(r'-v(\d+)-',row['checkpoint_id'])
            labels.append(f"{row['algorithm']} v{version[1] if version else '?'} {row['checkpoint_id'].split('__')[0].split('-')[-1]}\n{row['steps']/1e6:.2f}M")
        rates=[100*row['success_rate'] for row in values]
        errors=[[100*(row['success_rate']-row['confidence_interval'][0]) for row in values],
                [100*(row['confidence_interval'][1]-row['success_rate']) for row in values]]
        ax.bar(range(len(values)),rates,color='#75b8c9' if mission=='takeoff' else '#dba976',yerr=errors,capsize=4,ecolor='#e7d4bd')
        ax.set(title=f'{mission.capitalize()} / full mission',ylabel='Observed success (%)',ylim=(0,108))
        ax.set_xticks(range(len(values)),labels,rotation=35,ha='right',fontsize=8)
        ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
        for index,row in enumerate(values):
            ax.text(index,100*row['confidence_interval'][1]+2,f"{row['successes']}/{row['episodes']}",ha='center',fontsize=8)
    fig.suptitle('Measured full-task development samples / 95% Wilson intervals')
    fig.text(.5,.025,'Repeated development seeds 22000–22255; intervals do not adjust for model selection.\nSteps are each checkpoint\'s training lineage, not total experiment cost. Development comparisons do not replace separate nominal qualification.',ha='center',fontsize=9)
    fig.subplots_adjust(bottom=.25,top=.87,wspace=.18)
    for extension in ('png','svg'):save_figure(fig,target/f'full-task-development.{extension}')
    plt.close(fig)
    atomic_json(target/'full-task-development-sources.json',dict(scope='larger development samples, not qualification',results=[row['result_file'] for row in rows]))

def qualification_plot(target):
    rows=[value|dict(result_file=path.name) for path in (DATA/'results').glob('*.json') if (value:=read_json(path,{})).get('evaluation_role')=='frozen-candidate nominal qualification']
    groups=sorted(set((row['mission'],row['config_hash']) for row in rows))
    for mission,config in groups:
        values=sorted([row for row in rows if (row['mission'],row['config_hash'])==(mission,config)],key=lambda row:row['method'])
        if len(values)<2:continue
        labels=['Classical L4' if row['method']=='classical' else 'PPO frozen checkpoint' for row in values]
        rates=[100*(1-row['success_rate']) for row in values]
        errors=[[100*(row['confidence_interval'][1]-row['success_rate']) for row in values],
                [100*(row['success_rate']-row['confidence_interval'][0]) for row in values]]
        fig,ax=plt.subplots(figsize=(9,5))
        ax.bar(labels,rates,color=['#dba976' if row['method']=='classical' else '#75b8c9' for row in values],yerr=errors,capsize=7,width=.55,ecolor='#e7d4bd')
        ax.set(title=f'{mission.capitalize()} / frozen nominal candidates',ylabel='Observed failures (%)',ylim=(0,max(3,max(rates)*1.6)))
        ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
        for index,row in enumerate(values):
            ax.text(index,100*(1-row['confidence_interval'][0])+.12,f"{row['episodes']-row['successes']:,} / {row['episodes']:,} failures",ha='center')
        fig.text(.5,.04,f'95% Wilson intervals. Matched seeds 10000–19999; configuration {config}.\nExact frozen nominal candidates only; stress, other snapshots and real flight remain separate.',ha='center',fontsize=9)
        fig.subplots_adjust(bottom=.23)
        for extension in ('png','svg'):save_figure(fig,target/f'{mission}-frozen-qualification.{extension}')
        plt.close(fig)
    atomic_json(target/'qualification-sources.json',dict(scope='frozen nominal candidates',results=[row['result_file'] for row in rows]))

def main():
    target=DATA/"plots";target.mkdir(parents=True,exist_ok=True)
    plt.style.use("dark_background")
    development_plot(target)
    qualification_plot(target)
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
            ax.bar([str(r["level"]) for r in values],p,color="#b7a184",yerr=errors,capsize=4,ecolor='#e7d4bd')
            ax.set(title=mission,xlabel="controller level",ylabel="success fraction",ylim=(0,1.1));ax.grid(axis="y",alpha=.15)
            for i,r in enumerate(values):ax.text(i,.03,f"{r['successes']}/{r['episodes']}",ha="center",fontsize=9,color="#d9e5e6")
        fig.suptitle("Measured controller evaluation with 95% Wilson intervals")
        fig.savefig(target/"classical-comparison.png",dpi=170);plt.close(fig)
    print(target)
if __name__=="__main__":main()
