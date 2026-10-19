import json
from rocket_lab.storage import atomic_json

def test_windows_replace_retry(monkeypatch,tmp_path):
    import rocket_lab.storage as module
    original=module.os.replace;calls=[]
    def replace(source,target):
        calls.append(1)
        if len(calls)<3:raise PermissionError("temporary Windows reader lock")
        return original(source,target)
    monkeypatch.setattr(module.os,"replace",replace)
    path=tmp_path/"status.json";atomic_json(path,{"status":"running"})
    assert json.loads(path.read_text())=={"status":"running"}
    assert len(calls)==3
