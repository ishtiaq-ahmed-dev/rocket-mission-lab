"""Fit the neural flight policy to teacher-labelled states and export it for the browser.

Reads every dataset file under data/flight-policy/datasets/*.f32 (rows written by
rollout.js), trains two MLPs -- booster/stack and upper stage -- and writes
frontend/public/flight-policy.js, which the replay page and the Node tools load.

    python scripts/flight_policy/train.py [--epochs N] [--init] [--tag NAME]
"""
import argparse
import base64
import glob
import json
import os
import time

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
DATA = os.path.join(ROOT, 'data', 'flight-policy', 'datasets')
OUT = os.path.join(ROOT, 'frontend', 'public', 'flight-policy.js')
CKPT = os.path.join(ROOT, 'data', 'flight-policy', 'policy.pt')
NB, NU = 48, 26
ROW = 1 + NB + 7 + 1 + NU + 7
# booster block offsets
B_VALID, B_X = 0, 1
B_DIR, B_THR, B_ENG, B_SEP, B_MODE = 1 + NB, 4 + NB, 5 + NB, 6 + NB, 7 + NB
U_VALID = 8 + NB
U_X = U_VALID + 1
U_DIR, U_THR, U_ON, U_FAIR, U_DEP = U_X + NU, U_X + NU + 3, U_X + NU + 4, U_X + NU + 5, U_X + NU + 6
F_ATTACHED, U_F_SECO, U_F_FAIR, U_F_SAT = 25, 10, 12, 13
MODE_WEIGHT = [1.0, 1.5, 2.0, 1.0, 2.0, 2.0, 4.0]   # ASC COAST1 BB COAST2 ENTRY AERO LAND


def mlp(n_in, width, depth, n_out):
    layers, k = [], n_in
    for _ in range(depth):
        layers += [nn.Linear(k, width), nn.SiLU()]
        k = width
    layers.append(nn.Linear(k, n_out))
    return nn.Sequential(*layers)


def load():
    files = sorted(glob.glob(os.path.join(DATA, '*.f32')))
    arrays = [np.fromfile(f, dtype=np.float32).reshape(-1, ROW) for f in files]
    data = np.concatenate(arrays) if arrays else np.zeros((0, ROW), np.float32)
    return data, files


def normalizer(x):
    mean, std = x.mean(0), x.std(0)
    std[std < 1e-3] = 1.0
    return mean.astype(np.float32), std.astype(np.float32)


def booster_loss(net, x, y, w):
    """x = normalized features plus the raw `attached` flag as the last column."""
    out = net(x[:, :NB])
    d, eng, attached = y[:, 0:3], y[:, 4].long(), x[:, NB]
    on = (eng > 0).float()
    l_dir = ((out[:, 0:3] - d) ** 2).sum(1)
    l_thr = on * (out[:, 3] - y[:, 3]) ** 2
    l_eng = F.cross_entropy(out[:, 4:8], eng, reduction='none')
    l_sep = attached * F.binary_cross_entropy_with_logits(out[:, 8], y[:, 5], reduction='none')
    return (w * (1000 * l_dir + 50 * l_thr + l_eng + l_sep)).mean()


def upper_loss(net, x, y, flags):
    out = net(x)
    seco, has_fair, has_sat = flags[:, 0], flags[:, 1], flags[:, 2]
    on = y[:, 4]
    l_dir = ((out[:, 0:3] - y[:, 0:3]) ** 2).sum(1)
    l_thr = on * (out[:, 3] - y[:, 3]) ** 2
    bce = lambda z, t: F.binary_cross_entropy_with_logits(z, t, reduction='none')
    l_on = (1 - seco) * bce(out[:, 4], on)
    l_fair = has_fair * bce(out[:, 5], y[:, 5])
    l_dep = seco * has_sat * bce(out[:, 6], y[:, 6])
    return (1000 * l_dir + 50 * l_thr + l_on + l_fair + l_dep).mean()


def b64(a):
    return base64.b64encode(np.ascontiguousarray(a, dtype=np.float32).tobytes()).decode('ascii')


def export(net, mean, std):
    layers = [m for m in net if isinstance(m, nn.Linear)]
    return {'mean': b64(mean), 'std': b64(std), 'activation': 'silu',
            'layers': [{'in': l.in_features, 'out': l.out_features,
                        'W': b64(l.weight.detach().cpu().numpy()), 'b': b64(l.bias.detach().cpu().numpy())} for l in layers]}


def fit(net, loss_fn, tensors, epochs, lr, batch, dev, label):
    opt = torch.optim.AdamW(net.parameters(), lr=lr, weight_decay=1e-5)
    n = tensors[0].shape[0]
    steps = max(1, epochs * ((n + batch - 1) // batch))
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=lr, total_steps=steps, pct_start=0.1)
    t0 = time.time()
    for ep in range(epochs):
        perm = torch.randperm(n, device=dev)
        total = 0.0
        for i in range(0, n, batch):
            idx = perm[i:i + batch]
            loss = loss_fn(net, *[t[idx] for t in tensors])
            opt.zero_grad(set_to_none=True)
            loss.backward()
            nn.utils.clip_grad_norm_(net.parameters(), 1.0)
            opt.step()
            sched.step()
            total += loss.item() * len(idx)
        if ep == 0 or (ep + 1) % max(1, epochs // 8) == 0 or ep == epochs - 1:
            print(f'  {label} epoch {ep + 1}/{epochs} loss {total / n:.5f} ({time.time() - t0:.0f}s)', flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--epochs', type=int, default=40)
    ap.add_argument('--lr', type=float, default=2e-3)
    ap.add_argument('--init', action='store_true', help='start from the saved checkpoint')
    ap.add_argument('--tag', default='')
    args = ap.parse_args()
    torch.manual_seed(0)
    dev = 'cuda' if torch.cuda.is_available() else 'cpu'
    data, files = load()
    print(f'{len(data)} rows from {len(files)} files on {dev}')

    rb = data[data[:, B_VALID] > 0.5]
    xb = rb[:, B_X:B_X + NB]
    yb = np.stack([rb[:, B_DIR], rb[:, B_DIR + 1], rb[:, B_DIR + 2], rb[:, B_THR], rb[:, B_ENG], rb[:, B_SEP]], 1)
    wb = np.array(MODE_WEIGHT, np.float32)[rb[:, B_MODE].astype(int)]
    # the last 50 m of the landing burn decide touchdown speed: weight them more
    wb = wb * np.where((rb[:, B_MODE] == 6) & (xb[:, 8] < 0.5), 3.0, 1.0).astype(np.float32)
    ru = data[data[:, U_VALID] > 0.5]
    xu = ru[:, U_X:U_X + NU]
    yu = ru[:, U_DIR:U_DEP + 1]
    fu = np.stack([xu[:, U_F_SECO], xu[:, U_F_FAIR], xu[:, U_F_SAT]], 1)

    ckpt = torch.load(CKPT) if args.init and os.path.exists(CKPT) else None
    if ckpt:
        mb, sb, mu, su = (ckpt[k].numpy() for k in ('mb', 'sb', 'mu', 'su'))
    else:
        (mb, sb), (mu, su) = normalizer(xb), normalizer(xu)
    T = lambda a: torch.tensor(a, device=dev)
    nb, nu = mlp(NB, 256, 3, 9).to(dev), mlp(NU, 128, 3, 7).to(dev)
    if ckpt:
        nb.load_state_dict(ckpt['nb']); nu.load_state_dict(ckpt['nu'])

    # attached flag appended as the last column for the separation mask
    xbn = np.concatenate([(xb - mb) / sb, xb[:, F_ATTACHED:F_ATTACHED + 1]], 1)
    fit(nb, booster_loss, [T(xbn), T(yb), T(wb)], args.epochs, args.lr, 8192, dev, 'booster')
    xun = (xu - mu) / su
    fit(nu, upper_loss, [T(xun), T(yu), T(fu)], args.epochs, args.lr, 4096, dev, 'upper')

    os.makedirs(os.path.dirname(CKPT), exist_ok=True)
    torch.save({'nb': nb.state_dict(), 'nu': nu.state_dict(), **{k: torch.from_numpy(np.asarray(v)) for k, v in (('mb', mb), ('sb', sb), ('mu', mu), ('su', su))}}, CKPT)
    policy = {'version': 1, 'tag': args.tag, 'rows': int(len(data)), 'booster': export(nb, mb, sb), 'upper': export(nu, mu, su),
              'note': 'MLP flight policy (SiLU). Trained by imitation of a classical teacher with DAgger; see scripts/flight_policy.'}
    with open(OUT, 'w', encoding='utf-8', newline='\n') as f:
        f.write('/* Trained neural flight policy (generated by scripts/flight_policy/train.py; do not edit). */\n')
        f.write('(function(r){r.FLIGHT_POLICY=' + json.dumps(policy, separators=(',', ':')) + ';})(typeof window!=="undefined"?window:globalThis);\n')
    print(f'wrote {OUT} ({os.path.getsize(OUT) / 1024:.0f} KB)')


if __name__ == '__main__':
    main()
