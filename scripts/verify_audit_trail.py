#!/usr/bin/env python3
"""Verify zerotwin/results/audit_trail.jsonl hash chain."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from zerotwin.audit.ledger import AuditLedger


def main():
    ap = argparse.ArgumentParser(description="Verify PHI-SWARM audit trail chain")
    ap.add_argument(
        "--path",
        type=Path,
        default=ROOT / "zerotwin" / "results" / "audit_trail.jsonl",
    )
    args = ap.parse_args()
    if not args.path.exists():
        print(f"MISSING {args.path}")
        sys.exit(2)
    led = AuditLedger(args.path, reset=False)
    report = led.verify_report()
    print(json.dumps(report, indent=2))
    # show first line meta
    with open(args.path, "r", encoding="utf-8") as f:
        first = f.readline().strip()
    if first:
        d = json.loads(first)
        print(f"first_seq={d.get('seq')} event={d.get('event_type')} prev={str(d.get('prev_hash'))[:16]}...")
    sys.exit(0 if report["verified"] else 1)


if __name__ == "__main__":
    main()
