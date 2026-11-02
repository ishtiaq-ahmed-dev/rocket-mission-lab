import json
from rocket_lab.storage import atomic_json

def test_dynamics_identity_includes_propulsion(monkeypatch,tmp_path):
    import rocket_lab.storage as module
    source=module.ROOT/'rocket_lab'
    target=tmp_path/'rocket_lab';target.mkdir()
    for name in ('physics.py','envs.py','controllers.py','simulation.py','missions.py','atmosphere.py','propulsion.py'):
        (target/name).write_bytes((source/name).read_bytes())
    monkeypatch.setattr(module,'ROOT',tmp_path)
    before=module.dynamics_hash()
    with (target/'propulsion.py').open('ab') as file:file.write(b'\n# changed\n')
    assert module.dynamics_hash()!=before

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
