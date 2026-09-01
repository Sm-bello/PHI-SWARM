"""
Flower client for one simulated edge node.

Raw telemetry stays local. Only model parameters are exchanged.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np

try:
    import flwr as fl
except ImportError:
    print("flwr not installed. pip install flwr")
    sys.exit(1)

from zerotwin.physics import generate_node_dataset
from zerotwin.models import UAVPHMModel
from zerotwin.federated.train_utils import (
    train_local,
    evaluate,
    get_parameters,
    set_parameters,
)
from zerotwin.crypto import NodeKeypair, sign_parameters


class PHMClient(fl.client.NumPyClient):
    def __init__(self, node_id: int, seed: int = 42):
        self.node_id = node_id
        self.model = UAVPHMModel()
        self.X, self.y = generate_node_dataset(node_id, n_samples=600, seed=seed)
        # small holdout
        n = len(self.y)
        split = int(0.8 * n)
        self.Xtr, self.ytr = self.X[:split], self.y[:split]
        self.Xte, self.yte = self.X[split:], self.y[split:]
        self.keypair = NodeKeypair.generate(node_id)

    def get_parameters(self, config):
        return get_parameters(self.model)

    def fit(self, parameters, config):
        set_parameters(self.model, parameters)
        train_local(self.model, self.Xtr, self.ytr, epochs=2)
        params = get_parameters(self.model)
        # Sign the DELTA (local - global), matching the architecture in
        # docs/ARCHITECTURE.md and scripts/run_integrity_experiment.py.
        delta = [p - g for p, g in zip(params, parameters)]
        _ = sign_parameters(self.keypair, delta)
        return params, len(self.Xtr), {}

    def evaluate(self, parameters, config):
        set_parameters(self.model, parameters)
        acc = evaluate(self.model, self.Xte, self.yte)
        return float(1.0 - acc), len(self.Xte), {"accuracy": float(acc)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--node-id", type=int, required=True)
    ap.add_argument("--server", default="127.0.0.1:8080")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    client = PHMClient(args.node_id, seed=args.seed)
    print(f"[*] Node {args.node_id} → {args.server}")
    fl.client.start_numpy_client(server_address=args.server, client=client)


if __name__ == "__main__":
    main()
