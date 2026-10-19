"""Keep loopback services supervised outside an interactive terminal's lifetime.

Run normally in a terminal, or launch this file through Win32_Process.Create
on Windows to keep its process tree independent of the caller's job object.
"""
from pathlib import Path
import os
import shutil
import subprocess
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from rocket_lab.config import ROOT
from rocket_lab.storage import atomic_json

def main():
    logs=ROOT/"logs";logs.mkdir(exist_ok=True)
    node=shutil.which("node")
    if not node:raise RuntimeError("Node.js is required")
    commands=[("backend",[sys.executable,"-m","uvicorn","rocket_lab.api:app","--host","127.0.0.1","--port","8010"],ROOT),
              ("frontend",[node,str(ROOT/"frontend"/"node_modules"/"vite"/"bin"/"vite.js"),"--host","127.0.0.1"],ROOT/"frontend")]
    processes=[];handles=[]
    try:
        for name,command,cwd in commands:
            stdout=(logs/f"{name}.out.log").open("w");stderr=(logs/f"{name}.err.log").open("w");handles.extend([stdout,stderr])
            process=subprocess.Popen(command,cwd=cwd,stdout=stdout,stderr=stderr,creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0)
            processes.append((name,process))
        while True:
            state={"pid":os.getpid(),"updated_at":time.time(),"services":{name:{"pid":p.pid,"returncode":p.poll()} for name,p in processes}}
            atomic_json(logs/"services.json",state)
            if any(p.poll() is not None for _,p in processes):break
            time.sleep(2)
    except KeyboardInterrupt:pass
    finally:
        for _,process in processes:
            if process.poll() is None:process.terminate()
        for handle in handles:handle.close()

if __name__=="__main__":main()
