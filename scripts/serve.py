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
    handles=[]
    def spawn(name,command,cwd):
        stdout=(logs/f"{name}.out.log").open("a");stderr=(logs/f"{name}.err.log").open("a");handles.extend([stdout,stderr])
        process=subprocess.Popen(command,cwd=cwd,stdout=stdout,stderr=stderr,creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0)
        return [name,command,cwd,process]
    slots=[]
    try:
        for name,command,cwd in commands:slots.append(spawn(name,command,cwd))
        while True:
            for index,(name,command,cwd,process) in enumerate(slots):
                # Keep the service up without a terminal: restart a child that exits.
                if process.poll() is not None:
                    time.sleep(2)
                    slots[index]=spawn(name,command,cwd)
            state={"pid":os.getpid(),"mode":"development" if args.development else "production preview","updated_at":time.time(),"restarts":len(handles)//2-len(slots),
                   "services":{slot[0]:{"pid":slot[3].pid,"returncode":slot[3].poll()} for slot in slots}}
            atomic_json(logs/"services.json",state)
            time.sleep(5)
    except KeyboardInterrupt:pass
    finally:
        for _,_,_,process in slots:
            if process.poll() is None:process.terminate()
        for handle in handles:handle.close()

if __name__=="__main__":main()
