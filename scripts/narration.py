"""Build the announcer voice track for a recorded mission video and mux it.

Reads the flight report trace, derives the real event times (liftoff, engine
cutoff, stage separation, landing burn, touchdown/end), synthesizes each
narration line with the Windows built-in TTS voices (offline, no API keys),
splices them at their event times into one WAV, then muxes it with the
recorded video via ffmpeg (falling back to Isaac's frame encoder only).

Usage:
    python scripts/narration.py --report data/isaac/flight-report.json \
        --video data/isaac/flight-report-flight.mp4 \
        --out data/isaac/mission-live.mp4
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def events_from_trace(trace: list[dict]) -> list[tuple[float, str]]:
    """Derive (time, narration) pairs from real telemetry."""
    if not trace:
        raise SystemExit('Flight report has no trace; run the recorder first')
    end = trace[-1]['t']
    out: list[tuple[float, str]] = []
    t0 = trace[0]['t']
    out.append((max(0., t0 - 1.), "Meridian 9 flight vehicle on Takeoff Pad 01. Engine chill complete. Stand by for liftoff."))

    def sample(t: float) -> dict:
        return min(trace, key=lambda x: abs(x['t'] - t))

    # Liftoff: first sample with the stack off the pad (position.z > half+2).
    liftoff = None
    for x in trace:
        if x['position'][2] > 22.:
            liftoff = x['t']
            break
    if liftoff is None:
        liftoff = end
    out.append((liftoff, "Liftoff!! Meridian 9 has cleared the tower."))

    # Engine cut before separation: throttle collapses while still climbing.
    cut = None
    for i, x in enumerate(trace):
        if x['t'] > liftoff + 5. and x['throttle'] < .05 and x['position'][2] > 100.:
            cut = x
            break
    if cut is not None:
        alt = int(cut['position'][2])
        speed = int((sum(v * v for v in cut['velocity'])) ** .5)
        out.append((cut['t'], f"Main engine cutoff confirmed. Altitude {alt} meters, speed {speed} meters per second."))

    # Separation: phase handover to landing.
    sep = None
    prev = 'takeoff'
    for x in trace:
        if x['t'] > (cut['t'] if cut else liftoff) and x['phase'] != prev:
            sep = x
            break
        prev = x['phase']
    if sep is not None:
        out.append((sep['t'], "Stage separation confirmed. The booster is released and heading back to Landing Pad 01."))

    # Landing burn: post-separation descent, engine relights hard.
    burn = None
    for x in trace:
        if (sep and x['t'] > sep['t'] or not sep) and x['throttle'] > .3 and x['position'][2] < 500.:
            burn = x
            break
    if burn is not None:
        alt = int(burn['position'][2])
        out.append((burn['t'], f"Landing burn ignition at {alt} meters. Grid fins steering, landing legs deploy."))

    dist = int(trace[-1].get('pad_distance') or 0)
    speed = int((sum(v * v for v in trace[-1]['velocity'])) ** .5)
    if trace[-1]['position'][2] < 6.:
        out.append((end, f"Touchdown on Landing Pad 01. Stack upright, {dist} meters from center, contact speed {speed} meters per second. Outstanding!"))
    else:
        alt = int(trace[-1]['position'][2])
        out.append((end, f"Terminal guidance active. {alt} meters of altitude remaining, {dist} meters from the pad, closing at {speed} meters per second."))
    return [(max(0., min(t, end - .5)), line.strip()) for t, line in out]


def synth_line(text: str, wav_path: Path, rate: int = -1, voice: str | None = None) -> None:
    ps = [
        'powershell', '-NoProfile', '-Command',
        "Add-Type -AssemblyName System.Speech;"
        "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        + (f"$s.SelectVoice('{voice}');" if voice else "")
        + f"$s.Rate={rate};"
        f"$s.SetOutputToWaveFile('{wav_path}');"
        f"$s.Speak('{text.replace(chr(39), chr(39)*2)}');"
        "$s.Dispose()"
    ]
    subprocess.run(ps, check=True, capture_output=True, shell=False)


def read_wav(path: Path) -> tuple[int, bytearray]:
    with wave.open(str(path), 'rb') as w:
        assert w.getnchannels() == 1 and w.getsampwidth() in (1, 2), 'unexpected TTS wav format'
        return w.getframerate(), bytearray(w.readframes(w.getnframes()))


def spliced_track(events: list[tuple[float, str]], workdir: Path) -> tuple[int, int, bytes, list[float]]:
    """Concat narration with silence padding so each line lands on its event."""
    workdir.mkdir(parents=True, exist_ok=True)
    tracks = []                       # (start sample, mono bytes at 22.05k)
    rate = 22050
    for i, (t, text) in enumerate(events):
        wav = workdir / f'line{i:02d}.wav'
        synth_line(text, wav)
        sr, blob = read_wav(wav)
        rate = sr
        tracks.append((int(round(t * sr)), blob))
    total = max(start + len(blob) for start, blob in tracks)
    buf = bytearray(total)
    placed: list[float] = []
    for start, blob in tracks:
        over = max(0, start - (total - len(blob)))
        start -= over
        placed.append(start / rate)
        buf[start:start + len(blob)] = blob
    return rate, 1, bytes(buf), placed


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--report', type=Path, default=ROOT / 'data/isaac/flight-report.json')
    ap.add_argument('--video', type=Path, default=None)
    ap.add_argument('--out', type=Path, default=ROOT / 'data/isaac/mission-live.mp4')
    ap.add_argument('--voice', default=None, help='Windows TTS voice, e.g. Microsoft David Desktop')
    args = ap.parse_args()

    report = json.loads(args.report.read_text())
    trace = report['trace']
    video = args.video or Path(report.get('video_artifact') or '')
    if not video.exists():
        raise SystemExit(f'video not found: {video}')
    events = events_from_trace(trace)
    rate, ch, audio, placed = spliced_track(events, ROOT / 'data/isaac/narration')
    wav_path = ROOT / 'data/isaac/mission-narration.wav'
    with wave.open(str(wav_path), 'wb') as w:
        w.setnchannels(ch)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(audio)
    print('narration events:')
    for (t, text), actual in zip(events, placed):
        print(f"  t={t:6.2f}s placed={actual:6.2f}s  {text[:70]}")
    out = args.out
    cmd = ['ffmpeg', '-y', '-i', str(video), '-i', str(wav_path),
           '-map', '0:v', '-map', '1:a', '-c:v', 'copy', '-c:a', 'aac', '-shortest', str(out)]
    subprocess.run(cmd, check=True, capture_output=True)
    print(f'wrote {out}')


if __name__ == '__main__':
    main()
