#!/usr/bin/env python3
"""
Seed sweep: runs the integrity experiment across N seeds and reports
mean +/- std and a 95% CI for centralized / isolated / federated accuracy,
plus integrity-gate accept/reject counts. Answers "maybe seed 42 just
happened to work" with a distribution instead of one number.

Usage:
    python scripts/run_seed_sweep.py --n-seeds 20 --rounds 8 --samples 500
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np

from scripts.run_integrity_experiment import run as run_experiment


def ci95(values: list[float]) -> tuple[float, float]:
    arr = np.array(values, dtype=float)
    m, s = arr.mean(), arr.std(ddof=1) if len(arr) > 1 else 0.0
    half = 1.96 * s / max(np.sqrt(len(arr)), 1)
    return float(m - half), float(m + half)


def main():
    ap = argparse.ArgumentParser(description="ZeroTwin multi-seed statistical sweep")
    ap.add_argument("--n-seeds", type=int, default=20)
    ap.add_argument("--base-seed", type=int, default=1000)
    ap.add_argument("--nodes", type=int, default=5)
    ap.add_argument("--rounds", type=int, default=8)
    ap.add_argument("--samples", type=int, default=500)
    ap.add_argument("--attack-rate", type=float, default=0.3)
    args = ap.parse_args()

    results_dir = ROOT / "zerotwin" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    t0 = time.time()
    for k in range(args.n_seeds):
        seed = args.base_seed + k
        m = run_experiment(
            nodes=args.nodes, rounds=args.rounds, seed=seed,
            link_loss_rounds=0, samples=args.samples,
            attack_rate=args.attack_rate, write_output=False, quiet=True,
        )
        rows.append(m)
        print(f"[{k + 1:>3}/{args.n_seeds}] seed={seed}  "
              f"central={m['accuracy_centralized']:.4f}  isolated={m['accuracy_isolated_mean']:.4f}  "
              f"federated={m['accuracy_federated']:.4f}  gate_rejected={m['integrity_gate']['rejected']}")

    def col(key):
        return [r[key] for r in rows]

    summary = {}
    for key in ("accuracy_centralized", "accuracy_isolated_mean", "accuracy_federated"):
        vals = col(key)
        lo, hi = ci95(vals)
        summary[key] = {
            "mean": round(float(np.mean(vals)), 4),
            "std": round(float(np.std(vals, ddof=1)) if len(vals) > 1 else 0.0, 4),
            "min": round(float(np.min(vals)), 4),
            "max": round(float(np.max(vals)), 4),
            "ci95": [round(lo, 4), round(hi, 4)],
        }

    gain = [r["accuracy_federated"] - r["accuracy_isolated_mean"] for r in rows]
    summary["federation_gain_over_isolated"] = {
        "mean": round(float(np.mean(gain)), 4),
        "std": round(float(np.std(gain, ddof=1)) if len(gain) > 1 else 0.0, 4),
    }
    summary["integrity_gate_rejected_total"] = sum(r["integrity_gate"]["rejected"] for r in rows)
    summary["integrity_gate_accepted_total"] = sum(r["integrity_gate"]["accepted"] for r in rows)

    out = {
        "config": vars(args),
        "n_seeds": args.n_seeds,
        "elapsed_seconds": round(time.time() - t0, 1),
        "per_seed": [
            {"seed": r["seed"], "accuracy_centralized": r["accuracy_centralized"],
             "accuracy_isolated_mean": r["accuracy_isolated_mean"],
             "accuracy_federated": r["accuracy_federated"],
             "gate_rejected": r["integrity_gate"]["rejected"]}
            for r in rows
        ],
        "summary": summary,
    }

    out_path = results_dir / "seed_sweep.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)

    print("\n=== Seed sweep summary (n=%d) ===" % args.n_seeds)
    for key in ("accuracy_centralized", "accuracy_isolated_mean", "accuracy_federated"):
        s = summary[key]
        print(f"{key:<26} mean={s['mean']:.4f}  std={s['std']:.4f}  "
              f"range=[{s['min']:.4f}, {s['max']:.4f}]  95% CI=[{s['ci95'][0]:.4f}, {s['ci95'][1]:.4f}]")
    fg = summary["federation_gain_over_isolated"]
    print(f"federation_gain_over_isolated mean={fg['mean']:+.4f}  std={fg['std']:.4f}")
    print(f"integrity gate: {summary['integrity_gate_accepted_total']} accepted / "
          f"{summary['integrity_gate_rejected_total']} rejected across all seeds")
    print(f"Wrote {out_path}")
    print("==================================\n")

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(6, 4))
        labels = ["Centralized", "Isolated", "Federated\n(ZeroTwin)"]
        means = [summary["accuracy_centralized"]["mean"], summary["accuracy_isolated_mean"]["mean"],
                 summary["accuracy_federated"]["mean"]]
        stds = [summary["accuracy_centralized"]["std"], summary["accuracy_isolated_mean"]["std"],
                summary["accuracy_federated"]["std"]]
        ax.bar(labels, means, yerr=stds, capsize=6, color=["#64748b", "#d97706", "#0284c7"])
        ax.set_ylabel("Test accuracy")
        ax.set_ylim(0, 1.05)
        ax.set_title(f"ZeroTwin accuracy across {args.n_seeds} seeds (mean \u00b1 std)")
        fig.tight_layout()
        fig_path = results_dir / "figures"
        fig_path.mkdir(exist_ok=True)
        fig.savefig(fig_path / "seed_sweep_accuracy.png", dpi=150)
        print(f"Wrote {fig_path / 'seed_sweep_accuracy.png'}")
    except Exception as exc:
        print(f"[!] figure generation skipped: {exc}")


if __name__ == "__main__":
    main()
