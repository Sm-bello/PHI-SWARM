"""
Physics-hybrid degradation engines for quadrotor PHM.

Four fault modes with deterministic physical structure + controlled noise.
These define the integrity of the synthetic data: labels are not arbitrary;
they follow progressive degradation laws suitable for federated PHM studies.
"""

from __future__ import annotations

import numpy as np

FAULT_NAMES = [
    "normal",
    "rotor_imbalance",
    "esc_thermal",
    "bearing_bpfo",
    "voltage_sag",
]

# Sensor order: vibration (g), temperature (C), voltage (V), acoustic (dB)
N_SENSORS = 4


def _rotor_imbalance(t: np.ndarray, severity: float, rng: np.random.Generator) -> np.ndarray:
    """Progressive centrifugal imbalance → vibration at rotational harmonic."""
    omega = 2 * np.pi * 50.0  # ~50 Hz rotor fundamental (illustrative)
    alpha = 0.002 * severity
    vib = severity * (1.0 + alpha * t) * (
        np.sin(omega * t) + 0.4 * np.cos(omega * t)
    )
    vib = vib * 0.15 + rng.normal(0, 0.02, size=t.shape)
    temp = 35.0 + 0.01 * severity * t + rng.normal(0, 0.3, size=t.shape)
    volt = 15.8 - 0.001 * t + rng.normal(0, 0.05, size=t.shape)
    acou = 32.0 + 8.0 * severity + rng.normal(0, 0.8, size=t.shape)
    return np.stack([vib, temp, volt, acou], axis=-1)


def _esc_thermal(t: np.ndarray, severity: float, rng: np.random.Generator) -> np.ndarray:
    """Lumped thermal rise under load → temperature trajectory."""
    tau = 40.0 / max(severity, 0.2)
    delta_ss = 25.0 * severity
    temp = 34.0 + delta_ss * (1.0 - np.exp(-t / tau)) + rng.normal(0, 0.4, size=t.shape)
    vib = 0.04 + 0.01 * severity + rng.normal(0, 0.01, size=t.shape)
    volt = 15.5 - 0.02 * severity * (1.0 - np.exp(-t / (tau * 1.5))) + rng.normal(0, 0.05, size=t.shape)
    acou = 30.0 + 2.0 * severity + rng.normal(0, 0.6, size=t.shape)
    return np.stack([vib, temp, volt, acou], axis=-1)


def _bearing_bpfo(t: np.ndarray, severity: float, rng: np.random.Generator) -> np.ndarray:
    """Outer-race style impulsive content in vibration."""
    f_bpfo = 87.0  # illustrative BPFO
    bursts = severity * 0.2 * np.sin(2 * np.pi * f_bpfo * t)
    # Sparse impulse envelope
    envelope = (np.sin(2 * np.pi * 3.0 * t) > 0.85).astype(float)
    vib = 0.05 + bursts * envelope + rng.normal(0, 0.015, size=t.shape)
    temp = 38.0 + 4.0 * severity + 0.005 * t + rng.normal(0, 0.3, size=t.shape)
    volt = 15.6 + rng.normal(0, 0.04, size=t.shape)
    acou = 35.0 + 15.0 * severity * envelope + rng.normal(0, 1.0, size=t.shape)
    return np.stack([vib, temp, volt, acou], axis=-1)


def _voltage_sag(t: np.ndarray, severity: float, rng: np.random.Generator) -> np.ndarray:
    """Internal resistance growth + OCV decay under load."""
    tau = 60.0
    volt = 15.9 * np.exp(-0.002 * severity * t) - 0.3 * severity * (1.0 - np.exp(-t / tau))
    volt = volt + rng.normal(0, 0.04, size=t.shape)
    vib = 0.035 + rng.normal(0, 0.01, size=t.shape)
    temp = 36.0 + 0.008 * t + rng.normal(0, 0.25, size=t.shape)
    acou = 29.0 + rng.normal(0, 0.5, size=t.shape)
    return np.stack([vib, temp, volt, acou], axis=-1)


def _normal(t: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    vib = 0.03 + rng.normal(0, 0.008, size=t.shape)
    temp = 34.0 + rng.normal(0, 0.25, size=t.shape)
    volt = 15.7 + rng.normal(0, 0.03, size=t.shape)
    acou = 28.0 + rng.normal(0, 0.4, size=t.shape)
    return np.stack([vib, temp, volt, acou], axis=-1)


_GENERATORS = {
    0: lambda t, s, r: _normal(t, r),
    1: _rotor_imbalance,
    2: _esc_thermal,
    3: _bearing_bpfo,
    4: _voltage_sag,
}


def generate_window_batch(
    fault_label: int,
    n_windows: int,
    window_len: int = 64,
    severity: float = 1.0,
    seed: int | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Returns
    -------
    X : (n_windows, window_len, N_SENSORS)
    y : (n_windows,) int labels
    """
    rng = np.random.default_rng(seed)
    fault_label = int(np.clip(fault_label, 0, 4))
    severity = float(np.clip(severity, 0.1, 2.0))
    gen = _GENERATORS[fault_label]

    X = np.zeros((n_windows, window_len, N_SENSORS), dtype=np.float32)
    for i in range(n_windows):
        t0 = rng.uniform(0, 30)
        t = np.linspace(t0, t0 + window_len / 10.0, window_len)
        if fault_label == 0:
            X[i] = gen(t, severity, rng).astype(np.float32)
        else:
            X[i] = gen(t, severity, rng).astype(np.float32)
    y = np.full(n_windows, fault_label, dtype=np.int64)
    return X, y


def generate_node_dataset(
    node_id: int,
    n_samples: int = 800,
    window_len: int = 64,
    seed: int = 42,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Non-IID partition: each node is biased toward a primary fault mode
    while still seeing some normal and secondary samples.
    """
    rng = np.random.default_rng(seed + node_id * 17)
    # Primary fault for this node (1..4); node 1 also gets strong normal
    primary = ((node_id - 1) % 4) + 1
    fractions = {
        0: 0.35 if node_id == 1 else 0.20,
        primary: 0.45,
    }
    remaining = 1.0 - sum(fractions.values())
    others = [k for k in range(5) if k not in fractions]
    for k in others:
        fractions[k] = remaining / max(len(others), 1)

    Xs, ys = [], []
    for label, frac in fractions.items():
        n = max(1, int(n_samples * frac))
        severity = float(rng.uniform(0.6, 1.4))
        X, y = generate_window_batch(label, n, window_len, severity, seed=int(rng.integers(0, 1e9)))
        Xs.append(X)
        ys.append(y)

    X = np.concatenate(Xs, axis=0)
    y = np.concatenate(ys, axis=0)
    idx = rng.permutation(len(y))
    return X[idx][:n_samples], y[idx][:n_samples]
