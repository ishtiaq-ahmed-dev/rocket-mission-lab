"""Run local checks. Browser integration is opt-in when browser policy permits."""
from pathlib import Path
import argparse
import os
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
def main():
    parser=argparse.ArgumentParser();parser.add_argument("--browser",action="store_true");args=parser.parse_args()
    npm="npm.cmd" if os.name=="nt" else "npm"
    commands=[([sys.executable,"-m","pytest","-q"],ROOT),([npm,"run","typecheck"],ROOT/"frontend"),([npm,"run","lint"],ROOT/"frontend"),([npm,"test"],ROOT/"frontend"),([npm,"run","build"],ROOT/"frontend")]
    if args.browser:commands.append(([npm,"run","test:e2e"],ROOT/"frontend"))
    for command,cwd in commands:
        result=subprocess.run(command,cwd=cwd)
        if result.returncode:return result.returncode
    return 0
if __name__=="__main__":sys.exit(main())
