"""Install the optional CC0 daylight HDRI into the shared Isaac asset directory."""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request

NAME='kloofendal_48d_partly_cloudy_puresky_2k.hdr'
URL='https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/2k/'+NAME
SHA256='5244534e9cf5b606f2ff513aa00ddb161b0a4826ffd88a0d3bd03ac29247d198'


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--assets',type=Path,default=Path('D:/AppInstalled/NVIDIA/IsaacSim/assets'))
    args=parser.parse_args();args.assets.mkdir(parents=True,exist_ok=True)
    destination=args.assets/NAME
    if not destination.exists():
        partial=destination.with_suffix('.download')
        try:
            request=urllib.request.Request(URL,headers={'User-Agent':'RocketMissionLab/1.0'})
            with urllib.request.urlopen(request,timeout=60) as source,partial.open('wb') as target:
                total=0
                while block:=source.read(1024*1024):
                    total+=len(block)
                    if total>8*1024*1024:raise ValueError('Sky download exceeded expected size')
                    target.write(block)
            if hashlib.sha256(partial.read_bytes()).hexdigest()!=SHA256:
                raise ValueError('Sky checksum mismatch; installation refused')
            partial.replace(destination)
        finally:partial.unlink(missing_ok=True)
    if hashlib.sha256(destination.read_bytes()).hexdigest()!=SHA256:
        raise ValueError('Existing shared sky differs from the pinned asset; left unchanged')
    manifest=dict(file=str(destination),sha256=SHA256,download=URL,
        source='https://polyhaven.com/a/kloofendal_48d_partly_cloudy_puresky',
        authors=['Greg Zaal','Jarod Guest'],license='CC0',license_url='https://polyhaven.com/license')
    (args.assets/'sky-manifest.json').write_text(json.dumps(manifest,indent=2))
    print(json.dumps(manifest,indent=2))


if __name__=='__main__':main()
