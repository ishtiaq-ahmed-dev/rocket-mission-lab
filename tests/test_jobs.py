import subprocess
import pytest
from rocket_lab.jobs import launch_job
from rocket_lab.storage import read_json


def test_worker_module_allowlist_precedes_any_launch(tmp_path):
    with pytest.raises(ValueError,match='Unsupported'):
        launch_job(['python','-m','arbitrary_module'],tmp_path)
    assert not (tmp_path/'launch.json').exists()


def test_launch_failure_is_persisted_with_actual_diagnostic(monkeypatch,tmp_path):
    import rocket_lab.jobs as module
    def fail(*args,**kwargs):raise subprocess.CalledProcessError(1,['powershell'],stderr='WMI denied this launch')
    monkeypatch.setattr(module.subprocess,'run',fail)
    # Exercise the Windows dispatcher without starting a worker process.
    monkeypatch.setattr(module.os,'name','nt')
    with pytest.raises(subprocess.CalledProcessError):launch_job(['python','-m','rocket_lab.train','--steps','4096'],tmp_path)
    status=read_json(tmp_path/'status.json')
    assert status['status']=='failed' and 'WMI denied' in status['error']
    assert read_json(tmp_path/'launch.json')['module']=='rocket_lab.train'
