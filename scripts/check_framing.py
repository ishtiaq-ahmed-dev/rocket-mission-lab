"""Offline framing check: every shot must keep the vehicle and flame in gate."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from rocket_lab.config import load_config
from rocket_lab.isaac.cinematic import CameraDirector, FlightTrack

cfg = load_config()
track = FlightTrack.load('data/isaac/film/track.npz')
director = CameraDirector(cfg, track, 20.0)

worst = 0.0
for start, end, fn, focal, name in director.shots:
    rows = []
    for u in np.linspace(0, .999, 9):
        time_s = start + (end - start) * u
        eye, target, f = director.frame(time_s)
        subject = director._subject(time_s)
        points = subject['detail_points'] if name == 'stage_separation' else subject['points']
        frame_need = director._need(eye, target, f, points)
        worst = max(worst, frame_need)
        rows.append((time_s, frame_need, np.linalg.norm(eye - target), eye[2],
                     float(subject['state']['position'][2])))
    print(f'{name:17s} focal={focal:4.0f} ' + ' '.join(
        f'{r[1]:.2f}' for r in rows))
    print(f'{"":17s} dist  ' + ' '.join(f'{r[2]:5.0f}' for r in rows))
    print(f'{"":17s} eyeZ  ' + ' '.join(f'{r[3]:5.0f}' for r in rows))
    print(f'{"":17s} vehZ  ' + ' '.join(f'{r[4]:5.0f}' for r in rows))
print(f'worst fill = {worst:.3f} (1.0 would touch the gate edge)')
print('film seconds', round(director.timeline.duration, 2))
print('events', director.film_events())
