#!/usr/bin/env python3
"""
ZeroTwin integrity experiment — main scientific entrypoint.

Compares:
  - Centralized (pooled data, single model)
  - Isolated (each node trains only on local data, average accuracy)
  - Federated ZeroTwin (FedAvg over local physics-partitioned data)
  - Optional link-loss: skip aggregation for K rounds then resume
  - Optional attack injection: a fraction of rounds carry a malicious update
    (tampered-after-signing, or a valid-signature-but-anomalous-magnitude
    delta) that the integrity gate must catch and exclude from aggregation

Every round, each client's update is Ed25519-SIGNED AS A DELTA
(local_params - global_params), matching the architecture described in
docs/ARCHITECTURE.md, and is only aggregated if it passes both the
signature check and a norm-anomaly check ("integrity gate"). This was
previously only exercised in the live dashboard simulation; it now runs
inside the paper-metrics script too, so accept/reject behavior is part of
the primary reported result, not a side demo.

Raw telemetry never moves between nodes in the federated path.
"""

from __future__ import annotations

import argparse
import json
import random as _random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np

from zerotwin.physics import generate_node_dataset
from zerotwin.models import UAVPHMModel, count_parameters
from zerotwin.federated.train_utils import (
    train_local,
    evaluate,
    get_parameters,
    set_parameters,
    average_parameters,
)
from zerotwin.crypto import NodeKeypair, sign_parameters, verify_parameters


def run(
    nodes: int,
    rounds: int,
    seed: int,
    link_loss_rounds: int,
    samples: int,
    attack_rate: float = 0.0,
    write_output: bool = True,
    quiet: bool = False,
):
    py_rng = _random.Random(seed + 999)
    results_dir = ROOT / "zerotwin" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    # --- data (non-IID physics partitions) ---
    local = {}
    for i in range(1, nodes + 1):
        X, y = generate_node_dataset(i, n_samples=samples, seed=seed)
        n = len(y)
        split = int(0.8 * n)
        local[i] = {
            "Xtr": X[:split],
            "ytr": y[:split],
            "Xte": X[split:],
            "yte": y[split:],
        }

    Xtr_c = np.concatenate([local[i]["Xtr"] for i in local], axis=0)
    ytr_c = np.concatenate([local[i]["ytr"] for i in local], axis=0)
    Xte_c = np.concatenate([local[i]["Xte"] for i in local], axis=0)
    yte_c = np.concatenate([local[i]["yte"] for i in local], axis=0)

    # --- Centralized ---
    m_c = UAVPHMModel()
    train_local(m_c, Xtr_c, ytr_c, epochs=6)
    acc_central = evaluate(m_c, Xte_c, yte_c)

    # --- Isolated ---
    iso_accs = []
    for i in local:
        m = UAVPHMModel()
        train_local(m, local[i]["Xtr"], local[i]["ytr"], epochs=6)
        iso_accs.append(evaluate(m, local[i]["Xte"], local[i]["yte"]))
    acc_isolated = float(np.mean(iso_accs))

    # --- Federated, with integrity gate ---
    global_model = UAVPHMModel()
    keys = {i: NodeKeypair.generate(i) for i in local}
    history = {"round": [], "global_acc": [], "signed_ok": [], "accepted": [], "rejected": []}
    bytes_est = 0
    norm_history: list[float] = []
    gate_log = []  # per-update accept/reject decisions, for auditability

    for r in range(1, rounds + 1):
        if link_loss_rounds > 0 and (rounds // 2) < r <= (rounds // 2) + link_loss_rounds:
            history["round"].append(r)
            history["global_acc"].append(evaluate(global_model, Xte_c, yte_c))
            history["signed_ok"].append(True)
            history["accepted"].append(0)
            history["rejected"].append(0)
            continue

        g_params = get_parameters(global_model)
        accepted_params, accepted_weights = [], []
        n_accepted = n_rejected = 0

        attacker = None
        attack_kind = None
        if attack_rate > 0 and py_rng.random() < attack_rate:
            attacker = py_rng.choice(list(local))
            attack_kind = py_rng.choice(["tampered_signature", "anomalous_norm"])

        for i in local:
            m = UAVPHMModel()
            set_parameters(m, g_params)
            train_local(m, local[i]["Xtr"], local[i]["ytr"], epochs=2)
            params = get_parameters(m)
            delta = [p - gp for p, gp in zip(params, g_params)]

            is_attacker = (attacker == i)
            if is_attacker and attack_kind == "tampered_signature":
                sig = sign_parameters(keys[i], delta)
                delta = [d.copy() for d in delta]
                delta[0].flat[0] += 50.0
                params = [gp + d for gp, d in zip(g_params, delta)]
                sig_ok = verify_parameters(keys[i].public_key, delta, sig)
            elif is_attacker and attack_kind == "anomalous_norm":
                delta = [d * 25.0 for d in delta]
                params = [gp + d for gp, d in zip(g_params, delta)]
                sig = sign_parameters(keys[i], delta)
                sig_ok = verify_parameters(keys[i].public_key, delta, sig)
            else:
                sig = sign_parameters(keys[i], delta)
                sig_ok = verify_parameters(keys[i].public_key, delta, sig)

            update_norm = float(np.sqrt(sum(float(np.sum(d.astype(np.float64) ** 2)) for d in delta)))
            norm_ok = True
            if len(norm_history) >= 5:
                median = float(np.median(norm_history))
                std = float(np.std(norm_history))
                if update_norm > max(median * 5.0, median + 5.0 * (std + 1e-6)):
                    norm_ok = False

            accepted = sig_ok and norm_ok
            gate_log.append({
                "round": r, "node_id": i, "signature_ok": sig_ok, "norm_ok": norm_ok,
                "accepted": accepted, "update_norm": round(update_norm, 3),
                "simulated_attack": attack_kind if is_attacker else None,
            })

            if accepted:
                accepted_params.append(params)
                accepted_weights.append(len(local[i]["Xtr"]))
                norm_history.append(update_norm)
                if len(norm_history) > 50:
                    norm_history.pop(0)
                n_accepted += 1
                bytes_est += sum(p.nbytes for p in params)
            else:
                n_rejected += 1

        if accepted_params:
            avg = average_parameters(accepted_params, accepted_weights)
            set_parameters(global_model, avg)
        acc_g = evaluate(global_model, Xte_c, yte_c)
        history["round"].append(r)
        history["global_acc"].append(acc_g)
        history["signed_ok"].append(n_rejected == 0)
        history["accepted"].append(n_accepted)
        history["rejected"].append(n_rejected)

    acc_fed = history["global_acc"][-1] if history["global_acc"] else 0.0
    total_accepted = sum(history["accepted"])
    total_rejected = sum(history["rejected"])

    metrics = {
        "seed": seed,
        "nodes": nodes,
        "rounds": rounds,
        "samples_per_node": samples,
        "link_loss_rounds": link_loss_rounds,
        "attack_rate": attack_rate,
        "model_parameters": count_parameters(UAVPHMModel()),
        "accuracy_centralized": round(acc_central, 4),
        "accuracy_isolated_mean": round(acc_isolated, 4),
        "accuracy_federated": round(float(acc_fed), 4),
        "federation_gain_over_isolated": round(float(acc_fed) - acc_isolated, 4),
        "gap_to_centralized": round(acc_central - float(acc_fed), 4),
        "approx_param_bytes_total": int(bytes_est),
        "integrity_gate": {
            "total_updates_seen": total_accepted + total_rejected,
            "accepted": total_accepted,
            "rejected": total_rejected,
            "note": (
                "Updates are Ed25519-signed as deltas (local - global), verified, "
                "and norm-checked before aggregation. Rejected updates (tampered "
                "signature or anomalous-magnitude delta) are excluded from FedAvg."
            ),
        },
        "history": history,
        "claim_note": (
            "Federated path exchanges signed weight DELTAS only; raw telemetry "
            "stays on each node. Every delta is signature- and norm-checked "
            "before aggregation (integrity gate), not just signed."
        ),
    }

    if write_output:
        out = results_dir / "integrity_metrics.json"
        with open(out, "w") as f:
            json.dump(metrics, f, indent=2)
        gate_out = results_dir / "integrity_gate_log.json"
        with open(gate_out, "w") as f:
            json.dump(gate_log, f, indent=2)

    if not quiet:
        print("\n=== ZeroTwin Integrity Experiment ===")
        print(f"nodes={nodes}  rounds={rounds}  seed={seed}  link_loss={link_loss_rounds}  attack_rate={attack_rate}")
        print(f"Model parameters: {metrics['model_parameters']}")
        print(f"Centralized accuracy:     {metrics['accuracy_centralized']:.4f}")
        print(f"Isolated mean accuracy:   {metrics['accuracy_isolated_mean']:.4f}")
        print(f"Federated (ZeroTwin):     {metrics['accuracy_federated']:.4f}")
        print(f"Gain over isolated:       {metrics['federation_gain_over_isolated']:+.4f}")
        print(f"Gap to centralized:       {metrics['gap_to_centralized']:.4f}")
        print(f"Integrity gate:           {total_accepted} accepted / {total_rejected} rejected")
        print(f"Approx param bytes moved: {metrics['approx_param_bytes_total']}")
        if write_output:
            print(f"Wrote {results_dir / 'integrity_metrics.json'}")
        print("=====================================\n")
    return metrics


def main():
    ap = argparse.ArgumentParser(description="ZeroTwin integrity experiment")
    ap.add_argument("--nodes", type=int, default=5)
    ap.add_argument("--rounds", type=int, default=8)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--link-loss-rounds", type=int, default=0)
    ap.add_argument("--samples", type=int, default=500)
    ap.add_argument("--attack-rate", type=float, default=0.0,
                     help="probability per round that a malicious update is injected (0-1)")
    args = ap.parse_args()
    run(args.nodes, args.rounds, args.seed, args.link_loss_rounds, args.samples, args.attack_rate)


if __name__ == "__main__":
    main()
