"""
Flower aggregation server entrypoint.

For paper metrics prefer: python scripts/run_integrity_experiment.py
This module is for multi-terminal / remote SuperLink-style demos.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root on path
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import flwr as fl
except ImportError:
    print("flwr not installed. pip install flwr")
    sys.exit(1)

from zerotwin.models import UAVPHMModel
from zerotwin.federated.train_utils import get_parameters


def main(address: str = "0.0.0.0:8080", num_rounds: int = 20, min_clients: int = 2):
    model = UAVPHMModel()
    init = fl.common.ndarrays_to_parameters(get_parameters(model))

    strategy = fl.server.strategy.FedAvg(
        fraction_fit=1.0,
        fraction_evaluate=1.0,
        min_fit_clients=min_clients,
        min_evaluate_clients=min_clients,
        min_available_clients=min_clients,
        initial_parameters=init,
    )

    print(f"[*] ZeroTwin Flower server on {address}  rounds={num_rounds}")
    fl.server.start_server(
        server_address=address,
        config=fl.server.ServerConfig(num_rounds=num_rounds),
        strategy=strategy,
    )


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--address", default="0.0.0.0:8080")
    p.add_argument("--rounds", type=int, default=20)
    p.add_argument("--min-clients", type=int, default=2)
    args = p.parse_args()
    main(args.address, args.rounds, args.min_clients)
