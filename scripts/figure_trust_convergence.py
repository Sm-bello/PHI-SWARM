#!/usr/bin/env python3
"""
Figure: trust-score convergence, honest node vs. a node sending valid-
signature-but-malicious updates every round. This is the visual companion
to Test 1 in validate_l5_l9.py — shows the quarantine line actually being
crossed, and how many rounds it takes.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np

from zerotwin.crypto import NodeKeypair, sign_parameters
from zerotwin.integrity.gate import IntegrityGate, UpdateEnvelope
from zerotwin.trust.reputation import TrustFabric

SHAPES = [(32, 4, 3), (32,), (32, 32), (32,), (5, 32), (5,)]


def fake_delta(scale, rng):
    return [rng.normal(0, 0.01, size=s).astype(np.float32) * scale for s in SHAPES]


def main():
    gate_honest, trust_honest = IntegrityGate(), TrustFabric()
    gate_bad, trust_bad = IntegrityGate(), TrustFabric()
    key_h, key_b = NodeKeypair.generate(1), NodeKeypair.generate(2)
    rng = np.random.default_rng(0)

    honest_scores, bad_scores = [], []
    n_rounds = 20
    for r in range(1, n_rounds + 1):
        d = fake_delta(1.0, rng)
        sig = sign_parameters(key_h, d)
        env = UpdateEnvelope(node_id=1, round_id=r, delta=d, signature=sig, public_key=key_h.public_key,
                              local_health=0.9, claimed_fault=0)
        dec = gate_honest.check(env, node_trust=trust_honest.weight(1))
        trust_honest.record_decision(1, dec.accepted, dec.physics_score, "bad_signature" in dec.reasons)
        honest_scores.append(trust_honest.ensure(1).score)

        d2 = fake_delta(30.0, rng)  # oversized malicious delta, honestly signed
        sig2 = sign_parameters(key_b, d2)
        env2 = UpdateEnvelope(node_id=2, round_id=r, delta=d2, signature=sig2, public_key=key_b.public_key,
                               local_health=0.30, claimed_fault=0)
        dec2 = gate_bad.check(env2, node_trust=trust_bad.weight(2))
        trust_bad.record_decision(2, dec2.accepted, dec2.physics_score, "bad_signature" in dec2.reasons)
        bad_scores.append(trust_bad.ensure(2).score)

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(7, 4.2))
        rounds = list(range(1, n_rounds + 1))
        ax.plot(rounds, honest_scores, marker="o", markersize=3, color="#16a34a", label="Honest node")
        ax.plot(rounds, bad_scores, marker="o", markersize=3, color="#dc2626",
                 label="Malicious node (valid signature, physics-inconsistent + oversized delta)")
        ax.axhline(0.25, color="#64748b", linestyle="--", linewidth=1, label="Quarantine threshold (0.25)")
        ax.set_xlabel("Federated round")
        ax.set_ylabel("Trust score")
        ax.set_ylim(0, 1.05)
        ax.set_title("Trust-fabric convergence under sustained attack (L5/L6)")
        ax.legend(fontsize=8, loc="center right")
        fig.tight_layout()
        out_dir = ROOT / "zerotwin" / "results" / "figures"
        out_dir.mkdir(parents=True, exist_ok=True)
        fig.savefig(out_dir / "trust_convergence.png", dpi=150)
        print(f"Wrote {out_dir / 'trust_convergence.png'}")
    except Exception as exc:
        print(f"[!] figure generation skipped: {exc}")

    quarantine_round = next((r for r, s in zip(rounds, bad_scores) if s < 0.25), None)
    print(f"honest final score: {honest_scores[-1]:.3f}")
    print(f"malicious final score: {bad_scores[-1]:.3f}")
    print(f"malicious node crossed quarantine line at round: {quarantine_round}")


if __name__ == "__main__":
    main()
