from fastapi.testclient import TestClient
from rocket_lab.api import app
from rocket_lab.storage import atomic_json
import os


def test_index_cache_observes_replaced_deleted_files_and_does_not_leak_top_level_mutation(tmp_path):
    from rocket_lab.index_cache import cached_record
    path=tmp_path/'value.json'
    atomic_json(path,dict(steps=10))
    first=cached_record(path);first['steps']=999
    assert cached_record(path)['steps']==10
    original=path.stat()
    atomic_json(path,dict(steps=20))
    os.utime(path,ns=(original.st_atime_ns,original.st_mtime_ns))
    assert cached_record(path)['steps']==20
    path.unlink()
    assert cached_record(path) is None


def test_dashboard_does_not_ship_unused_histories_or_checkpoint_configs(monkeypatch):
    import rocket_lab.dashboard as module
    monkeypatch.setattr(module,'training_jobs',lambda:[dict(id='job',curve=[dict(reward=1)],episodes=[1],steps=5)])
    monkeypatch.setattr(module,'checkpoints',lambda:[dict(id='checkpoint',steps=5,config=dict(secretly_large='x'*100000))])
    client=TestClient(app)
    flight=client.get('/dashboard?view=flight').json()
    assert set(flight)=={'checkpoints'}
    assert 'config' not in flight['checkpoints'][0]
    training=client.get('/dashboard?view=training').json()
    assert training['jobs'][0]['curve']==training['jobs'][0]['episodes']==[]
    assert client.get('/dashboard?view=invalid').status_code==422


def test_selected_job_detail_preserves_history_and_rejects_unknown(monkeypatch,tmp_path):
    import rocket_lab.api as module
    monkeypatch.setattr(module,'DATA',tmp_path)
    value=dict(id='saved-job',curve=[dict(steps=10,reward=1)],episodes=[dict(outcome='success')])
    atomic_json(tmp_path/'jobs/saved-job/status.json',value)
    client=TestClient(app)
    assert client.get('/training/saved-job').json()==value
    assert client.get('/training/missing').status_code==404


def test_worker_budget_yields_wall_time_without_touching_simulation():
    from rocket_lab.resources import WorkBudget
    now=[0.];sleeps=[]
    def sleep(duration):sleeps.append(duration);now[0]+=duration
    budget=WorkBudget(clock=lambda:now[0],sleep=sleep)
    now[0]=.025;budget.yield_if_needed();assert sleeps==[]
    now[0]=.1;budget.yield_if_needed();assert sleeps==[.1]
    now[0]+=.01;budget.yield_if_needed();assert sleeps==[.1]


def test_production_preview_serves_static_and_api_from_one_app(tmp_path):
    from rocket_lab.preview import create_preview
    (tmp_path/'index.html').write_text('<html>Rocket Mission Lab</html>')
    client=TestClient(create_preview(tmp_path))
    assert client.get('/').text=='<html>Rocket Mission Lab</html>'
    assert client.get('/api/health').json()['physics']=='MuJoCo'
    assert client.get('/api/docs').status_code==200
