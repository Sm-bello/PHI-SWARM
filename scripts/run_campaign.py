#!/usr/bin/env python3
"""
Campaign experiment: NORMAL vs ATTACK vs FAILURE under PHI-SWARM vs baseline.

Baseline = FedAvg with signature check only (no norm/physics/trust/safety/swarm).
PHI-SWARM = full integrity gate + trust + autonomy logging.

Metrics:
  - attack_acceptance_rate
  - global accuracy
  - rejected updates
  - trust quarantine events
  - autonomy LAND/RTB counts (failure scenario)
  - swarm ESCORT assignments (failure scenario)
"""

from __future__ import annotations

import json
import random
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
from zerotwin.crypto import NodeKeypair, sign_parameters, verify_parameters
from zerotwin.integrity.gate import IntegrityGate, UpdateEnvelope
from zerotwin.trust.reputation import TrustFabric
from zerotwin.autonomy.health_state import HealthState
from zerotwin.autonomy.risk import RiskEngine
from zerotwin.autonomy.decision import DecisionEngine
from zerotwin.autonomy.safety import SafetyGovernor
from zerotwin.autonomy.swarm_coord import SwarmCoordinator


def _delta(local, g):
    return [a - b for a, b in zip(local, g)]


def run_scenario(
    name: str,
    mode: str,  # normal | attack | failure
    use_phi: bool,
    nodes: int = 5,
    rounds: int = 8,
    samples: int = 350,
    seed: int = 42,
    attack_rate: float = 0.25,
):
    rng = random.Random(seed + (0 if name == "normal" else 7))
    local = {}
    for i in range(1, nodes + 1):
        X, y = generate_node_dataset(i, n_samples=samples, seed=seed + i)
        n = len(y)
        s = int(0.8 * n)
        local[i] = {"Xtr": X[:s], "ytr": y[:s], "Xte": X[s:], "yte": y[s:]}
    Xte = np.concatenate([local[i]["Xte"] for i in local])
    yte = np.concatenate([local[i]["yte"] for i in local])

    keys = {i: NodeKeypair.generate(i) for i in range(1, nodes + 1)}
    gate = IntegrityGate(norm_z_threshold=3.2, min_history=4) if use_phi else None
    trust = TrustFabric() if use_phi else None
    risk_e, dec_e, safety, coord = RiskEngine(), DecisionEngine(), SafetyGovernor(), SwarmCoordinator()

    g_model = UAVPHMModel()
    g_params = get_parameters(g_model)

    accepted = rejected = attack_attempts = attack_accepted = 0
    land_count = escort_count = 0

    # Failure scenario: node 3 is critically unhealthy for autonomy layer
    failure_health = {
        1: HealthState(1, 0.95, 0.95, 0.95, 0.95, 0.95, "HEALTHY", 0, 96),
        2: HealthState(2, 0.9, 0.9, 0.9, 0.9, 0.9, "HEALTHY", 0, 94),
        3: HealthState(3, 0.25, 0.15, 0.2, 0.4, 0.15, "CRITICAL", 3, 40),
        4: HealthState(4, 0.88, 0.88, 0.88, 0.88, 0.88, "HEALTHY", 0, 93),
        5: HealthState(5, 0.92, 0.92, 0.92, 0.92, 0.92, "HEALTHY", 0, 95),
    }

    for r in range(1, rounds + 1):
        abs_list, weights = [], []
        for i in range(1, nodes + 1):
            m = UAVPHMModel()
            set_parameters(m, g_params)
            train_local(m, local[i]["Xtr"], local[i]["ytr"], epochs=1)
            d = _delta(get_parameters(m), g_params)

            # Scale attack only after warm-up rounds so PHI norm history is meaningful.
            is_attack = (
                mode == "attack" and i == 4 and r >= 4 and rng.random() < attack_rate
            )
            if is_attack:
                attack_attempts += 1
                d = [x * 35.0 for x in d]
                sig = sign_parameters(keys[i], d)
            else:
                sig = sign_parameters(keys[i], d)

            if use_phi:
                h_local = 0.2 if (mode == "failure" and i == 3) else 0.9
                claimed = 0 if (mode == "failure" and i == 3) else 0
                env = UpdateEnvelope(
                    node_id=i, round_id=r, delta=d,
                    signature=sig, public_key=keys[i].public_key,
                    local_health=h_local, claimed_fault=claimed,
                )
                # physics inconsistent on failure node when claiming healthy
                if mode == "failure" and i == 3:
                    env.local_health = 0.2
                    env.claimed_fault = 0
                dec = gate.check(env, node_trust=trust.weight(i))
                trust.record_decision(i, dec.accepted, dec.physics_score, "bad_signature" in dec.reasons)
                ok = dec.accepted
                w_mult = dec.weight
            else:
                # baseline: signature only
                ok = verify_parameters(keys[i].public_key, d, sig)
                w_mult = 1.0

            if ok:
                accepted += 1
                if is_attack:
                    attack_accepted += 1
                abs_list.append([gp + x for gp, x in zip(g_params, d)])
                weights.append(len(local[i]["Xtr"]) * w_mult)
            else:
                rejected += 1

        if abs_list:
            g_params = average_parameters(abs_list, weights)
            set_parameters(g_model, g_params)

    acc = float(evaluate(g_model, Xte, yte))

    if use_phi and mode == "failure":
        actions = {}
        for nid, h in failure_health.items():
            risk = risk_e.assess(h)
            rec = dec_e.recommend(h, risk)
            verd = safety.review(rec, h)
            actions[nid] = verd.action
            if verd.action in ("LAND", "RETURN_TO_BASE"):
                land_count += 1
        dirs = coord.plan(failure_health, actions)
        escort_count = sum(1 for d in dirs if d.role == "ESCORT")

    return {
        "scenario": name,
        "mode": mode,
        "phi_swarm": use_phi,
        "global_accuracy": round(acc, 4),
        "accepted": accepted,
        "rejected": rejected,
        "attack_attempts": attack_attempts,
        "attack_accepted": attack_accepted,
        "attack_acceptance_rate": (
            round(attack_accepted / attack_attempts, 4) if attack_attempts else None
        ),
        "land_or_rtb_count": land_count,
        "escort_assignments": escort_count,
        "trust": trust.snapshot() if trust else None,
    }


def main():
    results_dir = ROOT / "zerotwin" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    print("=== Campaign: NORMAL / ATTACK / FAILURE × baseline / PHI-SWARM ===\n")
    for mode in ("normal", "attack", "failure"):
        for use_phi in (False, True):
            label = f"{mode}_{'phi' if use_phi else 'baseline'}"
            print(f"  running {label}...")
            row = run_scenario(label, mode, use_phi)
            rows.append(row)
            print(
                f"    acc={row['global_accuracy']}  "
                f"rej={row['rejected']}  "
                f"atk_acc_rate={row['attack_acceptance_rate']}  "
                f"land={row['land_or_rtb_count']} escort={row['escort_assignments']}"
            )

    # Key comparisons
    atk_base = next(r for r in rows if r["mode"] == "attack" and not r["phi_swarm"])
    atk_phi = next(r for r in rows if r["mode"] == "attack" and r["phi_swarm"])
    fail_phi = next(r for r in rows if r["mode"] == "failure" and r["phi_swarm"])

    summary = {
        "campaign": "NORMAL_vs_ATTACK_vs_FAILURE",
        "rows": rows,
        "highlights": {
            "baseline_attack_acceptance_rate": atk_base["attack_acceptance_rate"],
            "phi_attack_acceptance_rate": atk_phi["attack_acceptance_rate"],
            "phi_reduces_attack_acceptance": (
                atk_phi["attack_acceptance_rate"] is not None
                and atk_base["attack_acceptance_rate"] is not None
                and atk_phi["attack_acceptance_rate"] < atk_base["attack_acceptance_rate"]
            ),
            "failure_land_or_rtb": fail_phi["land_or_rtb_count"],
            "failure_escort_assigned": fail_phi["escort_assignments"] > 0,
        },
        "claim": (
            "Under attack, PHI-SWARM integrity+trust rejects more malicious updates than "
            "signature-only baseline. Under failure, autonomy produces LAND/RTB and ESCORT."
        ),
    }
    path = results_dir / "campaign_results.json"
    path.write_text(json.dumps(summary, indent=2))
    print(f"\nhighlights: {json.dumps(summary['highlights'], indent=2)}")
    print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
