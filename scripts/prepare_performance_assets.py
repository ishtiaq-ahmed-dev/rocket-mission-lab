"""Create small derivatives of the existing licensed terrain textures."""
from pathlib import Path
from PIL import Image

root=Path(__file__).resolve().parents[1]/'frontend/public/assets/terrain'
if __name__=='__main__':
    for kind in ('color','normal','roughness'):
        source=root/f'ground-{kind}.jpg';target=root/f'ground-{kind}-1k.jpg'
        with Image.open(source) as image:
            image.resize((1024,1024),Image.Resampling.LANCZOS).save(target,quality=82,optimize=True)
        print(f'{target.name}: {source.stat().st_size:,} -> {target.stat().st_size:,} bytes')
