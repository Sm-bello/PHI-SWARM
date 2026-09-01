#!/usr/bin/env python3
"""Generate physics-informed synthetic windows per node (public-style corpus)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
from zerotwin.physics import generate_node_dataset, FAULT_NAMES


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples-per-node", type=int, default=2000)
    ap.add_argument("--nodes", type=int, default=5)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", type=str, default="zerotwin/data")
    args = ap.parse_args()

    out = ROOT / args.out
    out.mkdir(parents=True, exist_ok=True)

    for i in range(1, args.nodes + 1):
        X, y = generate_node_dataset(i, n_samples=args.samples_per_node, seed=args.seed)
        path = out / f"node_{i}.npz"
        np.savez_compressed(path, X=X, y=y, fault_names=np.array(FAULT_NAMES))
        print(f"wrote {path}  X={X.shape}  label_counts={np.bincount(y, minlength=5)}")

    meta = out / "README_DATA.txt"
    meta.write_text(
        "ZeroTwin physics-hybrid synthetic windows.\n"
        "X: (N, 64, 4) vibration, temperature, voltage, acoustic\n"
        "y: fault class 0..4 — " + ", ".join(FAULT_NAMES) + "\n"
        "Non-IID across nodes by construction.\n"
    )
    print(f"meta → {meta}")


if __name__ == "__main__":
    main()
