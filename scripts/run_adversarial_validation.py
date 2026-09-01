#!/usr/bin/env python3
"""
L5–L6 adversarial validation: malicious-but-signed updates + replay attacks.

Proves: Authentication ≠ behavioral trust.
  - Valid Ed25519 signature does NOT force acceptance.
  - Replay of a prior round is REJECTED.
  - Norm anomaly / physics inconsistency → reject + trust drop.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from zerotwin.physics import generate_node_dataset
from zerotwin.models import UAVPHMModel
from zerotwin.federated.train_utils import (
    train_local,
    evaluate,
    get_parameters,
    set_parameters,
    average_parameters,
)
from zerotwin.crypto import NodeKeypair, sign_parameters
from zerotwin.integrity.gate import IntegrityGate, UpdateEnvelope
from zerotwin.trust.reputation import TrustFabric
from zerotwin.autonomy.health_state import health_from_status


def _delta(local, global_p):
    return [lp - gp for lp, gp in zip(local, global_p)]


def main():
    seed, nodes, samples, rounds = 42, 5, 400, 6
    rng = np.random.default_rng(seed)
    results_dir = ROOT / "zerotwin" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    local = {}
    for i in range(1, nodes + 1):
        X, y = generate_node_dataset(i, n_samples=samples, seed=seed)
        n = len(y)
        s = int(0.8 * n)
        local[i] = {"Xtr": X[:s], "ytr": y[:s], "Xte": X[s:], "yte": y[s:]}

    Xte = np.concatenate([local[i]["Xte"] for i in local])
    yte = np.concatenate([local[i]["yte"] for i in local])

    keys = {i: NodeKeypair.generate(i) for i in range(1, nodes + 1)}
    gate = IntegrityGate(norm_z_threshold=3.0, min_history=3)
    trust = TrustFabric(quarantine_below=0.3)

    global_model = UAVPHMModel()
    g_params = get_parameters(global_model)

    # Warm history with honest deltas so norm baseline is meaningful
    for r in range(1, 4):
        honest_deltas = []
        for i in range(1, nodes + 1):
            m = UAVPHMModel()
            set_parameters(m, g_params)
            train_local(m, local[i]["Xtr"], local[i]["ytr"], epochs=1)
            d = _delta(get_parameters(m), g_params)
            honest_deltas.append(d)
            env = UpdateEnvelope(
                node_id=i, round_id=r, delta=d,
                signature=sign_parameters(keys[i], d),
                public_key=keys[i].public_key,
                local_health=0.9, claimed_fault=0,
            )
            dec = gate.check(env, node_trust=trust.weight(i))
            trust.record_decision(i, dec.accepted, dec.physics_score, "bad_signature" in dec.reasons)
        # aggregate first honest only for warm-up
        abs_list = [[gp + d for gp, d in zip(g_params, d)] for d in honest_deltas]
        g_params = average_parameters(abs_list, [1.0] * len(abs_list))
        set_parameters(global_model, g_params)

    log = []

    # ---- Test 1: malicious signed update (scale bomb) on node 4 ----
    m = UAVPHMModel()
    set_parameters(m, g_params)
    train_local(m, local[4]["Xtr"], local[4]["ytr"], epochs=1)
    d_mal = _delta(get_parameters(m), g_params)
    d_mal = [x * 40.0 for x in d_mal]  # magnitude attack, still signed
    sig = sign_parameters(keys[4], d_mal)
    env = UpdateEnvelope(
        node_id=4, round_id=10, delta=d_mal,
        signature=sig, public_key=keys[4].public_key,
        local_health=0.9, claimed_fault=0,
    )
    dec = gate.check(env, node_trust=trust.weight(4))
    trust.record_decision(4, dec.accepted, dec.physics_score, "bad_signature" in dec.reasons)
    log.append({
        "test": "malicious_signed_scale",
        "node": 4,
        "signature_valid": True,
        "accepted": dec.accepted,
        "reasons": dec.reasons,
        "trust_after": trust.ensure(4).score,
        "quarantined": trust.ensure(4).quarantined,
        "pass": (not dec.accepted),
    })

    # ---- Test 1b: physics-inconsistent claim (healthy claim, low health) ----
    m = UAVPHMModel()
    set_parameters(m, g_params)
    train_local(m, local[3]["Xtr"], local[3]["ytr"], epochs=1)
    d = _delta(get_parameters(m), g_params)
    sig = sign_parameters(keys[3], d)
    env = UpdateEnvelope(
        node_id=3, round_id=11, delta=d,
        signature=sig, public_key=keys[3].public_key,
        local_health=0.25, claimed_fault=0,  # claims normal while health low
    )
    dec = gate.check(env, node_trust=trust.weight(3))
    trust.record_decision(3, dec.accepted, dec.physics_score, "bad_signature" in dec.reasons)
    log.append({
        "test": "physics_inconsistent_claim",
        "node": 3,
        "signature_valid": True,
        "accepted": dec.accepted,
        "reasons": dec.reasons,
        "physics_score": dec.physics_score,
        "trust_after": trust.ensure(3).score,
        "pass": (not dec.accepted) or (dec.weight < 0.5),
    })

    # ---- Test 2: replay (dedicated gate — not polluted by prior attack norms) ----
    replay_gate = IntegrityGate(norm_z_threshold=3.0, min_history=8)
    m = UAVPHMModel()
    set_parameters(m, g_params)
    train_local(m, local[2]["Xtr"], local[2]["ytr"], epochs=1)
    d = _delta(get_parameters(m), g_params)
    sig = sign_parameters(keys[2], d)
    env_ok = UpdateEnvelope(
        node_id=2, round_id=20, delta=d,
        signature=sig, public_key=keys[2].public_key,
        local_health=0.9, claimed_fault=0,
    )
    dec1 = replay_gate.check(env_ok, node_trust=1.0)
    env_replay = UpdateEnvelope(
        node_id=2, round_id=20, delta=d,
        signature=sig, public_key=keys[2].public_key,
        local_health=0.9, claimed_fault=0,
    )
    dec2 = replay_gate.check(env_replay, node_trust=1.0)
    log.append({
        "test": "replay_attack",
        "node": 2,
        "first_accepted": dec1.accepted,
        "replay_accepted": dec2.accepted,
        "replay_reasons": dec2.reasons,
        "pass": bool(dec1.accepted) and (not dec2.accepted),
    })

    # ---- Test 1c: tampered after sign ----
    m = UAVPHMModel()
    set_parameters(m, g_params)
    train_local(m, local[5]["Xtr"], local[5]["ytr"], epochs=1)
    d = _delta(get_parameters(m), g_params)
    sig = sign_parameters(keys[5], d)
    d_tampered = [x + rng.normal(0, 0.3, size=x.shape).astype(x.dtype) for x in d]
    env = UpdateEnvelope(
        node_id=5, round_id=21, delta=d_tampered,
        signature=sig, public_key=keys[5].public_key,
        local_health=0.9, claimed_fault=0,
    )
    dec = gate.check(env, node_trust=trust.weight(5))
    trust.record_decision(5, dec.accepted, dec.physics_score, "bad_signature" in dec.reasons)
    log.append({
        "test": "tamper_after_sign",
        "node": 5,
        "accepted": dec.accepted,
        "reasons": dec.reasons,
        "pass": not dec.accepted,
    })

    all_pass = all(t["pass"] for t in log)
    out = {
        "suite": "adversarial_L5_L6",
        "all_pass": all_pass,
        "tests": log,
        "trust_snapshot": trust.snapshot(),
        "claim": "Valid signature alone does not force acceptance; replay is rejected.",
    }
    path = results_dir / "adversarial_validation.json"
    path.write_text(json.dumps(out, indent=2))

    print("=== Adversarial validation (L5–L6) ===")
    for t in log:
        status = "PASS" if t["pass"] else "FAIL"
        print(f"  [{status}] {t['test']}: { {k: v for k, v in t.items() if k not in ('test',)} }")
    print(f"all_pass={all_pass} → {path}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
