"""Train and evaluate a behavior-cloned combined flight policy.

The classical level-4 controller is a qualified 12/12 combined pilot on the
current aerodynamics. It is used here only as a demonstration source for a
supervised actor, not as a runtime controller. The student sees the same
22-value observation as every learned policy and commands throttle, gimbal and
the RCS channel explicitly (six actions).
"""
import argparse
import json
import math
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from rocket_lab.bc import MLP
from rocket_lab.config import DATA, load_config
from rocket_lab.controllers import ClassicalController
from rocket_lab.envs import RocketEnv
from rocket_lab.missions import configure_flight
from rocket_lab.storage import atomic_json, config_hash, dynamics_hash


def wilson(k, n):
    if n == 0:
        return [0., 1.]
    z = 1.95996398454
    p = k / n
    denominator = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denominator
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return [max(0., center - margin), min(1., center + margin)]


def unstable(*values, limit=1e4):
    """A diverged MuJoCo state must never become training data or a metric."""
    for value in values:
        array = np.asarray(value, dtype=np.float64)
        if not np.all(np.isfinite(array)) or (array.size and np.max(np.abs(array)) > limit):
            return True
    return False


def collect(mission, config, start_seed, episodes, level=4):
    env = RocketEnv(mission, config=config, difficulty=1., training=False,
                    randomize=True, noise=True, rcs_action=True)
    limit = float(config['vehicle'].get('rcs_torque_max', 0.))
    observations, actions, episode_ids = [], [], []
    outcomes = []
    for episode in range(episodes):
        seed = start_seed + episode
        observation, _ = env.reset(seed=seed)
        controller = ClassicalController(level)
        steps = 0
        info = {}
        first = len(observations)
        diverged = unstable(observation)
        while not diverged:
            # The teacher writes its RCS request onto the physics object before
            # returning the three gimbal/throttle values. Capture that request
            # as the fourth through sixth action dimensions.
            gimbal = controller.action(env)
            rcs = np.clip(env.physics.rcs_torque / max(limit, 1e-12), -1., 1.)
            action = np.r_[gimbal, rcs].astype(np.float32)
            if unstable(action):
                diverged = True
                break
            observations.append(observation.copy())
            actions.append(action)
            episode_ids.append(episode)
            observation, _, terminated, truncated, info = env.step(action)
            steps += 1
            if terminated or truncated:
                break
            diverged = unstable(observation)
        if diverged:
            # A diverged rollout is not a demonstration: drop every transition
            # it produced rather than fitting a non-finite state.
            del observations[first:]; del actions[first:]; del episode_ids[first:]
            info = {'outcome': 'unstable_state'}
            print(f"COLLECT {episode + 1}/{episodes} seed={seed} DISCARDED unstable simulator state", flush=True)
        else:
            print(f"COLLECT {episode + 1}/{episodes} seed={seed} outcome={info.get('outcome')} steps={steps}", flush=True)
        outcomes.append(dict(seed=seed, outcome=info.get('outcome'), steps=steps,
                             touchdown_speed=info.get('touchdown_speed'),
                             tilt=info.get('tilt'), pad_distance=info.get('pad_distance')))
    env.close()
    return (np.asarray(observations, dtype=np.float32),
            np.asarray(actions, dtype=np.float32),
            np.asarray(episode_ids, dtype=np.int64), outcomes)


def terminal_weights(observations, config):
    """Prioritize the last metres, where a small action error is a crash."""
    scale = float(np.asarray(config['training'].get('observation_position_scale', [400,400,250]))[2])
    altitude = np.maximum(0., observations[:, 2] * scale)
    vertical_speed = np.abs(observations[:, 5] * float(np.asarray(config['training'].get('observation_velocity_scale', [50,50,30]))[2]))
    weight = 1. + 7. * np.exp(-altitude / 22.) + 3. * np.exp(-altitude / 70.)
    weight += 2. * np.exp(-altitude / 35.) * np.clip(vertical_speed / 6., 0., 2.)
    return (weight / weight.mean()).astype(np.float32)


def split(observations, actions, episode_ids, seed=0, validation_fraction=.15):
    unique = np.unique(episode_ids)
    rng = np.random.default_rng(seed)
    count = max(1, int(round(len(unique) * validation_fraction)))
    validation = set(rng.choice(unique, size=count, replace=False).tolist())
    mask = np.array([value not in validation for value in episode_ids])
    return observations[mask], actions[mask], observations[~mask], actions[~mask], validation


def train(observations, actions, episode_ids, config, epochs=50, hidden=256, seed=0, log_prefix="TRAIN", throttle_mode="tanh"):
    if len(observations) == 0:
        raise RuntimeError('No finite demonstration transitions were collected; refusing to train')
    if unstable(observations) or unstable(actions):
        raise RuntimeError('Training data contains a non-finite or divergent state; refusing to fit it')
    train_x, train_y, val_x, val_y, validation = split(observations, actions, episode_ids, seed=seed)
    mean = train_x.mean(axis=0)
    std = train_x.std(axis=0)
    std[std < 1e-6] = 1.
    train_weights = terminal_weights(train_x, config)
    validation_weights = terminal_weights(val_x, config)
    train_x = (train_x - mean) / std
    val_x = (val_x - mean) / std
    model = MLP(train_x.shape[1], train_y.shape[1], hidden,
                output_activation=None if throttle_mode == 'sigmoid' else 'tanh')
    def prediction_error(outputs, targets):
        if throttle_mode == 'sigmoid':
            # The engine is effectively on or off in the terminal phase. A
            # sigmoid logit preserves that decision instead of averaging it.
            target_throttle = (targets[:, 0] + 1.) / 2.
            throttle_error = nn.functional.binary_cross_entropy_with_logits(
                outputs[:, 0], target_throttle, reduction='none')
            control_error = (torch.tanh(outputs[:, 1:]) - targets[:, 1:]) ** 2
            return torch.cat([throttle_error[:, None], control_error], dim=1)
        return (outputs - targets) ** 2
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=max(1, epochs))
    loader = DataLoader(TensorDataset(torch.from_numpy(train_x), torch.from_numpy(train_y), torch.from_numpy(train_weights)),
                        batch_size=1024, shuffle=True)
    best_loss, best_state = float('inf'), None
    for epoch in range(epochs):
        model.train()
        total = 0.
        count = 0
        for batch_x, batch_y, batch_weight in loader:
            optimizer.zero_grad()
            error = prediction_error(model(batch_x), batch_y)
            loss = (error * batch_weight[:, None]).mean()
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.)
            optimizer.step()
            total += loss.item() * len(batch_x)
            count += len(batch_x)
        scheduler.step()
        model.eval()
        with torch.no_grad():
            validation_error = prediction_error(model(torch.from_numpy(val_x)), torch.from_numpy(val_y))
            validation_loss = float((validation_error * torch.from_numpy(validation_weights)[:, None]).mean())
        if validation_loss < best_loss:
            best_loss = validation_loss
            best_state = {key: value.detach().clone() for key, value in model.state_dict().items()}
        if epoch == 0 or (epoch + 1) % 5 == 0 or epoch + 1 == epochs:
            print(f"{log_prefix} epoch {epoch + 1}/{epochs} train_mse={total / max(count, 1):.6f} val_mse={validation_loss:.6f}", flush=True)
    model.load_state_dict(best_state)
    model.eval()
    return model, mean, std, dict(validation_loss=best_loss, train_samples=len(train_x),
                                  validation_samples=len(val_x), validation_episodes=sorted(validation))


def predict(model, mean, std, observation, throttle_mode="tanh"):
    with torch.no_grad():
        x = (np.asarray(observation, dtype=np.float32) - mean) / std
        raw = model(torch.from_numpy(x).unsqueeze(0))
        if throttle_mode == 'sigmoid':
            throttle = torch.sigmoid(raw[:, :1]) * 2. - 1.
            controls = torch.tanh(raw[:, 1:])
            value = torch.cat([throttle, controls], dim=1)
        else:
            value = raw
        return np.clip(value.numpy()[0], -1., 1.).astype(np.float32)


def evaluate(model, mean, std, mission, config, start_seed, episodes, throttle_mode="tanh"):
    env = RocketEnv(mission, config=config, difficulty=1., training=False,
                    randomize=True, noise=True, rcs_action=True)
    rows = []
    for episode in range(episodes):
        seed = start_seed + episode
        observation, _ = env.reset(seed=seed)
        info = {}
        diverged = unstable(observation)
        while not diverged:
            action = predict(model, mean, std, observation, throttle_mode)
            if unstable(action):
                diverged = True
                break
            observation, _, terminated, truncated, info = env.step(action)
            if terminated or truncated:
                diverged = unstable(observation)
                break
            diverged = unstable(observation)
        outcome = 'unstable_state' if diverged else info.get('outcome')
        # A diverged rollout has no meaningful touchdown numbers; record the
        # failure with null metrics instead of inventing zeros.
        rows.append(dict(seed=seed, outcome=outcome,
                         touchdown_speed=None if diverged else float(info.get('touchdown_speed', 0.)),
                         tilt=None if diverged else float(info.get('tilt', 0.)),
                         pad_distance=None if diverged else float(info.get('pad_distance', 0.)),
                         fuel_used=None if diverged else float(info.get('fuel_used', 0.))))
        print(f"EVAL {episode + 1}/{episodes} seed={seed} outcome={outcome} "
              f"speed={rows[-1]['touchdown_speed']} tilt={rows[-1]['tilt']} pad={rows[-1]['pad_distance']}", flush=True)
    env.close()
    valid = [row for row in rows if all(isinstance(row[key], float) and math.isfinite(row[key])
                                        for key in ('touchdown_speed', 'tilt', 'pad_distance'))]
    if not valid:
        raise RuntimeError('Evaluation produced no finite flight metrics; refusing to write a checkpoint')
    def values(key):
        return np.array([row[key] for row in valid], dtype=np.float64)
    speed, tilt, pad = values('touchdown_speed'), values('tilt'), values('pad_distance')
    summary = dict(mean_touchdown_speed=float(np.mean(speed)), median_touchdown_speed=float(np.median(speed)),
                   touchdown_speed_std=float(np.std(speed)), mean_tilt=float(np.mean(tilt)),
                   median_tilt=float(np.median(tilt)), tilt_std=float(np.std(tilt)),
                   mean_pad_distance=float(np.mean(pad)), median_pad_distance=float(np.median(pad)),
                   pad_distance_std=float(np.std(pad)))
    if not all(math.isfinite(value) for value in summary.values()):
        raise RuntimeError('Held-out metrics are not finite; refusing to write a checkpoint')
    successes = sum(row['outcome'] == 'success' for row in rows)
    return rows, successes, valid, summary


def dagger_round(model, mean, std, mission, config, start_seed, episodes, level=4, throttle_mode="tanh"):
    """Relabel states visited by the student with the classical teacher."""
    env = RocketEnv(mission, config=config, difficulty=1., training=False,
                    randomize=True, noise=True, rcs_action=True)
    limit = float(config['vehicle'].get('rcs_torque_max', 0.))
    observations, actions, episode_ids = [], [], []
    for episode in range(episodes):
        seed = start_seed + episode
        observation, _ = env.reset(seed=seed)
        controller = ClassicalController(level)
        info = {}
        first = len(observations)
        diverged = unstable(observation)
        while not diverged:
            # Teacher label for the current student-visited state.
            gimbal = controller.action(env)
            rcs = np.clip(env.physics.rcs_torque / max(limit, 1e-12), -1., 1.)
            teacher = np.r_[gimbal, rcs].astype(np.float32)
            if unstable(teacher):
                diverged = True
                break
            observations.append(observation.copy())
            actions.append(teacher)
            episode_ids.append(episode)
            student = predict(model, mean, std, observation, throttle_mode)
            if unstable(student):
                diverged = True
                break
            observation, _, terminated, truncated, info = env.step(student)
            if terminated or truncated:
                break
            diverged = unstable(observation)
        if diverged:
            del observations[first:]; del actions[first:]; del episode_ids[first:]
            print(f"DAGGER {episode + 1}/{episodes} seed={seed} DISCARDED unstable simulator state", flush=True)
        else:
            print(f"DAGGER {episode + 1}/{episodes} seed={seed} outcome={info.get('outcome')}", flush=True)
    env.close()
    return (np.asarray(observations, dtype=np.float32),
            np.asarray(actions, dtype=np.float32),
            np.asarray(episode_ids, dtype=np.int64) + start_seed)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mission', default='combined', choices=['landing', 'takeoff', 'combined'])
    parser.add_argument('--episodes', type=int, default=40)
    parser.add_argument('--dagger', type=int, default=2)
    parser.add_argument('--dagger-episodes', type=int, default=15)
    parser.add_argument('--epochs', type=int, default=50)
    parser.add_argument('--hidden', type=int, default=256)
    parser.add_argument('--throttle-mode', choices=['tanh', 'sigmoid'], default='sigmoid')
    parser.add_argument('--eval-episodes', type=int, default=24)
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--output', default='data/checkpoints/bc-combined-v1/step-000000001')
    args = parser.parse_args()
    torch.set_num_threads(max(1, min(8, os.cpu_count() or 1)))

    config, _ = configure_flight(load_config(), mission=args.mission)
    started = time.time()
    observations, actions, episode_ids, teacher_rows = collect(args.mission, config, 0, args.episodes)
    print(f"COLLECTED {len(observations)} transitions from {args.episodes} classical flights in {time.time() - started:.1f}s", flush=True)
    model, mean, std, train_metrics = train(observations, actions, episode_ids, config, args.epochs, args.hidden, args.seed, throttle_mode=args.throttle_mode)
    for round_index in range(args.dagger):
        dagger_x, dagger_y, dagger_ids = dagger_round(model, mean, std, args.mission, config,
                                                     1000 + round_index * args.dagger_episodes, args.dagger_episodes,
                                                     throttle_mode=args.throttle_mode)
        observations = np.concatenate([observations, dagger_x])
        actions = np.concatenate([actions, dagger_y])
        episode_ids = np.concatenate([episode_ids, dagger_ids])
        model, mean, std, train_metrics = train(observations, actions, episode_ids, config, args.epochs, args.hidden, args.seed, throttle_mode=args.throttle_mode)
        print(f"DAGGER ROUND {round_index + 1} complete; total transitions={len(observations)}", flush=True)

    rows, successes, valid, summary = evaluate(model, mean, std, args.mission, config, 20000, args.eval_episodes, args.throttle_mode)
    success_rate = successes / max(1, len(rows))
    interval = wilson(successes, len(rows))
    metrics = {
        'success_rate': success_rate,
        'successes': successes,
        'episodes': len(rows),
        'confidence_interval': interval,
        **summary,
        'failures': {outcome: sum(row['outcome'] == outcome for row in rows)
                     for outcome in sorted({row['outcome'] for row in rows if row['outcome'] != 'success'})},
        'train': train_metrics,
        'teacher_outcomes': teacher_rows,
        'rows': rows,
    }
    output = ROOT / args.output
    output.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), output / 'model.pt')
    np.savez_compressed(output / 'normalizer.npz', mean=mean, std=std)
    checkpoint = {
        'job_id': output.parent.name,
        'mission': args.mission,
        'algorithm': 'BC',
        'steps': int(len(observations)),
        'action_dim': 6,
        'observation_dim': int(observations.shape[1]),
        'hidden': args.hidden,
        'throttle_mode': args.throttle_mode,
        'rcs_action': True,
        'config': config,
        'config_hash': config_hash(config),
        'dynamics_hash': dynamics_hash(),
        'evaluation_episodes': len(rows),
        'successes': successes,
        'success_rate': success_rate,
        'confidence_interval': interval,
        'mean_touchdown_speed': summary['mean_touchdown_speed'],
        'median_touchdown_speed': summary['median_touchdown_speed'],
        'touchdown_speed_std': summary['touchdown_speed_std'],
        'mean_tilt': summary['mean_tilt'],
        'median_tilt': summary['median_tilt'],
        'tilt_std': summary['tilt_std'],
        'mean_pad_distance': summary['mean_pad_distance'],
        'median_pad_distance': summary['median_pad_distance'],
        'pad_distance_std': summary['pad_distance_std'],
        'mean_reward': 0.,
        'created_at': time.time(),
    }
    atomic_json(output / 'checkpoint.json', checkpoint)
    atomic_json(output / 'metrics.json', metrics)
    atomic_json(DATA / 'models' / output.parent.name / 'metrics.json', metrics)
    print(json.dumps(checkpoint, indent=2), flush=True)
    print(f"CHECKPOINT {output}", flush=True)


if __name__ == '__main__':
    main()
