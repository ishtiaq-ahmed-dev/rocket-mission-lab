import errno
from pathlib import Path
from types import SimpleNamespace
import pytest
from rocket_lab import storage
from rocket_lab.train import TrainingCallback


def test_partial_atomic_write_preserves_previous_record_and_cleans_temp(tmp_path,monkeypatch):
    target=tmp_path/'status.json';storage.atomic_json(target,{'status':'saved'})
    original=Path.write_text
    def full_disk(path,text,**kwargs):
        original(path,'partial',**kwargs)
        raise OSError(errno.ENOSPC,'No space left on device')
    monkeypatch.setattr(Path,'write_text',full_disk)
    with pytest.raises(OSError):storage.atomic_json(target,{'status':'new'})
    assert storage.read_json(target)=={'status':'saved'}
    assert list(tmp_path.glob('*.tmp'))==[]


def test_low_space_stops_before_exhaustion_and_requests_final_checkpoint(tmp_path,monkeypatch):
    import rocket_lab.train as module
    monkeypatch.setattr(module,'DATA',tmp_path)
    callback=TrainingCallback('low-space','landing','PPO',100)
    callback.folder.mkdir(parents=True);callback.milestones=[]
    callback.locals={};written=[]
    monkeypatch.setattr(module.shutil,'disk_usage',lambda path:SimpleNamespace(free=48*1024**2))
    monkeypatch.setattr(callback,'write_status',lambda *args,**kwargs:written.append(True))
    assert callback._on_step() is False
    assert (callback.folder/'stop').exists() and written
    assert 'disk exhaustion' in callback.stop_reason
    monkeypatch.setattr(module.shutil,'disk_usage',lambda path:SimpleNamespace(free=16*1024**2))
    with pytest.raises(OSError,match='existing checkpoints are preserved'):callback.checkpoint(final=True)
