"""Supervised flight policy trained from classical demonstrations.

The optional sigmoid throttle head models the engine's on/off nature instead of
regressing it to an average. The gimbal and RCS channels remain continuous
tanh outputs. Existing tanh checkpoints load unchanged.
"""
from pathlib import Path
import json
import numpy as np
import torch
from torch import nn


class MLP(nn.Module):
    def __init__(self, observation_dim=22, action_dim=6, hidden=256, output_activation='tanh'):
        super().__init__()
        self.output_activation = output_activation
        self.net = nn.Sequential(
            nn.Linear(observation_dim, hidden), nn.SiLU(),
            nn.Linear(hidden, hidden), nn.SiLU(),
            nn.Linear(hidden, action_dim),
        )

    def forward(self, x):
        value = self.net(x)
        return torch.tanh(value) if self.output_activation == 'tanh' else value


class BCPolicy:
    def __init__(self, path):
        path = Path(path)
        self.meta = json.loads((path / "checkpoint.json").read_text(encoding="utf-8"))
        stats = np.load(path / "normalizer.npz")
        self.mean = stats["mean"].astype(np.float32)
        self.std = stats["std"].astype(np.float32)
        self.action_dim = int(self.meta.get("action_dim", 6))
        self.throttle_mode = self.meta.get("throttle_mode", "tanh")
        self.model = MLP(
            observation_dim=int(self.meta.get("observation_dim", 22)),
            action_dim=self.action_dim,
            hidden=int(self.meta.get("hidden", 256)),
            output_activation=None if self.throttle_mode == 'sigmoid' else 'tanh',
        )
        self.model.load_state_dict(torch.load(path / "model.pt", map_location="cpu", weights_only=True))
        self.model.eval()

    @torch.no_grad()
    def action(self, observation):
        x = (np.asarray(observation, dtype=np.float32) - self.mean) / self.std
        raw = self.model(torch.from_numpy(x).unsqueeze(0))
        if self.throttle_mode == 'sigmoid':
            throttle = torch.sigmoid(raw[:, :1]) * 2. - 1.
            controls = torch.tanh(raw[:, 1:])
            y = torch.cat([throttle, controls], dim=1).numpy()[0]
        else:
            y = raw.numpy()[0]
        return np.clip(y, -1., 1.).astype(np.float32)
