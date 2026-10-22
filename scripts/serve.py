"""Keep loopback services supervised outside an interactive terminal's lifetime.

Run normally in a terminal, or launch this file through Win32_Process.Create
on Windows to keep its process tree independent of the caller's job object.
"""
from pathlib import Path
import argparse
import os
import shutil
import subprocess
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from rocket_lab.config import ROOT
from rocket_lab.storage import atomic_json

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--development',action='store_true');args=parser.parse_args()
    logs=ROOT/"logs";logs.mkdir(exist_ok=True)
    if not args.development and not (ROOT/"frontend"/"dist"/"index.html").exists():raise RuntimeError("Build the frontend with npm run build before starting the production preview")
    if args.development:
        node=shutil.which("node")
        if not node:raise RuntimeError("Node.js is required for development")
        frontend=[node,str(ROOT/'frontend/node_modules/vite/bin/vite.js'),'--host','127.0.0.1','--port','5180','--strictPort']
        commands=[('backend',[sys.executable,'-m','uvicorn','rocket_lab.api:app','--host','127.0.0.1','--port','8010'],ROOT),('frontend',frontend,ROOT/'frontend')]
    else:
        commands=[('preview',[sys.executable,'-m','uvicorn','rocket_lab.preview:app','--host','127.0.0.1','--port','5180'],ROOT)]
    processes=[];handles=[]
    try:
        for name,command,cwd in commands:
            stdout=(logs/f"{name}.out.log").open("w");stderr=(logs/f"{name}.err.log").open("w");handles.extend([stdout,stderr])
            process=subprocess.Popen(command,cwd=cwd,stdout=stdout,stderr=stderr,creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0)
            processes.append((name,process))
        while True:
            state={"pid":os.getpid(),"mode":"development" if args.development else "production preview","updated_at":time.time(),"services":{name:{"pid":p.pid,"returncode":p.poll()} for name,p in processes}}
            atomic_json(logs/"services.json",state)
            if any(p.poll() is not None for _,p in processes):break
            time.sleep(5)
    except KeyboardInterrupt:pass
    finally:
        for _,process in processes:
            if process.poll() is None:process.terminate()
        for handle in handles:handle.close()

if __name__=="__main__":main()
