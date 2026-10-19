"""One cross-platform launcher. python scripts/dev.py; Ctrl+C shuts down servers."""
from pathlib import Path
import os
import signal
import subprocess
import sys
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]

def main():
    npm="npm.cmd" if os.name=="nt" else "npm"
    processes=[]
    try:
        for port in [8010,5180]:
            try:urllib.request.urlopen(f"http://127.0.0.1:{port}",timeout=1)
            except urllib.error.HTTPError:raise SystemExit(f"Port {port} is already serving an app. Use the running server or stop it first.")
            except (OSError,TimeoutError):continue
            raise SystemExit(f"Port {port} is already serving an app. Open http://127.0.0.1:5180 if Rocket Mission Lab is running.")
        processes.append(subprocess.Popen([sys.executable,"-m","uvicorn","rocket_lab.api:app","--host","127.0.0.1","--port","8010"],cwd=ROOT))
        processes.append(subprocess.Popen([npm,"run","dev"],cwd=ROOT/"frontend"))
        print("\nRocket Mission Lab: http://127.0.0.1:5180\nAPI: http://127.0.0.1:8010/docs\nCtrl+C stops the web servers. Training jobs are independent.\n",flush=True)
        while all(p.poll() is None for p in processes):time.sleep(.5)
    except KeyboardInterrupt:pass
    finally:
        for process in processes:
            if process.poll() is None:process.terminate()

if __name__=="__main__":main()
