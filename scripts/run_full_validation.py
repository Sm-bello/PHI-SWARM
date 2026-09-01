#!/usr/bin/env python3
"""
Full validation suite (software lab gates for TRL-4 trajectory).

Runs:
  1) Integrity experiment (centralized / isolated / federated + optional attacks)
  2) Seed sweep (multi-seed mean ± std)
  3) Link-loss resilience sweep
  4) Edge benchmark
  5) Short PHI-SWARM live run + audit verify

Produces zerotwin/results/validation_suite.json
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def run_cmd(args: list[str], timeout: int = 600) -> dict:
    t0 = time.time()
    p = subprocess.run(
        [sys.executable, *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return {
        "cmd": args,
        "returncode": p.returncode,
        "seconds": round(time.time() - t0, 2),
        "stdout_tail": p.stdout[-2000:] if p.stdout else "",
        "stderr_tail": p.stderr[-1000:] if p.stderr else "",
        "ok": p.returncode == 0,
    }


def main():
    results_dir = ROOT / "zerotwin" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    suite = {"steps": [], "started": time.time()}

    print("=== PHI-SWARM / ZeroTwin full validation suite ===\n")

    steps = [
        ("integrity", ["scripts/run_integrity_experiment.py", "--nodes", "5", "--rounds", "6", "--samples", "400", "--seed", "42"]),
        ("seed_sweep", ["scripts/run_seed_sweep.py"]),
        ("link_loss", ["scripts/run_link_loss_sweep.py"]),
        ("edge", ["scripts/benchmark_edge.py"]),
        ("phi_swarm_2min", ["scripts/run_phi_swarm.py", "--minutes", "2", "--round-interval", "2", "--nodes", "5"]),
    ]

    # seed_sweep with 20 seeds × 8 rounds is multi-hour on CPU; allow 3600s.
    timeouts = {
        "integrity": 600,
        "seed_sweep": 3600,
        "link_loss": 900,
        "edge": 120,
        "phi_swarm_2min": 300,
    }
    for name, cmd in steps:
        print(f"--- {name}: {' '.join(cmd)}")
        try:
            r = run_cmd(cmd, timeout=timeouts.get(name, 900))
        except subprocess.TimeoutExpired:
            r = {"cmd": cmd, "ok": False, "error": "timeout", "seconds": None}
        suite["steps"].append({"name": name, **r})
        print(f"    ok={r.get('ok')}  seconds={r.get('seconds')}\n")

    # collect metric files if present
    artifacts = {}
    for fname in [
        "integrity_metrics.json",
        "seed_sweep.json",
        "resilience_results.json",
        "edge_benchmark.json",
        "phi_swarm_summary.json",
    ]:
        p = results_dir / fname
        if p.exists():
            try:
                artifacts[fname] = json.loads(p.read_text())
            except Exception as e:
                artifacts[fname] = {"error": str(e)}

    suite["artifacts"] = artifacts
    suite["elapsed_seconds"] = round(time.time() - suite["started"], 2)
    suite["all_ok"] = all(s.get("ok") for s in suite["steps"])

    out = results_dir / "validation_suite.json"
    # don't embed huge stdout in final if needed — keep summary
    slim = {
        "all_ok": suite["all_ok"],
        "elapsed_seconds": suite["elapsed_seconds"],
        "steps": [{"name": s["name"], "ok": s.get("ok"), "seconds": s.get("seconds")} for s in suite["steps"]],
        "artifacts_present": list(artifacts.keys()),
    }
    out.write_text(json.dumps(slim, indent=2))
    print(f"=== Suite complete all_ok={slim['all_ok']} → {out} ===")


if __name__ == "__main__":
    main()
