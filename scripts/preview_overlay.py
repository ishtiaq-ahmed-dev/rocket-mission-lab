"""Render overlay stills over a neutral plate to check broadcast typography."""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

from rocket_lab.config import load_config
from rocket_lab.isaac.cinematic import CameraDirector, FlightTrack
import broadcast

cfg = load_config()
track = FlightTrack.load(ROOT / 'data/isaac/film/track.npz')
director = CameraDirector(cfg, track, 20.0)
meta = director.export()
meta.update(fps=30.0, width=1920, height=1080, film_seconds=director.timeline.duration)
work = ROOT / 'data/isaac/broadcast'
work.mkdir(parents=True, exist_ok=True)
(work / 'meta-preview.json').write_text(json.dumps(meta, indent=2))

film = broadcast.Film(meta)
telemetry = broadcast.Telemetry(ROOT / 'data/isaac/film/track.npz', film)
broadcast.build_overlay(film, telemetry, work / 'overlay.ass')
print('events', film.events)
print('duration', film.duration)
print('shots', [(s['name'], s['start'], s['end']) for s in film.shots])

plate = ROOT / 'data/ref/plate.png'
subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
                'color=c=0x2b3a4a:s=1920x1080', '-frames:v', '1', str(plate)], check=True)
for t in (2.0, 12.0, 40.0, 70.0, 79.0):
    out = ROOT / f'data/ref/overlay-{t:05.1f}.png'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-loop', '1', '-i', str(plate),
                    '-vf', f"ass=overlay.ass", '-ss', f'{t:.2f}', '-frames:v', '1',
                    str(out)], check=True, cwd=work)
    print('wrote', out)
