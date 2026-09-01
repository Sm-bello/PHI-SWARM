#!/usr/bin/env python3
"""
Sweeps link_loss_rounds and reports the resulting federated-resilience
curve: how much does temporarily skipping aggregation for K rounds cost,
and does accuracy recover afterward. This is a simulated connectivity
experiment (skip-aggregation), not an RF/EW claim.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.run_integrity_experiment import run as run_experiment


def main():
    ap = argparse.ArgumentParser(description="ZeroTwin link-loss resilience sweep")
    ap.add_argument("--loss-rounds", type=int, nargs="+", default=[0, 1, 2, 4, 6])
    ap.add_argument("--rounds", type=int, default=12)
    ap.add_argument("--samples", type=int, default=400)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    results_dir = ROOT / "zerotwin" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    curve = []
    for k in args.loss_rounds:
        m = run_experiment(
            nodes=5, rounds=args.rounds, seed=args.seed,
            link_loss_rounds=k, samples=args.samples,
            attack_rate=0.0, write_output=False, quiet=True,
        )
        curve.append({
            "link_loss_rounds": k,
            "final_accuracy": m["accuracy_federated"],
            "history_global_acc": m["history"]["global_acc"],
        })
        print(f"link_loss_rounds={k:<2}  final_accuracy={m['accuracy_federated']:.4f}")

    out = {"config": vars(args), "curve": curve}
    out_path = results_dir / "resilience_results.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"Wrote {out_path}")

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(7, 4))
        for c in curve:
            ax.plot(range(1, len(c["history_global_acc"]) + 1), c["history_global_acc"],
                     marker="o", markersize=3, label=f"loss={c['link_loss_rounds']} rounds")
        ax.set_xlabel("Federated round")
        ax.set_ylabel("Global test accuracy")
        ax.set_title("Federated resilience under simulated link loss")
        ax.legend(fontsize=8)
        fig.tight_layout()
        fig_dir = results_dir / "figures"
        fig_dir.mkdir(exist_ok=True)
        fig.savefig(fig_dir / "resilience_curve.png", dpi=150)
        print(f"Wrote {fig_dir / 'resilience_curve.png'}")
    except Exception as exc:
        print(f"[!] figure generation skipped: {exc}")


if __name__ == "__main__":
    main()
