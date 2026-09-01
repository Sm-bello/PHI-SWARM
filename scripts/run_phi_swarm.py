#!/usr/bin/env python3
"""
PHI-SWARM continuous simulation (L0–L9 software stack).

Runs the integrated engine: physics twin, federated PHM, integrity gate,
trust fabric, risk/decision/safety, swarm coordination, encrypted messaging,
hash-chained audit trail.

Usage:
  python scripts/run_phi_swarm.py --minutes 10 --nodes 5
  python scripts/run_phi_swarm.py --minutes 2 --round-interval 2
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from zerotwin.simulation.phi_swarm_engine import PHISwarmEngine

STATUS = {"HEALTHY": "OK  ", "WARNING": "WARN", "CRITICAL": "CRIT", "LINK-LOST": "LOST"}


def main():
    ap = argparse.ArgumentParser(description="PHI-SWARM continuous simulation")
    ap.add_argument("--minutes", type=float, default=10.0)
    ap.add_argument("--nodes", type=int, default=5)
    ap.add_argument("--samples", type=int, default=300)
    ap.add_argument("--round-interval", type=float, default=3.0)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--attack-probability", type=float, default=0.2)
    args = ap.parse_args()

    duration = args.minutes * 60.0
    print("=== PHI-SWARM Live Simulation (L0–L9 software) ===")
    print(f"nodes={args.nodes}  duration={args.minutes:.1f} min  round_interval={args.round_interval}s")
    print("Audit: zerotwin/results/audit_trail.jsonl\n")

    engine = PHISwarmEngine(
        num_nodes=args.nodes,
        seed=args.seed,
        samples_per_node=args.samples,
        round_interval=args.round_interval,
        attack_probability=args.attack_probability,
        reset_audit=True,  # fresh chain each scripted run → verify can succeed
    )
    engine.start()

    last_round = -1
    last_print = 0.0
    try:
        t0 = time.time()
        while time.time() - t0 < duration:
            state = engine.get_state()
            if state["fed_round"] != last_round:
                last_round = state["fed_round"]
                sec = state["security"]
                print(
                    f"[round {state['fed_round']:>4}] acc={state['global_accuracy']:.4f}  "
                    f"acc/rej={sec['accepted_updates']}/{sec['rejected_updates']}  "
                    f"enc={sec['encrypted_messages']} blocked={sec['eavesdrops_blocked']}"
                )
                if state.get("directives"):
                    roles = ", ".join(f"N{d['node_id']}:{d['role']}" for d in state["directives"])
                    print(f"         swarm roles: {roles}")
            now = time.time()
            if now - last_print >= 5.0:
                last_print = now
                trust = state.get("trust", {})
                for nid, n in state["nodes"].items():
                    ts = trust.get(int(nid), trust.get(str(nid), {}))
                    tscore = ts.get("score", 0) if isinstance(ts, dict) else 0
                    print(
                        f"    {n['name']:<7} [{STATUS.get(n['status'], '?')}] "
                        f"fault={n['fault_type']:<15} conf={n['confidence']:>3}% "
                        f"trust={tscore:.2f}  vib={n['vib']:.3f}"
                    )
                print()
            time.sleep(0.4)
    except KeyboardInterrupt:
        print("\n[!] Stopped by user.")
    finally:
        engine.stop()

    state = engine.get_state()
    verify = engine.audit_verify()
    summary = {
        "framework": "PHI-SWARM",
        "elapsed_seconds": state["elapsed_seconds"],
        "fed_rounds": state["fed_round"],
        "global_accuracy": state["global_accuracy"],
        "security": state["security"],
        "trust": state.get("trust"),
        "directives": state.get("directives"),
        "audit_verified": verify.get("verified"),
        "levels_active": state.get("levels_active"),
    }
    out = ROOT / "zerotwin" / "results" / "phi_swarm_summary.json"
    out.write_text(json.dumps(summary, indent=2))

    print("\n=== PHI-SWARM summary ===")
    print(f"Rounds: {state['fed_round']}  Acc: {state['global_accuracy']:.4f}")
    print(f"Accepted/Rejected: {state['security']['accepted_updates']}/{state['security']['rejected_updates']}")
    print(f"Encrypted msgs / eavesdrops blocked: {state['security']['encrypted_messages']}/{state['security']['eavesdrops_blocked']}")
    print(f"Audit verified: {verify.get('verified')}")
    print(f"Wrote {out}")
    print("=========================\n")


if __name__ == "__main__":
    main()
