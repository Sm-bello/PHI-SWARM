#!/usr/bin/env python3
"""
Continuous terminal stress test for ZeroTwin.

Runs the live simulation engine for a fixed duration (default 10 minutes),
printing telemetry, fault transitions, federated rounds, integrity-gate
decisions, and encrypted-message events as they happen. At the end it
verifies the hash-chained audit trail and prints a summary.

Usage:
    python scripts/run_live_simulation.py
    python scripts/run_live_simulation.py --minutes 10 --nodes 5 --round-interval 3
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from zerotwin.simulation.live_engine import LiveSimulationEngine

STATUS_GLYPH = {"HEALTHY": "OK  ", "WARNING": "WARN", "CRITICAL": "CRIT", "LINK-LOST": "LOST"}


def main():
    ap = argparse.ArgumentParser(description="ZeroTwin continuous live stress test")
    ap.add_argument("--minutes", type=float, default=10.0)
    ap.add_argument("--nodes", type=int, default=5)
    ap.add_argument("--samples", type=int, default=300)
    ap.add_argument("--round-interval", type=float, default=3.0)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--attack-probability", type=float, default=0.18)
    ap.add_argument("--message-probability", type=float, default=0.6)
    args = ap.parse_args()

    duration = args.minutes * 60.0
    print("=== ZeroTwin Live Simulation — continuous stress test ===")
    print(f"nodes={args.nodes}  duration={args.minutes:.1f} min  round_interval={args.round_interval}s")
    print("Ctrl+C to stop early. Audit trail: zerotwin/results/audit_trail.jsonl\n")

    engine = LiveSimulationEngine(
        num_nodes=args.nodes,
        seed=args.seed,
        samples_per_node=args.samples,
        round_interval=args.round_interval,
        attack_probability=args.attack_probability,
        message_probability=args.message_probability,
    )
    engine.start()

    last_round_seen = -1
    last_print = 0.0
    try:
        start = time.time()
        while time.time() - start < duration:
            state = engine.get_state()

            if state["fed_round"] != last_round_seen:
                last_round_seen = state["fed_round"]
                sec = state["security"]
                print(
                    f"[round {state['fed_round']:>4}] global_acc={state['global_accuracy']:.4f}  "
                    f"accepted={sec['accepted_updates']} rejected={sec['rejected_updates']}  "
                    f"encrypted_msgs={sec['encrypted_messages']} eavesdrops_blocked={sec['eavesdrops_blocked']} "
                    f"replays_blocked={sec['replays_blocked']}  bytes={state['bytes_transferred']:,}"
                )

            now = time.time()
            if now - last_print >= 5.0:
                last_print = now
                for nid, n in state["nodes"].items():
                    glyph = STATUS_GLYPH.get(n["status"], n["status"])
                    print(
                        f"    {n['name']:<7} [{glyph}] fault={n['fault_type']:<15} "
                        f"conf={n['confidence']:>3}%  vib={n['vib']:.3f}g  temp={n['temp']:>5.1f}C  volt={n['volt']:>5.2f}V"
                    )
                print()
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n[!] Stopped early by user.")
    finally:
        engine.stop()

    state = engine.get_state()
    verify = engine.audit_verify()

    print("\n=== Run summary ===")
    print(f"Elapsed:              {state['elapsed_seconds']:.1f} s")
    print(f"Federated rounds:     {state['fed_round']}")
    print(f"Global accuracy:      {state['global_accuracy']:.4f}")
    print(f"Model parameters:     {state['model_parameters']:,}")
    print(f"Bytes transferred:    {state['bytes_transferred']:,}")
    sec = state["security"]
    print(f"Updates accepted:     {sec['accepted_updates']}")
    print(f"Updates rejected:     {sec['rejected_updates']}  (tampered signature / anomalous norm)")
    print(f"Encrypted messages:   {sec['encrypted_messages']}")
    print(f"Eavesdrops blocked:   {sec['eavesdrops_blocked']}")
    print(f"Replays blocked:      {sec['replays_blocked']}")
    print(f"Audit trail file:     {verify['path']}")
    if verify["verified"]:
        print("Audit chain verified: PASS - no tampering detected")
    else:
        print(f"Audit chain verified: FAIL at seq {verify['first_bad_seq']}")
    print("===================\n")


if __name__ == "__main__":
    main()
