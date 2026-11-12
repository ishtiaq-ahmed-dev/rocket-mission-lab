"""Generate the README figures from the shipped simulator and network, in light and dark variants.

    python scripts/readme_figures.py [--cached]

Writes docs/assets/{mission-profile,touchdown,fault-recovery}-{light,dark}.svg. Needs Node: the simulator
is the JavaScript embedded in frontend/index.html. The touchdown figure flies the 1,300 held-out flights
(seeds 900000-900299 and 910000-910999) in parallel, which takes a few minutes; --cached restyles from the
last run's flight data (data/flight-policy/figures-data.json).
"""
import json
import subprocess
import sys
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Rectangle

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs' / 'assets'
CACHE = ROOT / 'data' / 'flight-policy' / 'figures-data.json'

# Forced engine faults during the landing burn, 100 dispersed flights each (seeds 620000-620099),
# measured with the shipped network, the previous one and the teacher (docs/FLIGHT-POLICY.md, "Engine faults").
FAULTS = [('Engine out 1 s at 2,500 m', 100, 0, 100), ('Engine out 1 s at 1,500 m', 99, 0, 100),
          ('Three engines 0.8 s at 250 m', 100, 25, 100), ('Three engines 0.8 s at 120 m', 100, 0, 100)]

# Reference palette (validated on GitHub's white and #0d1117 pages); text never takes a series colour.
THEMES = {
    'light': dict(series=['#2a78d6', '#eb6834', '#1baf7a'], ink='#0b0b0b', ink2='#52514e', muted='#898781',
                  grid='#e1e0d9', axis='#c3c2b7', gap='#ffffff'),
    'dark': dict(series=['#3987e5', '#d95926', '#199e70'], ink='#f0efec', ink2='#c3c2b7', muted='#898781',
                 grid='#2c2c2a', axis='#383835', gap='#0d1117'),
}

NODE = r"""
const path = require('path'), root = process.argv[1];
const { loadSim, POLICY_FILE } = require(path.join(root, 'scripts/flight_policy/sim'));
const { runSeeds } = require(path.join(root, 'scripts/flight_policy/parallel'));
const FS = loadSim(), _ = FS._, net = FS.neuralController(globalThis.FLIGHT_POLICY), track = [];
let next = -10;
const sim = FS.run({ stopWhen: (B, U, t) => B.landed && U.seco && t > U.tSeco + 62, controller: ctx => {
  if (ctx.t >= next) { next = ctx.t + 1;
    track.push([ctx.t, (_.nrm(ctx.B.r) - FS.RE) / 1000, ctx.U.separated ? (_.nrm(ctx.U.r) - FS.RE) / 1000 : null]); }
  return net(ctx); } });
const seeds = [...Array(300).keys()].map(i => 900000 + i).concat([...Array(1000).keys()].map(i => 910000 + i));
runSeeds(path.join(root, 'data/flight-policy/eval'), 'figures', seeds, { fly: 'policy', policyFile: POLICY_FILE }).then(rows => {
  process.stdout.write(JSON.stringify({ track, events: sim.events.map(e => [e.name, e.t]),
    touchdowns: rows.map(r => [r.errE, r.errN, r.vV, r.success && r.orbit && r.deploy && r.fairing]) }));
});
"""


def style(ax, th, grid_axis='y'):
    ax.set_facecolor('none')
    for side in ('top', 'right'):
        ax.spines[side].set_visible(False)
    for side in ('left', 'bottom'):
        ax.spines[side].set_color(th['axis'])
    ax.tick_params(colors=th['muted'], labelcolor=th['ink2'], length=0, labelsize=9.5)
    if grid_axis:
        ax.grid(axis=grid_axis, color=th['grid'], linewidth=0.8)
        ax.set_axisbelow(True)


def title(fig, th, text, sub):
    fig.text(0.012, 0.965, text, color=th['ink'], fontsize=13, fontweight='bold', va='top')
    fig.text(0.012, 0.895, sub, color=th['ink2'], fontsize=10, va='top')


def save(fig, name, mode):
    fig.savefig(OUT / f'{name}-{mode}.svg', transparent=True, metadata={'Date': None})
    plt.close(fig)


def profile(data, mode):
    th = THEMES[mode]
    fig, ax = plt.subplots(figsize=(10, 4.4))
    fig.subplots_adjust(left=0.065, right=0.86, top=0.78, bottom=0.13)
    title(fig, th, 'One flight, two stages', 'Altitude of the booster and the second stage on the default flight, every command from the network')
    t = [p[0] / 60 for p in data['track']]
    ax.plot(t, [p[2] for p in data['track']], color=th['series'][1], linewidth=2, solid_capstyle='round')
    ax.plot(t, [p[1] for p in data['track']], color=th['series'][0], linewidth=2, solid_capstyle='round')
    ev = dict(data['events'])
    marks = [('MECO', 'MECO'), ('BOOSTBACK_START', 'Boostback'), ('ENTRY_BURN', 'Entry burn'),
             ('LANDING_BURN', 'Landing burn'), ('SECO', 'SECO')]
    for key, label in marks:
        x = ev[key] / 60
        ax.plot([x, x], [0, 300], color=th['axis'], linewidth=0.8, linestyle=(0, (2, 3)), zorder=0)
        ax.text(x, 306, label, rotation=90, ha='center', va='bottom', fontsize=8.5, color=th['muted'])
    end = data['track'][-1]
    ax.text(end[0] / 60 + 0.12, end[2], 'Second stage\n270 km orbit', color=th['ink'], fontsize=9.5, va='center')
    land = next(p for p in data['track'] if p[0] >= ev['TOUCHDOWN'])
    ax.annotate('Booster lands\nT+%d:%02d' % divmod(round(ev['TOUCHDOWN']), 60), (land[0] / 60, 0), xytext=(land[0] / 60 + 0.35, 52),
                color=th['ink'], fontsize=9.5, arrowprops=dict(arrowstyle='-', color=th['muted'], linewidth=0.8))
    apo = max(data['track'], key=lambda p: p[1])
    ax.annotate('Booster apogee %.0f km' % apo[1], (apo[0] / 60, apo[1]), xytext=(apo[0] / 60 + 0.3, apo[1] + 32),
                color=th['ink'], fontsize=9.5, arrowprops=dict(arrowstyle='-', color=th['muted'], linewidth=0.8))
    style(ax, th)
    ax.set_xlim(0, 10.5)
    ax.set_ylim(0, 380)
    ax.set_yticks(range(0, 301, 50))
    ax.set_xlabel('Mission time (minutes)', color=th['ink2'], fontsize=10)
    ax.set_ylabel('Altitude (km)', color=th['ink2'], fontsize=10)
    handles = [plt.Line2D([], [], color=th['series'][0], linewidth=2), plt.Line2D([], [], color=th['series'][1], linewidth=2)]
    fig.legend(handles, ['Booster', 'Second stage'], loc='upper right', bbox_to_anchor=(0.99, 0.985), frameon=False,
               fontsize=9.5, labelcolor=th['ink2'], ncol=2, handlelength=1.6)
    save(fig, 'mission-profile', mode)


def touchdown(data, mode):
    th = THEMES[mode]
    pts = [p for p in data['touchdowns'] if p[0] is not None]
    fig, (a, b) = plt.subplots(1, 2, figsize=(10, 4.4), gridspec_kw=dict(width_ratios=[1, 1.35]))
    fig.subplots_adjust(left=0.07, right=0.985, top=0.78, bottom=0.14, wspace=0.28)
    ok = sum(p[3] for p in data['touchdowns'])
    title(fig, th, f'{ok:,} of {len(data["touchdowns"]):,} held-out landings',
          'Touchdown points and speeds on flights the network never trained on (wind, thrust, drag and mass dispersed)')
    lim = 12
    a.add_patch(Circle((0, 0), 5, fill=False, edgecolor=th['axis'], linewidth=0.8, linestyle=(0, (2, 3))))
    a.text(3.6, -4.2, '5 m', color=th['muted'], fontsize=8.5)
    a.scatter([p[0] for p in pts], [p[1] for p in pts], s=9, color=th['series'][0], alpha=0.45, linewidths=0)
    a.plot([0], [0], marker='+', markersize=10, color=th['ink'], markeredgewidth=1.2)
    style(a, th, grid_axis=None)
    a.set_xlim(-lim, lim)
    a.set_ylim(-lim, lim)
    a.set_aspect('equal')
    a.set_xlabel('East of pad centre (m)', color=th['ink2'], fontsize=10)
    a.set_ylabel('North of pad centre (m)', color=th['ink2'], fontsize=10)
    a.text(-lim + 0.6, lim - 1.2, 'Pad radius 43 m', color=th['muted'], fontsize=8.5)
    speeds = [-p[2] for p in pts]
    bins = [0.8 + 0.05 * i for i in range(29)]
    b.hist(speeds, bins=bins, color=th['series'][0], edgecolor=th['gap'], linewidth=1.5)
    b.axvline(3.0, color=th['ink2'], linewidth=1, linestyle=(0, (3, 3)))
    b.text(2.95, b.get_ylim()[1] * 0.92, 'limit 3 m/s', ha='right', color=th['ink2'], fontsize=9)
    style(b, th)
    b.set_xlim(0.8, 3.2)
    b.set_xlabel('Vertical speed at touchdown (m/s)', color=th['ink2'], fontsize=10)
    b.set_ylabel('Flights', color=th['ink2'], fontsize=10)
    save(fig, 'touchdown', mode)


def faults(mode):
    th = THEMES[mode]
    fig, ax = plt.subplots(figsize=(10, 4.4))
    fig.subplots_adjust(left=0.235, right=0.97, top=0.78, bottom=0.13)
    title(fig, th, 'Recovering from engine faults', 'Landings out of 100 dispersed flights with the fault forced during the landing burn')
    names = ['This network', 'Previous network', 'Classical teacher']
    h, step = 0.24, 0.28
    for i, (label, *vals) in enumerate(FAULTS):
        base = len(FAULTS) - 1 - i
        for k, v in enumerate(vals):
            y = base + (1 - k) * step - h / 2
            if v > 0:
                ax.barh(y + h / 2, v, height=h, color=th['series'][k], edgecolor=th['gap'], linewidth=1.5)
            ax.text(v + 1.2, y + h / 2, str(v), va='center', fontsize=9, color=th['ink'])
    ax.set_yticks(range(len(FAULTS)))
    ax.set_yticklabels([f[0] for f in reversed(FAULTS)], fontsize=10, color=th['ink'])
    style(ax, th, grid_axis='x')
    ax.set_xlim(0, 108)
    ax.set_ylim(-0.55, len(FAULTS) - 0.45)
    ax.set_xlabel('Landed (of 100)', color=th['ink2'], fontsize=10)
    handles = [Rectangle((0, 0), 1, 1, color=c) for c in th['series']]
    fig.legend(handles, names, loc='upper right', bbox_to_anchor=(0.99, 0.985), frameon=False, fontsize=9.5,
               labelcolor=th['ink2'], ncol=3, handlelength=1.1)
    save(fig, 'fault-recovery', mode)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({'svg.fonttype': 'none', 'font.family': ['Segoe UI', 'DejaVu Sans', 'sans-serif']})
    if '--cached' in sys.argv and CACHE.exists():
        data = json.loads(CACHE.read_text())
    else:
        run = subprocess.run(['node', '-e', NODE, str(ROOT)], cwd=ROOT, capture_output=True, text=True, check=True)
        data = json.loads(run.stdout)
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(data))
    for mode in THEMES:
        profile(data, mode)
        touchdown(data, mode)
        faults(mode)
    ok = sum(p[3] for p in data['touchdowns'])
    print(f'wrote {OUT}: held-out {ok}/{len(data["touchdowns"])}')


if __name__ == '__main__':
    main()
