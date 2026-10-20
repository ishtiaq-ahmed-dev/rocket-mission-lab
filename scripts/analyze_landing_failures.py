"""Inspect simultaneous terminal constraint failures from one real batch."""
from pathlib import Path
from collections import Counter
import argparse
import csv
import sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from rocket_lab.config import DATA
from rocket_lab.storage import atomic_json,config_hash,read_json


def run(filename):
    if Path(filename).name!=filename or not filename.endswith('.json'):raise ValueError('Use a saved result filename')
    result=read_json(DATA/'results'/filename)
    if not result or result['mission']!='landing':raise ValueError('This analysis requires a landing batch, not ascent speed magnitude')
    identity=read_json(DATA/'evaluations'/result['progress_id']/'identity.json')
    cfg=identity['config'];assert config_hash(cfg)==result['config_hash']
    with (DATA/'results'/Path(filename).with_suffix('.csv')).open(newline='') as stream:rows=list(csv.DictReader(stream))
    assert len(rows)==result['episodes']
    impacts=[row for row in rows if row['outcome'] in ('success','crash_speed','crash_tilt','missed_pad')]
    other=Counter(row['outcome'] for row in rows if row not in impacts)
    speed=np.array([float(row['touchdown_speed']) for row in impacts])
    tilt=np.array([float(row['tilt']) for row in impacts])
    offset=np.array([float(row['pad_distance']) for row in impacts])
    m=cfg['mission']
    failed=np.column_stack((speed>=m['touchdown_speed'],tilt>=m['touchdown_tilt_deg'],offset>m['pad_radius']))
    names=['speed','tilt','offset'];joint=Counter()
    for row,violations in zip(impacts,failed):
        combination='+'.join(name for name,bad in zip(names,violations) if bad) or 'none'
        joint[combination]+=1
        assert (combination=='none')==(row['outcome']=='success')
    report=dict(scope='One batch; simultaneous terminal kinematic failures, not pooled seeds or qualification',
                result_file=filename,checkpoint_id=result['checkpoint_id'],seeds=result['seeds'],episodes=len(rows),impact_episodes=len(impacts),
                other_outcomes=dict(other),thresholds=dict(speed_less_than=m['touchdown_speed'],tilt_less_than=m['touchdown_tilt_deg'],offset_at_most=m['pad_radius']),
                individual_constraint_pass_counts={name:int((~failed[:,index]).sum()) for index,name in enumerate(names)},
                simultaneous_violations=dict(joint),recorded_successes=result['successes'])
    stem=f"landing-terminal-{result['checkpoint_id']}-s{result['seeds'][0]}-n{result['episodes']}"
    atomic_json(DATA/'diagnostics'/f'{stem}.json',report)
    plt.style.use('dark_background');plt.rcParams['svg.hashsalt']='rocket-mission-lab';fig,axes=plt.subplots(1,2,figsize=(12,5))
    points=axes[0].scatter(offset,speed,c=tilt,cmap='plasma',vmin=0,vmax=max(6,float(np.percentile(tilt,98))),s=18,alpha=.8)
    axes[0].axvline(m['pad_radius'],color='#80c9b5',linestyle='--',linewidth=1)
    axes[0].axhline(m['touchdown_speed'],color='#80c9b5',linestyle='--',linewidth=1)
    axes[0].set(xlabel='Terminal pad offset (m)',ylabel='Terminal total speed (m/s)',title='All recorded impact outcomes')
    fig.colorbar(points,ax=axes[0],label='Terminal tilt (degrees)')
    counts=[report['individual_constraint_pass_counts'][key] for key in names]+[result['successes']]
    axes[1].bar(['Speed only','Tilt only','Offset only','All three'],counts,color=['#8db8b8']*3+['#dba976'])
    axes[1].set(ylabel='Episodes meeting the constraint',ylim=(0,len(impacts)*1.12),title='Individual conditions do not establish a landing')
    for index,value in enumerate(counts):axes[1].text(index,value+3,f'{value}/{len(impacts)}',ha='center',fontsize=10)
    for ax in axes:ax.grid(alpha=.15);ax.set_axisbelow(True)
    fig.suptitle(f"Landing checkpoint {result['checkpoint_id'].split('__')[1]} / seeds {result['seeds'][0]}–{result['seeds'][1]}")
    fig.text(.5,.035,'Tilt, speed and pad constraints must pass together. Original outcomes remain authoritative.\nThis is one development sample; it does not establish independent reliability.',ha='center',fontsize=9)
    fig.subplots_adjust(bottom=.23,top=.84,wspace=.3)
    folder=DATA/'plots';folder.mkdir(exist_ok=True)
    for extension in ('png','svg'):
        path=folder/f'{stem}.{extension}';fig.savefig(path,dpi=160,metadata={'Date':None} if extension=='svg' else None)
        if extension=='svg':path.write_text('\n'.join(line.rstrip() for line in path.read_text(encoding='utf-8').splitlines())+'\n',encoding='utf-8',newline='\n')
    plt.close(fig);print(report,flush=True)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('result_file');args=parser.parse_args();run(args.result_file)
