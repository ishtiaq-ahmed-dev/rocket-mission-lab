"""Fit the neural flight policy to teacher-labelled states and export it for the browser.

Reads every dataset file under data/flight-policy/datasets/*.f32 (rows written by
rollout.js), trains two MLPs -- booster/stack and upper stage -- and writes
an isolated candidate under data/flight-policy. The DAgger driver evaluates it
before replacing frontend/public/flight-policy.js.

    python scripts/flight_policy/train.py [--epochs N] [--init] [--tag NAME]
"""
import argparse
import base64
import glob
import json
import os
import time
import tempfile

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
DATA = os.path.join(ROOT, 'data', 'flight-policy', 'datasets')
OUT = os.path.join(ROOT, 'data', 'flight-policy', 'candidate.js')
CKPT = os.path.join(ROOT, 'data', 'flight-policy', 'policy.pt')
NB, NU = 52, 26
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


class MappedRows:
    """File-backed rows; materialize only the requested minibatch."""
    def __init__(self, arrays):
        self.arrays = arrays
        self.ends = np.cumsum([len(a) for a in arrays])
        self.starts = np.r_[0, self.ends[:-1]]

    def __len__(self):
        return int(self.ends[-1])

    def take(self, indices):
        indices = np.asarray(indices, dtype=np.int64)
        if np.any(indices < 0) or np.any(indices >= len(self)):
            raise IndexError('Flight-policy row index out of bounds')
        result = np.empty((len(indices), ROW), np.float32)
        owners = np.searchsorted(self.ends, indices, side='right')
        for owner in np.unique(owners):
            mask = owners == owner
            result[mask] = self.arrays[owner][indices[mask] - self.starts[owner]]
        return result

    def valid_indices(self, column):
        return np.concatenate([np.flatnonzero(a[:, column] > 0.5) + start for a, start in zip(self.arrays, self.starts)])


def load(directory=DATA):
    files = sorted(glob.glob(os.path.join(directory, '*.f32')))
    if not files:
        raise ValueError(f'No flight-policy datasets found in {directory}')
    # Map source files instead of retaining every file plus the concatenated
    # dataset in RAM. This matters on Windows where commit can run out while
    # physical RAM is still available.
    arrays = []
    for file in files:
        if os.path.getsize(file) == 0 or os.path.getsize(file) % (ROW * 4):
            raise ValueError(f'Invalid flight-policy row size: {file}')
        rows = np.memmap(file, dtype='<f4', mode='r').reshape(-1, ROW)
        if not np.isfinite(rows).all():
            raise ValueError('Flight-policy datasets must contain finite, nonempty rows')
        active = rows[:, B_VALID] > 0.5
        modes, engines = rows[active, B_MODE], rows[active, B_ENG]
        if np.any((modes < 0) | (modes >= len(MODE_WEIGHT)) | (modes != np.floor(modes))):
            raise ValueError('Invalid booster mode labels in flight-policy dataset')
        if np.any((engines < 0) | (engines > 3) | (engines != np.floor(engines))):
            raise ValueError('Invalid engine labels in flight-policy dataset')
        arrays.append(rows)
    return MappedRows(arrays), files


def normalizer(x):
    if x.ndim != 2 or not len(x) or not np.isfinite(x).all():
        raise ValueError('Normalization requires finite, nonempty feature rows')
    mean, std = x.mean(0), x.std(0)
    std[std < 1e-3] = 1.0
    return mean.astype(np.float32), std.astype(np.float32)


def mapped_normalizer(data, indices, start, width):
    if not len(indices):
        raise ValueError('Normalization requires finite, nonempty feature rows')
    total, squares = np.zeros(width), np.zeros(width)
    for offset in range(0, len(indices), 32768):
        x = data.take(indices[offset:offset + 32768])[:, start:start + width].astype(np.float64)
        total += x.sum(0)
        squares += np.square(x).sum(0)
    mean = total / len(indices)
    std = np.sqrt(np.maximum(0, squares / len(indices) - mean * mean))
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


def from_policy(filename):
    """Resume the actual shipped weights, which can differ from policy.pt."""
    with open(filename, encoding='utf-8') as stream:
        source = stream.read()
    policy = json.JSONDecoder().raw_decode(source.split('r.FLIGHT_POLICY=', 1)[1])[0]
    result = {}
    for key, name, mean_key, std_key in [('nb', 'booster', 'mb', 'sb'), ('nu', 'upper', 'mu', 'su')]:
        spec = policy[name]
        decode = lambda value: np.frombuffer(base64.b64decode(value, validate=True), dtype='<f4').copy()
        result[mean_key] = torch.from_numpy(decode(spec['mean']))
        result[std_key] = torch.from_numpy(decode(spec['std']))
        state = {}
        for index, layer in enumerate(spec['layers']):
            state[f'{index * 2}.weight'] = torch.from_numpy(decode(layer['W']).reshape(layer['out'], layer['in']))
            state[f'{index * 2}.bias'] = torch.from_numpy(decode(layer['b']))
        result[key] = state
    return result


def atomic_save(filename, writer):
    directory = os.path.dirname(os.path.abspath(filename))
    os.makedirs(directory, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.policy-', suffix='.tmp', dir=directory)
    os.close(fd)
    try:
        writer(temporary)
        os.replace(temporary, filename)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)


def fit(net, loss_fn, data, indices, prepare, epochs, lr, batch, dev, label):
    opt = torch.optim.AdamW(net.parameters(), lr=lr, weight_decay=1e-5)
    n = len(indices)
    if n == 0:
        raise ValueError(f'No valid {label} training rows')
    steps = max(1, epochs * ((n + batch - 1) // batch))
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=lr, total_steps=steps, pct_start=0.1)
    t0 = time.time()
    for ep in range(epochs):
        perm = torch.randperm(n).numpy()
        total = 0.0
        for i in range(0, n, batch):
            rows = data.take(indices[perm[i:i + batch]])
            tensors = [torch.from_numpy(a).to(dev) for a in prepare(rows)]
            loss = loss_fn(net, *tensors)
            if not torch.isfinite(loss):
                raise ValueError(f'Nonfinite {label} training loss; candidate was not exported')
            opt.zero_grad(set_to_none=True)
            loss.backward()
            nn.utils.clip_grad_norm_(net.parameters(), 1.0)
            opt.step()
            sched.step()
            total += loss.item() * len(rows)
        if ep == 0 or (ep + 1) % max(1, epochs // 8) == 0 or ep == epochs - 1:
            print(f'  {label} epoch {ep + 1}/{epochs} loss {total / n:.5f} ({time.time() - t0:.0f}s)', flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--epochs', type=int, default=40)
    ap.add_argument('--lr', type=float, default=2e-3)
    ap.add_argument('--init', action='store_true', help='start from the saved checkpoint')
    ap.add_argument('--init-policy', help='resume the exact weights of an exported policy instead of a different local checkpoint')
    ap.add_argument('--output', default=OUT, help='candidate export path; use a local path until closed-loop validation passes')
    ap.add_argument('--checkpoint', default=CKPT)
    ap.add_argument('--data-dir', default=DATA)
    ap.add_argument('--booster-only', action='store_true', help='preserve the upper-stage network during a landing refinement')
    ap.add_argument('--tag', default='')
    args = ap.parse_args()
    if args.epochs < 1 or not np.isfinite(args.lr) or args.lr <= 0:
        ap.error('epochs and learning rate must be positive')
    if args.booster_only and not (args.init_policy or args.init):
        ap.error('--booster-only requires existing weights')
    torch.manual_seed(0)
    dev = 'cuda' if torch.cuda.is_available() else 'cpu'
    data, files = load(args.data_dir)
    print(f'{len(data)} rows from {len(files)} files on {dev}')

    row_count = len(data)
    ib, iu = data.valid_indices(B_VALID), data.valid_indices(U_VALID)

    if args.init and not os.path.exists(args.checkpoint):
        raise ValueError(f'Requested checkpoint does not exist: {args.checkpoint}')
    ckpt = from_policy(args.init_policy) if args.init_policy else torch.load(args.checkpoint, map_location='cpu', weights_only=True) if args.init else None
    if ckpt:
        mb, sb, mu, su = (ckpt[k].numpy() for k in ('mb', 'sb', 'mu', 'su'))
    else:
        (mb, sb), (mu, su) = mapped_normalizer(data, ib, B_X, NB), mapped_normalizer(data, iu, U_X, NU)
    nb, nu = mlp(NB, 384, 4, 9).to(dev), mlp(NU, 128, 3, 7).to(dev)
    if ckpt:
        nb.load_state_dict(ckpt['nb']); nu.load_state_dict(ckpt['nu'])

    def prepare_booster(rows):
        x = rows[:, B_X:B_X + NB]
        y = np.stack([rows[:, k] for k in (B_DIR, B_DIR + 1, B_DIR + 2, B_THR, B_ENG, B_SEP)], 1)
        w = np.array(MODE_WEIGHT, np.float32)[rows[:, B_MODE].astype(int)]
        w *= np.where((rows[:, B_MODE] == 6) & (x[:, 8] < 0.5), 3., 1.).astype(np.float32)
        return [np.concatenate([(x - mb) / sb, x[:, F_ATTACHED:F_ATTACHED + 1]], 1), y, w]

    fit(nb, booster_loss, data, ib, prepare_booster, args.epochs, args.lr, 8192, dev, 'booster')
    if not args.booster_only:
        def prepare_upper(rows):
            x = rows[:, U_X:U_X + NU]
            flags = np.stack([x[:, k] for k in (U_F_SECO, U_F_FAIR, U_F_SAT)], 1)
            return [(x - mu) / su, rows[:, U_DIR:U_DEP + 1].copy(), flags]
        fit(nu, upper_loss, data, iu, prepare_upper, args.epochs, args.lr, 4096, dev, 'upper')

    atomic_save(args.checkpoint, lambda file: torch.save({'nb': nb.state_dict(), 'nu': nu.state_dict(), **{k: torch.from_numpy(np.asarray(v)) for k, v in (('mb', mb), ('sb', sb), ('mu', mu), ('su', su))}}, file))
    policy = {'version': 1, 'tag': args.tag, 'rows': int(row_count), 'booster': export(nb, mb, sb), 'upper': export(nu, mu, su),
              'note': 'MLP flight policy (SiLU). Trained by imitation of a classical teacher with DAgger; see scripts/flight_policy.'}
    source = '/* Trained neural flight policy (generated by scripts/flight_policy/train.py; do not edit). */\n'
    source += '(function(r){r.FLIGHT_POLICY=' + json.dumps(policy, separators=(',', ':'), allow_nan=False) + ';})(typeof window!=="undefined"?window:globalThis);\n'
    def write(file):
        with open(file, 'w', encoding='utf-8', newline='\n') as stream:
            stream.write(source)
    atomic_save(args.output, write)
    print(f'wrote {args.output} ({os.path.getsize(args.output) / 1024:.0f} KB)')


if __name__ == '__main__':
    main()
