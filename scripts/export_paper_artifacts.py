#!/usr/bin/env python3
"""
Export publication datasets (CSV) and figures (PNG) for community reproducibility.

Writes under:
  zerotwin/results/data/
  zerotwin/results/figures/

Only scientific artifacts — not UI screenshots.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np

RESULTS = ROOT / "zerotwin" / "results"
DATA = RESULTS / "data"
FIGS = RESULTS / "figures"
DATA.mkdir(parents=True, exist_ok=True)
FIGS.mkdir(parents=True, exist_ok=True)


def _load(name):
    p = RESULTS / name
    if not p.exists():
        return None
    return json.loads(p.read_text())


def write_csv(path: Path, rows: list[dict]):
    if not rows:
        return
    fields = []
    for r in rows:
        for k in r.keys():
            if k not in fields:
                fields.append(k)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"  wrote {path}")


def fig_physics():
    from zerotwin.physics import generate_window_batch, FAULT_NAMES

    rows = []
    for label, name in enumerate(FAULT_NAMES):
        for sev in (0.3, 0.8, 1.4):
            X, _ = generate_window_batch(label, 20, window_len=8, severity=sev)
            # X: (n, T, C)
            mean = X.mean(axis=(0, 1))
            rows.append({
                "fault": name,
                "severity": sev,
                "vib_mean": float(mean[0]),
                "temp_mean": float(mean[1]),
                "volt_mean": float(mean[2]),
                "acoustic_mean": float(mean[3]) if len(mean) > 3 else 0.0,
            })
    write_csv(DATA / "figure_01_physics.csv", rows)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        faults = sorted(set(r["fault"] for r in rows))
        fig, ax = plt.subplots(figsize=(7, 4))
        for f in faults:
            xs = [r["severity"] for r in rows if r["fault"] == f]
            ys = [r["vib_mean"] for r in rows if r["fault"] == f]
            ax.plot(xs, ys, marker="o", label=f)
        ax.set_xlabel("Severity")
        ax.set_ylabel("Mean vibration")
        ax.set_title("Physics engines — vibration vs severity")
        ax.legend(fontsize=8)
        fig.tight_layout()
        fig.savefig(FIGS / "figure_01_physics.png", dpi=150)
        plt.close()
        print(f"  wrote {FIGS / 'figure_01_physics.png'}")
    except Exception as e:
        print(f"  figure_01 skip: {e}")


def fig_federation():
    im = _load("integrity_metrics.json") or {}
    rows = []
    mapping = [
        ("centralized", im.get("accuracy_centralized", im.get("centralized_accuracy", im.get("centralized")))),
        ("isolated_mean", im.get("accuracy_isolated_mean", im.get("isolated_mean_accuracy", im.get("isolated_mean")))),
        ("federated", im.get("accuracy_federated", im.get("federated_accuracy", im.get("zerotwin_accuracy")))),
    ]
    for name, val in mapping:
        if val is not None:
            rows.append({"method": name, "accuracy": float(val)})
    write_csv(DATA / "figure_02_federation.csv", rows)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        if not rows:
            return
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.bar([r["method"] for r in rows], [r["accuracy"] for r in rows], color=["#64748b", "#94a3b8", "#2563eb"])
        ax.set_ylim(0, 1.05)
        ax.set_ylabel("Accuracy")
        ax.set_title("Centralized vs Isolated vs Federated")
        fig.tight_layout()
        fig.savefig(FIGS / "figure_02_federation.png", dpi=150)
        plt.close()
        print(f"  wrote {FIGS / 'figure_02_federation.png'}")
    except Exception as e:
        print(f"  figure_02 skip: {e}")


def fig_resilience():
    res = _load("resilience_results.json") or {}
    rows = []
    # flexible shapes
    if isinstance(res, dict):
        for k, v in res.items():
            if isinstance(v, (int, float)):
                rows.append({"key": k, "value": float(v)})
            elif isinstance(v, dict):
                rows.append({"key": k, **{sk: sv for sk, sv in v.items() if isinstance(sv, (int, float))}})
            elif isinstance(v, list):
                for i, item in enumerate(v):
                    if isinstance(item, dict):
                        rows.append({"idx": i, **item})
                    else:
                        rows.append({"idx": i, "value": item})
    if rows:
        write_csv(DATA / "figure_03_resilience.csv", rows)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        # try common keys
        xs, ys = [], []
        if isinstance(res, dict) and "results" in res:
            for item in res["results"]:
                xs.append(item.get("link_loss_rounds", item.get("loss", i)))
                ys.append(item.get("federated_accuracy", item.get("accuracy", 0)))
        elif isinstance(res, list):
            for item in res:
                xs.append(item.get("link_loss_rounds", item.get("loss", 0)))
                ys.append(item.get("federated_accuracy", item.get("accuracy", 0)))
        if xs:
            fig, ax = plt.subplots(figsize=(6, 4))
            ax.plot(xs, ys, marker="o")
            ax.set_xlabel("Link-loss rounds")
            ax.set_ylabel("Federated accuracy")
            ax.set_title("Resilience curve")
            fig.tight_layout()
            fig.savefig(FIGS / "figure_03_resilience.png", dpi=150)
            plt.close()
            print(f"  wrote {FIGS / 'figure_03_resilience.png'}")
    except Exception as e:
        print(f"  figure_03 skip: {e}")


def fig_integrity():
    adv = _load("adversarial_validation.json") or {}
    rows = []
    for t in adv.get("tests", []):
        rows.append({
            "test": t.get("test"),
            "pass": t.get("pass"),
            "accepted": t.get("accepted", t.get("replay_accepted")),
            "reasons": json.dumps(t.get("reasons") or t.get("replay_reasons") or []),
        })
    write_csv(DATA / "figure_04_integrity.csv", rows)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        if not rows:
            return
        labels = [r["test"] for r in rows]
        vals = [1 if r["pass"] else 0 for r in rows]
        fig, ax = plt.subplots(figsize=(7, 3.5))
        ax.barh(labels, vals, color=["#16a34a" if v else "#dc2626" for v in vals])
        ax.set_xlim(0, 1.2)
        ax.set_xlabel("Pass (1) / Fail (0)")
        ax.set_title("Adversarial integrity suite")
        fig.tight_layout()
        fig.savefig(FIGS / "figure_04_integrity.png", dpi=150)
        plt.close()
        print(f"  wrote {FIGS / 'figure_04_integrity.png'}")
    except Exception as e:
        print(f"  figure_04 skip: {e}")


def fig_autonomy_swarm():
    auto = _load("autonomy_validation.json") or {}
    camp = _load("campaign_results.json") or {}
    rows = []
    for t in auto.get("tests", []):
        rows.append({"suite": "autonomy", "test": t.get("test"), "pass": t.get("pass")})
    hl = camp.get("highlights") or {}
    rows.append({"suite": "campaign", "test": "phi_reduces_attack_acceptance", "pass": hl.get("phi_reduces_attack_acceptance")})
    rows.append({"suite": "campaign", "test": "failure_escort_assigned", "pass": hl.get("failure_escort_assigned")})
    write_csv(DATA / "figure_06_autonomy.csv", rows)
    # campaign table
    crow = []
    for r in camp.get("rows", []):
        crow.append({
            "scenario": r.get("scenario"),
            "mode": r.get("mode"),
            "phi_swarm": r.get("phi_swarm"),
            "accuracy": r.get("global_accuracy"),
            "rejected": r.get("rejected"),
            "attack_acceptance_rate": r.get("attack_acceptance_rate"),
            "land_or_rtb": r.get("land_or_rtb_count"),
            "escort": r.get("escort_assignments"),
        })
    if crow:
        write_csv(DATA / "figure_07_campaign.csv", crow)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        if crow:
            modes = []
            base_acc, phi_acc = [], []
            for mode in ("normal", "attack", "failure"):
                b = next((x for x in crow if x["mode"] == mode and not x["phi_swarm"]), None)
                p = next((x for x in crow if x["mode"] == mode and x["phi_swarm"]), None)
                if b and p:
                    modes.append(mode)
                    base_acc.append(b["accuracy"] or 0)
                    phi_acc.append(p["accuracy"] or 0)
            if modes:
                x = np.arange(len(modes))
                fig, ax = plt.subplots(figsize=(6, 4))
                ax.bar(x - 0.2, base_acc, 0.4, label="baseline")
                ax.bar(x + 0.2, phi_acc, 0.4, label="PHI-SWARM")
                ax.set_xticks(x)
                ax.set_xticklabels(modes)
                ax.set_ylabel("Accuracy")
                ax.legend()
                ax.set_title("Campaign accuracy by mode")
                fig.tight_layout()
                fig.savefig(FIGS / "figure_07_swarm_recovery.png", dpi=150)
                plt.close()
                print(f"  wrote {FIGS / 'figure_07_swarm_recovery.png'}")
    except Exception as e:
        print(f"  figure_07 skip: {e}")


def fig_seed():
    seed = _load("seed_sweep.json") or {}
    rows = []
    # Preferred schema from run_seed_sweep.py
    if isinstance(seed, dict) and "per_seed" in seed:
        for r in seed["per_seed"]:
            rows.append({
                "seed": r.get("seed"),
                "accuracy_centralized": r.get("accuracy_centralized"),
                "accuracy_isolated_mean": r.get("accuracy_isolated_mean"),
                "accuracy_federated": r.get("accuracy_federated"),
                "gate_rejected": r.get("gate_rejected"),
            })
        summary = seed.get("summary") or {}
        if summary:
            for k, v in summary.items():
                if isinstance(v, (int, float)):
                    rows.append({"metric": k, "value": v})
    elif isinstance(seed, dict) and "runs" in seed:
        for r in seed["runs"]:
            rows.append(r if isinstance(r, dict) else {"value": r})
    elif isinstance(seed, list):
        rows = seed
    elif isinstance(seed, dict):
        for k, v in seed.items():
            if isinstance(v, (int, float)):
                rows.append({"metric": k, "value": v})
    if rows:
        write_csv(DATA / "figure_05_seed_sweep.csv", rows)
        print(f"  wrote {DATA / 'figure_05_seed_sweep.csv'} ({len(rows)} rows)")


def main():
    print("=== Export paper artifacts ===")
    fig_physics()
    fig_federation()
    fig_resilience()
    fig_integrity()
    fig_seed()
    fig_autonomy_swarm()
    # index
    index = {
        "data_dir": str(DATA),
        "figures_dir": str(FIGS),
        "files": sorted([p.name for p in DATA.glob("*")]) + sorted([p.name for p in FIGS.glob("figure_*.png")]),
    }
    (RESULTS / "artifact_index.json").write_text(json.dumps(index, indent=2))
    print(f"Index → {RESULTS / 'artifact_index.json'}")
    print("Done.")


if __name__ == "__main__":
    main()
