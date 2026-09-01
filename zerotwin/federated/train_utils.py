"""Local train / eval helpers shared by experiment and clients."""

from __future__ import annotations

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from zerotwin.models import UAVPHMModel


def make_loader(X: np.ndarray, y: np.ndarray, batch_size: int = 32, shuffle: bool = True) -> DataLoader:
    xt = torch.tensor(X, dtype=torch.float32)
    yt = torch.tensor(y, dtype=torch.long)
    return DataLoader(TensorDataset(xt, yt), batch_size=batch_size, shuffle=shuffle)


def train_local(
    model: UAVPHMModel,
    X: np.ndarray,
    y: np.ndarray,
    epochs: int = 3,
    lr: float = 1e-3,
    batch_size: int = 32,
    device: str | None = None,
) -> float:
    device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    model = model.to(device)
    model.train()
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    crit = nn.CrossEntropyLoss()
    loader = make_loader(X, y, batch_size=batch_size, shuffle=True)
    last_loss = 0.0
    for _ in range(epochs):
        for xb, yb in loader:
            xb, yb = xb.to(device), yb.to(device)
            opt.zero_grad()
            loss = crit(model(xb), yb)
            loss.backward()
            opt.step()
            last_loss = float(loss.item())
    return last_loss


@torch.no_grad()
def evaluate(model: UAVPHMModel, X: np.ndarray, y: np.ndarray, batch_size: int = 64) -> float:
    device = next(model.parameters()).device
    model.eval()
    loader = make_loader(X, y, batch_size=batch_size, shuffle=False)
    correct, total = 0, 0
    for xb, yb in loader:
        xb, yb = xb.to(device), yb.to(device)
        pred = model(xb).argmax(dim=1)
        correct += int((pred == yb).sum().item())
        total += yb.numel()
    return correct / max(total, 1)


def get_parameters(model: UAVPHMModel) -> list[np.ndarray]:
    return [p.detach().cpu().numpy().copy() for p in model.parameters()]


def set_parameters(model: UAVPHMModel, params: list[np.ndarray]) -> None:
    with torch.no_grad():
        for p, arr in zip(model.parameters(), params):
            p.copy_(torch.tensor(arr, dtype=p.dtype))


def average_parameters(param_lists: list[list[np.ndarray]], weights: list[float] | None = None) -> list[np.ndarray]:
    if not param_lists:
        raise ValueError("empty param_lists")
    n = len(param_lists)
    if weights is None:
        weights = [1.0 / n] * n
    s = float(sum(weights))
    weights = [w / s for w in weights]
    out = []
    for layer_idx in range(len(param_lists[0])):
        acc = np.zeros_like(param_lists[0][layer_idx], dtype=np.float64)
        for client_idx, params in enumerate(param_lists):
            acc += weights[client_idx] * params[layer_idx]
        out.append(acc.astype(param_lists[0][layer_idx].dtype))
    return out
