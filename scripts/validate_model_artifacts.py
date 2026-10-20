"""Validate published model evidence and fixed-seed replay links without a browser."""
from pathlib import Path
import json
import sys
import time
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from rocket_lab.config import ROOT,DATA
from rocket_lab.schemas import Telemetry
from rocket_lab.storage import atomic_json,checkpoint_path,read_json
from rocket_lab.evaluate import wilson
import csv
import hashlib
from collections import Counter

def validate():
    public=ROOT/'frontend'/'public';dist=ROOT/'frontend'/'dist'
    summaries=read_json(public/'model-probes.json',[])
    assert summaries,'No published model probes'
    checked=[]
    for summary in summaries:
        identifier=summary['checkpoint_id']
        raw=read_json(DATA/'probes'/f"{identifier}{'-practice' if summary.get('practice') else ''}.json")
        checkpoint=read_json(checkpoint_path(identifier)/'checkpoint.json')
        assert summary['steps']==checkpoint['steps']
        assert summary['training_config_hash']==checkpoint['config_hash']
        for stage in summary['stages']:
            saved=next(s for s in raw['stages'] if s['difficulty']==stage['difficulty'])
            assert len(saved['rows'])==stage['episodes']
            assert sum(r['outcome']=='success' for r in saved['rows'])==stage['successes']
            for key,field in [('mean_speed','touchdown_speed'),('mean_tilt','tilt'),('mean_offset','pad_distance')]:
                assert np.isclose(stage[key],np.mean([r[field] for r in saved['rows']]),atol=1e-9,rtol=0)
            relative=Path(stage['replay_url'].removeprefix('/'))
            assert relative.parts[0]=='model-replays' and '..' not in relative.parts
            document=read_json(public/relative)
            assert document==read_json(dist/relative),'Built replay differs from public source'
            replay=Telemetry.model_validate(document);first=saved['rows'][0]
            assert replay.run.checkpoint_id==identifier and replay.run.checkpoint_steps==summary['steps']
            assert replay.run.seed==first['seed']==stage['seeds'][0]==stage['replay_seed']
            assert replay.run.difficulty==stage['difficulty']
            if summary.get('practice'):
                assert replay.run.training_mode and replay.run.mission=='takeoff'
                assert replay.run.target_altitude==stage['target_altitude'] and replay.run.target_velocity==stage['target_velocity']
                assert 'training-only' in replay.run.source
            assert replay.run.outcome==first['outcome']==stage['replay_outcome']
            assert 'development replay' in replay.run.source
            np.testing.assert_allclose([replay.run.touchdown_speed,replay.run.tilt,replay.run.pad_distance],
                [first['touchdown_speed'],first['tilt'],first['pad_distance']],atol=1e-6,rtol=0)
            assert all(b.t>a.t for a,b in zip(replay.frames,replay.frames[1:]))
            assert all(abs(np.linalg.norm(f.quaternion)-1)<1e-5 for f in replay.frames)
            checked.append(dict(checkpoint=identifier,difficulty=stage['difficulty'],seed=replay.run.seed,
                                outcome=replay.run.outcome,frames=len(replay.frames),url=stage['replay_url']))
    assert read_json(public/'model-probes.json')==read_json(dist/'model-probes.json')
    evaluations=read_json(public/'model-evaluations.json',[])
    successful_examples=0
    assert evaluations==read_json(dist/'model-evaluations.json')
    for evaluation in evaluations:
        filename=evaluation['result_file'];assert Path(filename).name==filename
        source=read_json(DATA/'results'/filename)
        assert all(evaluation[key]==value for key,value in source.items())
        with (DATA/'results'/Path(filename).with_suffix('.csv')).open(newline='') as stream:rows=list(csv.DictReader(stream))
        assert len(rows)==evaluation['episodes']
        assert [int(row['seed']) for row in rows]==list(range(evaluation['seeds'][0],evaluation['seeds'][1]+1))
        successes=sum(row['outcome']=='success' for row in rows);assert successes==evaluation['successes']
        np.testing.assert_allclose(evaluation['confidence_interval'],wilson(successes,len(rows)),atol=1e-12,rtol=0)
        for key in ('touchdown_speed','tilt','pad_distance'):
            assert np.isclose(evaluation[f'mean_{key}'],np.mean([float(row[key]) for row in rows]),atol=1e-9,rtol=0)
        if evaluation.get('replay_url'):
            relative=Path(evaluation['replay_url'].removeprefix('/'))
            assert relative.parts[0]=='model-replays' and '..' not in relative.parts
            document=read_json(public/relative);assert document==read_json(dist/relative)
            replay=Telemetry.model_validate(document)
            selected=next(row for row in rows if row['outcome']=='success')
            assert replay.run.seed==int(selected['seed'])==evaluation['replay_seed']
            assert replay.run.checkpoint_id==evaluation['checkpoint_id']
            assert replay.run.difficulty==1. and replay.run.outcome=='success'
            assert 'selected successful' in replay.run.source and 'selected by outcome' in evaluation['selection_note']
            for key in ('touchdown_speed','tilt','pad_distance'):
                assert np.isclose(getattr(replay.run,key),float(selected[key]),atol=1e-6,rtol=0)
            successful_examples+=1
    qualifications=read_json(public/'model-qualifications.json',[])
    assert qualifications==read_json(dist/'model-qualifications.json',[])
    for qualification in qualifications:
        filename=qualification['result_file'];assert Path(filename).name==filename
        source=read_json(DATA/'results'/filename)
        assert all(qualification[key]==value for key,value in source.items())
        assert source['evaluation_role']=='frozen-candidate nominal qualification'
        assert source['episodes']==10000 and source['seeds']==[10000,19999] and source['scenario']=='nominal'
        with (DATA/'results'/Path(filename).with_suffix('.csv')).open(newline='') as stream:rows=list(csv.DictReader(stream))
        assert len(rows)==10000 and [int(row['seed']) for row in rows]==list(range(10000,20000))
        successes=sum(row['outcome']=='success' for row in rows);assert successes==source['successes']
        assert dict(Counter(row['outcome'] for row in rows if row['outcome']!='success'))==source['failures']
        np.testing.assert_allclose(source['confidence_interval'],wilson(successes,10000),atol=1e-12,rtol=0)
        for key in ('touchdown_speed','tilt','pad_distance','fuel_used'):
            assert np.isclose(source[f'mean_{key}'],np.mean([float(row[key]) for row in rows]),atol=1e-9,rtol=0)
        manifest=read_json(DATA/'qualifications'/source['manifest_file'])
        assert manifest['checkpoint_id']==source['checkpoint_id'] and manifest['config_hash']==source['config_hash']
        identity=read_json(DATA/'evaluations'/source['progress_id']/'identity.json')
        assert identity['source_hash']==source['source_hash'] and identity['checkpoint_id']==source['checkpoint_id']
        snapshot=DATA/'qualifications'/f"{source['progress_id']}.source"
        digest=hashlib.sha256(b''.join((snapshot/name).read_bytes() for name in ('physics.py','envs.py','controllers.py','simulation.py'))).hexdigest()
        assert digest==source['source_hash']
        if source['checkpoint_id']:
            folder=checkpoint_path(source['checkpoint_id'])
            assert all(hashlib.sha256((folder/name).read_bytes()).hexdigest()==value for name,value in manifest['candidate_sha256'].items())
    report=dict(created_at=time.time(),status='passed',scope='saved evidence/schema/build-link validation; no browser or HTTP check',
                checkpoints=len(summaries),replays=len(checked)+successful_examples,stage_replays=len(checked),
                selected_successful_examples=successful_examples,full_task_samples=len(evaluations),
                full_task_episodes=sum(value['episodes'] for value in evaluations),qualification_samples=len(qualifications),
                qualification_episodes=sum(value['episodes'] for value in qualifications),checked=checked)
    atomic_json(DATA/'model-artifact-validation.json',report)
    print(json.dumps({key:value for key,value in report.items() if key!='checked'},indent=2))
    return report

if __name__=='__main__':validate()
