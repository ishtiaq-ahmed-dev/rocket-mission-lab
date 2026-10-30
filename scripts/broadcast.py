"""Turn the silent cinematic film into a broadcast segment.

Adds what a real launch webcast has and a raw render lacks:
  * an on-screen telemetry strip keyed to the actual flight track
  * mission-clock and callouts (liftoff, staging, boostback, landing burn)
  * an announcer voice reading the real numbers (Kokoro neural TTS offline,
    with Windows SAPI as the fallback when the model is not installed)
  * an engine bed whose loudness follows recorded throttle

The film is a highlight edit: coasts are time-compressed, so every overlay
and line is placed on the *film* clock by inverting the edit timeline saved
next to the video.

Usage:
    python scripts/broadcast.py --track data/isaac/film/track.npz \
        --meta videos/mission-film-meta.json --video videos/mission-film.mp4 \
        --out videos/meridian9-flight-test.mp4
"""
from __future__ import annotations

import argparse
import json
import math
import random
import shutil
import struct
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
RATE = 24000
VOICE = 'am_michael'


class Film:
    """Edit timeline loaded from the render metadata."""

    def __init__(self, meta):
        self.segments = meta['timeline']
        self.duration = float(meta['film_seconds'])
        self.width = int(meta.get('width', 1920))
        self.height = int(meta.get('height', 1080))
        self.fps = float(meta.get('fps', 60))
        self.events = meta['events']
        self.event_track = meta.get('event_track', {})
        self.shots = meta.get('shots', [])

    def track_time(self, film_time):
        film_time = max(0., min(self.duration, film_time))
        for seg in self.segments:
            if film_time <= seg['film_end'] + 1e-9:
                return seg['track_start'] + (film_time - seg['film_start']) * seg['speed']
        return self.segments[-1]['track_end']

    def speed_at(self, film_time):
        for seg in self.segments:
            if seg['film_start'] <= film_time <= seg['film_end']:
                return seg['speed']
        return 1.

    def film_time(self, track_time):
        for seg in self.segments:
            if track_time <= seg['track_end']:
                return seg['film_start'] + (max(seg['track_start'], track_time) - seg['track_start']) / seg['speed']
        return self.duration


class Telemetry:
    def __init__(self, npz, film):
        blob = np.load(npz)
        self.t = blob['t']
        self.position = blob['position']
        self.velocity = blob['velocity']
        self.quaternion = blob['quaternion']
        self.throttle = blob['throttle']
        self.phase = blob['phase']
        self.film = film
        # Pad centre = booster position after settling at the end of the track.
        self.pad = self.position[-1][:2].copy()
        self.stand = 20.0

    def at(self, film_time):
        t = self.film.track_time(film_time)
        index = int(np.searchsorted(self.t, t))
        index = max(1, min(index, len(self.t) - 1))
        t0, t1 = self.t[index - 1], self.t[index]
        u = float(np.clip((t - t0) / max(t1 - t0, 1e-9), 0., 1.))
        pos = self.position[index - 1] * (1 - u) + self.position[index] * u
        vel = self.velocity[index - 1] * (1 - u) + self.velocity[index] * u
        throttle = float(self.throttle[index - 1] * (1 - u) + self.throttle[index] * u)
        tilt = math.degrees(math.acos(float(np.clip(self._up(index - 1, u)[2], -1, 1))))
        return dict(t=t, position=pos, velocity=vel, throttle=throttle,
                    altitude=max(0., float(pos[2] - self.stand)),
                    speed=float(np.linalg.norm(vel)), tilt=tilt,
                    pad_distance=float(np.linalg.norm(pos[:2] - self.pad)))

    def summary(self):
        """Real numbers for the end card, straight from the recorded track."""
        altitude = self.position[:, 2] - self.stand
        speed = np.linalg.norm(self.velocity, axis=1)
        return dict(apogee=float(altitude.max()), max_speed=float(speed.max()),
                    touchdown_speed=float(speed[-1]),
                    miss=float(np.linalg.norm(self.position[-1][:2] - self.pad)))

    def _up(self, index, u):
        q0, q1 = self.quaternion[index], self.quaternion[min(index + 1, len(self.t) - 1)]
        q = q0 * (1 - u) + q1 * u
        w, x, y, z = q / max(np.linalg.norm(q), 1e-9)
        return np.array([2 * (x * z + w * y), 2 * (y * z - w * x), 1 - 2 * (x * x + y * y)])


def ass_time(t):
    h = int(t // 3600)
    m = int(t % 3600 // 60)
    s = t % 60
    return f'{h}:{m:02d}:{s:05.2f}'


# Broadcast palette (ASS is BGR, so these read right-to-left).
WHITE = '&H00FFFFFF'
GREY = '&H00B4B4B4'
DIM = '&H00909090'
AMBER = '&H0022A8FF'      # #FFA822
PANEL = '&H00110F0D'


def draw_box(x, y, w, h, colour=PANEL, alpha='40'):
    return (f'{{\\an7\\pos({int(x)},{int(y)})\\p1\\c{colour}\\alpha&H{alpha}&}}'
            f'm 0 0 l {int(w)} 0 l {int(w)} {int(h)} l 0 {int(h)}{{\\p0}}')


def build_overlay(film, telemetry, path: Path):
    """Network-style graphics: bug, clock, telemetry panel, chapters, callouts."""
    W, H = film.width, film.height
    s = H / 1080.
    px = lambda value: int(round(value * s))
    left, right = px(64), W - px(64)
    rows = []
    add = lambda layer, start, stop, style, text: rows.append((layer, start, stop, style, text))

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Title,Arial,{px(42)},&H00FFFFFF,&H00FFFFFF,&H00101010,&H90000000,1,0,0,0,100,100,0,0,1,2,0,7,0,0,0,1
Style: Sub,Arial,{px(18)},&H00C8C8C8,&H00FFFFFF,&H00101010,&H90000000,0,0,0,0,100,100,{px(2)},0,1,1,0,7,0,0,0,1
Style: Chip,Arial,{px(15)},&H00FFFFFF,&H00FFFFFF,&H00101010,&H90000000,1,0,0,0,100,100,{px(2)},0,3,0,0,7,{px(11)},{px(11)},0,1
Style: Clock,Consolas,{px(27)},&H00FFFFFF,&H00FFFFFF,&H00101010,&H90000000,0,0,0,0,100,100,0,0,1,2,0,9,0,0,0,1
Style: Label,Arial,{px(13)},&H00949494,&H00FFFFFF,&H00101010,&H90000000,0,0,0,0,100,100,{px(3)},0,1,0,0,7,0,0,0,1
Style: Value,Consolas,{px(31)},&H00FFFFFF,&H00FFFFFF,&H00101010,&H90000000,1,0,0,0,100,100,0,0,1,1,0,7,0,0,0,1
Style: Chapter,Arial,{px(25)},&H00FFFFFF,&H00FFFFFF,&H00101010,&H90000000,1,0,0,0,100,100,{px(2)},0,1,2,0,9,0,0,0,1
Style: ChapterSub,Arial,{px(14)},&H00B4B4B4,&H00FFFFFF,&H00101010,&H90000000,0,0,0,0,100,100,{px(3)},0,1,1,0,9,0,0,0,1
Style: Callout,Arial,{px(56)},&H00FFFFFF,&H00FFFFFF,&H00101010,&H90000000,1,0,0,0,100,100,{px(3)},0,1,3,0,2,0,0,0,1
Style: Badge,Consolas,{px(17)},&H00FFFFFF,&H00FFFFFF,&H00101010,&H90000000,1,0,0,0,100,100,{px(2)},0,3,0,0,8,{px(11)},{px(11)},0,1
Style: EndTitle,Arial,{px(50)},&H00FFFFFF,&H00FFFFFF,&H00101010,&H90000000,1,0,0,0,100,100,{px(2)},0,1,2,0,5,0,0,0,1
Style: EndSub,Consolas,{px(21)},&H00C8C8C8,&H00FFFFFF,&H00101010,&H90000000,0,0,0,0,100,100,0,0,1,0,0,5,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    # ---- persistent brand block ------------------------------------------
    add(1, .4, film.duration, 'Title', draw_box(left, px(44), px(5), px(74), AMBER, '00'))
    add(0, .4, film.duration, 'Title', f'{{\pos({left + px(18)},{px(40)})}}MERIDIAN 9')
    add(0, .4, film.duration, 'Sub', f'{{\pos({left + px(19)},{px(92)})}}FLIGHT TEST 01 · LAUNCH COMPLEX ONE')
    add(0, .4, film.duration, 'Chip', f'{{\pos({right},{px(44)})}}SIMULATION')

    # ---- telemetry panel --------------------------------------------------
    panel_w, panel_h = px(404), px(212)
    panel_x, panel_y = left, H - px(56) - panel_h
    add(1, .4, film.duration, 'Label', draw_box(panel_x, panel_y, panel_w, panel_h))
    add(2, .4, film.duration, 'Label', draw_box(panel_x, panel_y, px(3), panel_h, AMBER, '00'))

    step = .25
    fields = [('ALTITUDE', lambda f: f"{f['altitude'] / 1000.:.3f} km"),
              ('VELOCITY', lambda f: f"{f['speed']:,.0f} m/s"),
              ('DOWNRANGE', lambda f: f"{f['pad_distance'] / 1000.:.2f} km"),
              ('THROTTLE', lambda f: f"{f['throttle'] * 100.:.0f} %")]
    t = 0.
    while t < film.duration:
        frame = telemetry.at(t + step * .5)
        stop = min(t + step * 1.06, film.duration)
        for index, (label, fmt) in enumerate(fields):
            row_y = panel_y + px(22) + index * px(46)
            add(0, t, stop, 'Label', f"{{\pos({panel_x + px(20)},{row_y})}}{label}")
            add(0, t, stop, 'Value', f"{{\pos({panel_x + px(146)},{row_y - px(13)})}}{fmt(frame)}")
        clock = frame['t']
        add(0, t, stop, 'Clock', f"{{\pos({right},{px(82)})}}T+ {int(clock // 60):02d}:{clock % 60:04.1f}")
        t += step

    # ---- chapter cards, one per camera cut --------------------------------
    chapters = {'pad_ignition': ('PAD CAMERA 01', 'Launch Complex One'),
                'liftoff_track': ('TRACKING CAM 02', 'Liftoff and climb'),
                'ascent_chase': ('TRACKING CAM 03', 'Vehicle ascent'),
                'stage_separation': ('ENGINE CAM 04', 'Stage separation'),
                'booster_flip': ('TRACKING CAM 05', 'Booster flip'),
                'descent_chase': ('TRACKING CAM 06', 'Return descent'),
                'landing_burn': ('GROUND CAM 07', 'Landing burn'),
                'touchdown': ('GROUND CAM 08', 'Touchdown'),
                'recovered': ('RECOVERY 09', 'Booster recovered')}
    for shot in film.shots:
        title, sub = chapters.get(shot['name'], (shot['name'].upper(), ''))
        add(0, shot['start'] + .1, shot['end'] - .05, 'Chapter',
            f"{{\pos({right},{H - px(126)})}}{title}")
        add(0, shot['start'] + .1, shot['end'] - .05, 'ChapterSub',
            f"{{\pos({right},{H - px(90)})}}{sub}")

    bucket = 0.
    while bucket < film.duration:
        speed = film.speed_at(bucket + .3)
        if speed > 1.5:
            add(0, bucket, min(bucket + 1., film.duration), 'Badge',
                f'{{\pos({W // 2},{px(42)})}}PLAYBACK {speed:.0f}x')
        bucket += 1.

    callouts = [('liftoff', 'LIFTOFF'), ('separation', 'STAGE SEPARATION'),
                ('boostback', 'BOOSTBACK IGNITION'), ('landing_burn', 'LANDING BURN'),
                ('touchdown', 'TOUCHDOWN')]
    for key, text in callouts:
        at = film.events.get(key)
        if at is None:
            continue
        start, stop = max(0., at - .15), min(film.duration, at + 3.4)
        add(0, start, stop, 'Callout', f"{{\pos({W // 2},{int(H * .58)})}}{text}")
        add(1, start, stop, 'Label',
            draw_box(W / 2 - px(170), H * .58 + px(64), px(340), px(3), AMBER, '00'))

    # ---- end card ---------------------------------------------------------
    end_at = max(0., film.duration - 4.8)
    stats = telemetry.summary()
    add(1, end_at, film.duration, 'Label', draw_box(0, 0, W, H, '&H00000000', '26'))
    add(0, end_at + .25, film.duration, 'EndTitle', 'MERIDIAN 9  ·  FLIGHT TEST 01')
    add(0, end_at + .55, film.duration, 'EndSub',
        f"APOGEE {stats['apogee'] / 1000.:.2f} km    MAX SPEED {stats['max_speed']:,.0f} m/s    "
        f"TOUCHDOWN {stats['touchdown_speed']:.1f} m/s    MISS {stats['miss']:.2f} m")

    with path.open('w', encoding='utf-8') as fh:
        fh.write(header)
        for layer, start, stop, style, text in rows:
            if stop <= start:
                continue
            fh.write(f'Dialogue: {layer},{ass_time(start)},{ass_time(stop)},{style},,0,0,0,,{text}\n')


def speak_kokoro(text, out: Path):
    from kokoro_onnx import Kokoro
    import soundfile as sf
    model = ROOT / 'data/models/kokoro/kokoro-v1.0.fp16.onnx'
    voices = ROOT / 'data/models/kokoro/voices-v1.0.bin'
    kokoro = Kokoro(str(model), str(voices))
    samples, rate = kokoro.create(text, voice=VOICE, speed=1.02, lang='en-us')
    sf.write(str(out), samples, rate, subtype='PCM_16')
    return rate


def speak_sapi(text, out: Path):
    ps = 'Add-Type -AssemblyName System.Speech;' \
         '$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;' \
         '$s.Rate=-1;' \
         f"$s.SetOutputToWaveFile('{out}');" \
         f"$s.Speak('{text.replace(chr(39), chr(39) * 2)}');" \
         '$s.Dispose()'
    subprocess.run(['powershell', '-NoProfile', '-Command', ps], check=True, capture_output=True)
    return RATE


def read_wav(path: Path):
    with wave.open(str(path), 'rb') as w:
        assert w.getnchannels() == 1 and w.getsampwidth() == 2
        return w.getframerate(), bytearray(w.readframes(w.getnframes()))


def narration_lines(film, telemetry):
    """Commentary cue sheet: times are on the film clock, numbers are real."""
    ev = film.events
    at = lambda seconds: max(0.25, float(seconds))
    def frame(seconds): return telemetry.at(max(0., float(seconds)))
    lines = [(.5, 'Meridian 9 is on the pad at Launch Complex One, counting down to Flight Test One.')]
    if ev.get('liftoff') is not None:
        lines.append((at(ev['liftoff'] - .3), 'Ignition. And liftoff!')
                     )
        f = frame(ev['liftoff'] + 4.2)
        lines.append((at(ev['liftoff'] + 3.4),
                      f"Meridian 9 is climbing through {int(f['altitude'])} meters, "
                      f"velocity {int(f['speed'])} meters per second."))
    if ev.get('separation') is not None:
        lines.append((at(ev['separation'] - 4.2), 'Coming up on main engine cutoff and stage separation.'))
        lines.append((at(ev['separation'] + .3),
                      'Separation confirmed. The upper stage is away, and the booster is beginning its flip.'))
    if ev.get('boostback') is not None:
        f = frame(ev['boostback'] + 2.6)
        lines.append((at(ev['boostback'] + .6),
                      f"Boostback ignition. The booster is reversing course toward Landing Pad One, "
                      f"{f['pad_distance'] / 1000.:.1f} kilometers out."))
    if ev.get('landing_burn') is not None:
        f = frame(ev['landing_burn'] + 1. - 1.)
        lines.append((at(ev['landing_burn'] + .4),
                      f"Landing burn ignition at {int(f['altitude'])} meters. Grid fins are steering her to the pad."))
    if ev.get('touchdown') is not None:
        f = frame(ev['touchdown'])
        lines.append((at(ev['touchdown'] + .2),
                      f"Touchdown! Meridian 9 is upright on Landing Pad One, {f['pad_distance']:.1f} meters from center."))
    lines.append((at(film.duration - 5.4),
                  'This flight was simulated in Isaac Sim with PhysX physics, from the same guidance that flies the vehicle.'))
    return lines


def build_narration(lines, workdir: Path, out: Path):
    workdir.mkdir(parents=True, exist_ok=True)
    placed, blobs, rate = [], [], RATE
    use_kokoro = (ROOT / 'data/models/kokoro/kokoro-v1.0.fp16.onnx').exists()
    for i, (t, text) in enumerate(lines):
        wav = workdir / f'line{i}.wav'
        try:
            rate = speak_kokoro(text, wav) if use_kokoro else speak_sapi(text, wav)
        except Exception as error:
            print(f'announcer fallback to SAPI ({type(error).__name__}: {error})', flush=True)
            rate = speak_sapi(text, wav)
        sample_rate, blob = read_wav(wav)
        if sample_rate != RATE:
            # Kokoro is 24 kHz; SAPI is 22.05 kHz. Resample is avoided by
            # writing the final bed at the first successful voice rate.
            blobs = [(start * RATE / sample_rate, b) for start, b in blobs]
            blobs = [(int(s), b) for s, b in blobs]
        blobs.append((int(t * RATE), blob))
        placed.append(t)
    total = max(start + len(blob) for start, blob in blobs)
    buf = bytearray(total)
    for start, blob in blobs:
        start = max(0, min(start, total - len(blob)))
        buf[start:start + len(blob)] = blob
    with wave.open(str(out), 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(bytes(buf))
    return placed


def build_bed(film, telemetry, out: Path):
    """Engine rumble plus wind, following the recorded throttle on the film clock."""
    n = int((film.duration + .5) * RATE)
    rnd = random.Random(9)
    brown = lp = wind = 0.
    buf = bytearray(n * 2)
    telemetry.at(0.)
    for i in range(n):
        t = i / RATE
        frame = telemetry.at(t)
        throttle = max(0., min(1., frame['throttle']))
        speed = frame['speed']
        brown = .985 * brown + .05 * rnd.uniform(-1., 1.)
        lp = .86 * lp + .14 * brown
        wind = .995 * wind + .0025 * rnd.uniform(-1., 1.)
        crackle = rnd.uniform(-1., 1.) * .22 * max(0., throttle - .6)
        engine = (lp * .9 + crackle) * ((throttle ** 1.7) * .55 + .01)
        airflow = wind * min(1., speed / 320.) * .22
        sample = int(max(-1., min(1., (engine + airflow) * 9000.)))
        struct.pack_into('<h', buf, i * 2, sample)
    with wave.open(str(out), 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(bytes(buf))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--track', type=Path, default=ROOT / 'data/isaac/film/track.npz')
    ap.add_argument('--meta', type=Path, default=ROOT / 'videos/mission-film-meta.json')
    ap.add_argument('--video', type=Path, default=ROOT / 'videos/mission-film.mp4')
    ap.add_argument('--out', type=Path, default=ROOT / 'videos/meridian9-flight-test.mp4')
    ap.add_argument('--work', type=Path, default=ROOT / 'data/isaac/broadcast')
    ap.add_argument('--keep-mute', action='store_true')
    args = ap.parse_args()
    if not args.video.exists():
        raise SystemExit(f'film not found: {args.video}')
    meta = json.loads(args.meta.read_text())
    film = Film(meta)
    telemetry = Telemetry(args.track, film)
    args.work.mkdir(parents=True, exist_ok=True)
    ass = args.work / 'overlay.ass'
    build_overlay(film, telemetry, ass)
    lines = narration_lines(film, telemetry)
    voice = args.work / 'voice.wav'
    placed = build_narration(lines, args.work / 'lines', voice)
    bed = args.work / 'bed.wav'
    build_bed(film, telemetry, bed)
    print('announcer:')
    for (t, text) in lines:
        print(f'  {t:6.2f}s  {text}')
    # Broadcast grade: a touch more contrast and saturation than the raw RTX
    # frame, plus a light sharpen. The overlay is referenced relatively so
    # libass never has to parse a Windows drive colon.
    grade = ('eq=contrast=1.06:saturation=1.12:gamma=1.01,'
             'unsharp=5:5:0.35:5:5:0.0')
    cmd = ['ffmpeg', '-y', '-fflags', '+genpts', '-i', str(args.video.resolve()),
           '-i', str(voice.resolve()), '-i', str(bed.resolve()),
           '-filter_complex',
           f"[0:v]{grade},ass=overlay.ass[v];[1:a]volume=1.0[voice];[2:a]volume=0.5[bed];"
           f"[voice][bed]amix=inputs=2:duration=longest:normalize=0,alimiter=limit=0.95,"
           f"aresample={RATE}[a]",
           '-map', '[v]', '-map', '[a]', '-t', f'{film.duration:.3f}',
           '-c:v', 'libx264', '-crf', '19', '-preset', 'medium', '-pix_fmt', 'yuv420p',
           '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709',
           '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', str(args.out.resolve())]
    subprocess.run(cmd, check=True, cwd=args.work)
    print(f'wrote {args.out}  ({film.duration:.1f} s)')


if __name__ == '__main__':
    main()
