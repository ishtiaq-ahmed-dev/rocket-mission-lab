"""Verify/extract NVIDIA's official shared workstation package on Windows."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import time
import zipfile

EXPECTED_MD5='86dabd127e9e8c225c239b41a8e3909b'
EXPECTED_BYTES=10528731217


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=Path('D:/AppInstalled/NVIDIA/IsaacSim'))
    args=parser.parse_args();root=args.root.resolve();archive=root/'isaac-sim-6.2.0-windows.zip';target=root/'6.2.0'
    if not archive.is_file() or archive.stat().st_size!=EXPECTED_BYTES:raise RuntimeError('Official archive download is incomplete')
    print('Checking official archive checksum...',flush=True)
    digest=hashlib.md5()
    with archive.open('rb') as source:
        for block in iter(lambda:source.read(8*1024**2),b''):digest.update(block)
    if digest.hexdigest()!=EXPECTED_MD5:raise RuntimeError('Archive checksum does not match NVIDIA publication; extraction refused')
    target.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive) as package:
        entries=package.infolist();required=sum(value.file_size for value in entries)
        if shutil.disk_usage(root).free<required+10*1024**3:raise OSError('Insufficient room for runtime plus 10 GiB reserve')
        for index,entry in enumerate(entries):
            path=(target/entry.filename).resolve()
            if not path.is_relative_to(target):raise ValueError('Archive path escapes installation root')
            package.extract(entry,target)
            if index%5000==0:print(f'Extracted {index:,}/{len(entries):,} files',flush=True)
    wrappers=list(target.glob('python.bat'))
    if not wrappers:raise RuntimeError('Extracted runtime has no python.bat')
    evidence=dict(installed_at=time.time(),version='6.2.0',root=str(target),python=str(wrappers[0]),
        archive_md5=digest.hexdigest(),archive_bytes=archive.stat().st_size,source='https://downloads.isaacsim.nvidia.com/isaac-sim-standalone-6.2.0-windows-x86_64.zip')
    (root/'installation.json').write_text(json.dumps(evidence,indent=2));print(json.dumps(evidence,indent=2),flush=True)


if __name__=='__main__':main()
