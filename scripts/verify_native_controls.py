"""Exercise real native pause/step/manual/guidance/retarget/stop over loopback."""
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from rocket_lab.isaac.stream import exchange


def wait_for(predicate,timeout=60):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        try:
            value=exchange(dict(op='status'))
            if value.get('snapshot') and predicate(value['snapshot']):return value['snapshot']
        except (OSError,ValueError):pass
        time.sleep(.05)
    raise TimeoutError('Native control acknowledgement timed out')


def command(kind,**values):
    request=urllib.request.Request('http://127.0.0.1:5180/api/native/command',
        data=json.dumps(dict(type=kind,**values)).encode(),headers={'Content-Type':'application/json'},method='POST')
    with urllib.request.urlopen(request,timeout=2) as response:assert json.load(response)['queued']


def main():
    evidence=ROOT/'docs/evidence/2026-10-23';evidence.mkdir(parents=True,exist_ok=True)
    report=dict(status='starting');process=None
    try:
        try:
            exchange(dict(op='status'))
        except OSError:pass
        else:raise RuntimeError('Another native runner owns port 8766; stop it before this test')
        with (ROOT/'logs/isaac-control-test.log').open('w') as log:
            process=subprocess.Popen(['powershell.exe','-NoProfile','-File',str(ROOT/'scripts/run_isaac.ps1'),
                '-Headless','--start-paused','--max-seconds','180','--output',str(evidence/'isaac-control-runner.json')],
                cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
            first=wait_for(lambda value:value.get('paused'))
            t=first['frame']['t'];time.sleep(.3)
            assert wait_for(lambda value:value.get('paused'))['frame']['t']==t
            command('step');stepped=wait_for(lambda value:value.get('paused') and value['frame']['t']>t)
            assert abs(stepped['frame']['t']-t-.1)<1e-6
            command('manual',action=[.4,.1,-.1]);wait_for(lambda value:value.get('control_mode')=='manual')
            command('retarget',landing=[1300.,-30.]);wait_for(lambda value:value['landing']==[1300.,-30.])
            command('guidance');wait_for(lambda value:value.get('control_mode')=='guidance')
            command('resume');running=wait_for(lambda value:not value.get('paused') and value['frame']['t']>stepped['frame']['t'])
            command('pause');paused=wait_for(lambda value:value.get('paused'))
            command('stop');exit_code=process.wait(timeout=150)
            assert exit_code==0,f'Native process exited {exit_code}'
            runner=json.loads((evidence/'isaac-control-runner.json').read_text());assert runner['status']=='stopped'
            report.update(status='passed',http_commands_verified=['pause','resume','step','manual','guidance','retarget','stop'],
                pause_clock_frozen=True,single_step_seconds=.1,run_seconds=running['frame']['t'],final_pause_seconds=paused['frame']['t'])
    except BaseException as error:
        report.update(status='failed',error=repr(error));raise
    finally:
        (evidence/'isaac-control-test.json').write_text(json.dumps(report,indent=2))
        if process and process.poll() is None:
            try:exchange(dict(op='command',command=dict(type='stop')));process.wait(timeout=15)
            except (OSError,subprocess.TimeoutExpired):
                subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True)
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
