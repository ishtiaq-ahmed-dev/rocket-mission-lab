"""Run local checks: the Python suite, the flight model invariants and the production frontend build."""
from pathlib import Path
import os
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]


def main():
    npm="npm.cmd" if os.name=="nt" else "npm"
    node=shutil.which("node")
    if not node or not shutil.which(npm):
        print('Node.js and npm are required to validate the shipped flight and build.',file=sys.stderr)
        return 1
    commands=[([sys.executable,"-m","pytest","-q"],ROOT)]
    commands.append(([node,"scripts/check_standards.js"],ROOT))
    commands.append(([node,"scripts/check_flight.js"],ROOT))
    commands.append(([node,"--test","scripts/check_regressions.js"],ROOT))
    commands.append(([npm,"run","build"],ROOT/"frontend"))
    for command,cwd in commands:
        if subprocess.run(command,cwd=cwd).returncode:return 1
    return 0


if __name__=="__main__":sys.exit(main())
