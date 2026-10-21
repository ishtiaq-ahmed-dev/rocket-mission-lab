"""Launch local workers independently of a Windows terminal/API job object."""
import base64
import os
import subprocess
import sys
from .config import ROOT
from .storage import atomic_json,read_json


def launch_job(command,folder):
    if command[1:3] not in (['-m','rocket_lab.train'],['-m','rocket_lab.campaign']):
        raise ValueError('Unsupported local worker')
    spec=folder/'launch.json'
    atomic_json(spec,dict(module=command[2],arguments=command[3:]))
    worker=[sys.executable,str(ROOT/'scripts'/'job_worker.py'),str(spec)]
    try:
        if os.name=='nt':
            encoded=base64.b64encode(subprocess.list2cmdline(worker).encode('utf-8')).decode('ascii')
            root_encoded=base64.b64encode(str(ROOT).encode('utf-8')).decode('ascii')
            script=f"$ErrorActionPreference='Stop'; $workerCommand=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{encoded}')); $workerRoot=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{root_encoded}')); $workerStartup=New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{{ShowWindow=[UInt16]0}}; $created=Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{{CommandLine=$workerCommand;CurrentDirectory=$workerRoot;ProcessStartupInformation=$workerStartup}}; if($created.ReturnValue -ne 0){{throw ('Worker launch failed: '+$created.ReturnValue)}}; Write-Output $created.ProcessId"
            payload=base64.b64encode(script.encode('utf-16le')).decode('ascii')
            result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-WindowStyle','Hidden','-EncodedCommand',payload],capture_output=True,text=True,timeout=30,check=True,creationflags=subprocess.CREATE_NO_WINDOW)
            return int(result.stdout.strip())
        with (folder/'launcher.log').open('a') as log:
            return subprocess.Popen(worker,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True).pid
    except Exception as ex:
        status=read_json(folder/'status.json',{})
        message=ex.stderr if isinstance(ex,subprocess.CalledProcessError) else str(ex)
        status.update(status='failed',error=f'Could not launch local worker: {message[-2000:]}')
        atomic_json(folder/'status.json',status)
        raise
