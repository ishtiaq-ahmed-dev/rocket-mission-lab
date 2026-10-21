"""WMI/session-independent worker host with owned logs and no visible console."""
from pathlib import Path
import json
import os
import runpy
import sys
import time
import traceback

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


if __name__=='__main__':
    path=Path(sys.argv[1]).resolve()
    if not path.is_relative_to(ROOT/'data'):raise ValueError('Worker specification must be in project data')
    specification=json.loads(path.read_text(encoding='utf-8'))
    module=specification['module']
    if module not in ('rocket_lab.train','rocket_lab.campaign'):raise ValueError('Unsupported worker')
    with (path.parent/'output.log').open('a',buffering=1,encoding='utf-8') as output:
        sys.stdout=sys.stderr=output
        print(f'INDEPENDENT WORKER pid={os.getpid()} module={module} started={time.time()}',flush=True)
        sys.argv=[module,*specification['arguments']]
        try:runpy.run_module(module,run_name='__main__')
        except BaseException:
            from rocket_lab.storage import atomic_json,read_json
            status=read_json(path.parent/'status.json',{})
            status.update(status='failed',error=traceback.format_exc(),updated_at=time.time(),pid=os.getpid())
            atomic_json(path.parent/'status.json',status)
            traceback.print_exc();raise
