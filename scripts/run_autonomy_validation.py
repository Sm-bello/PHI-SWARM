#!/usr/bin/env python3
"""
L7–L9 autonomy validation: forced degradation + swarm compensation.

Test 3: low health → HIGH/CRITICAL risk → RTB/LAND → safety approves conservative action
Test 4: one UAV LAND → coordinator assigns EGRESS + ESCORT on healthiest node
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from zerotwin.autonomy.health_state import HealthState, health_from_status
from zerotwin.autonomy.risk import RiskEngine
from zerotwin.autonomy.decision import DecisionEngine
from zerotwin.autonomy.safety import SafetyGovernor
from zerotwin.autonomy.swarm_coord import SwarmCoordinator


def main():
    results_dir = ROOT / "zerotwin" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    risk_e = RiskEngine()
    dec_e = DecisionEngine()
    safety = SafetyGovernor()
    coord = SwarmCoordinator()

    tests = []

    # ---- Test 3a: critical bearing + battery → LAND ----
    h = HealthState(
        node_id=3, motor=0.7, battery=0.18, bearing=0.22, thermal=0.6,
        overall=0.18, status="CRITICAL", fault_label=3, confidence=55.0,
    )
    r = risk_e.assess(h)
    rec = dec_e.recommend(h, r)
    verd = safety.review(rec, h)
    tests.append({
        "test": "critical_degradation_to_land",
        "health_overall": h.overall,
        "risk": r.level,
        "ai_action": rec.action,
        "final_action": verd.action,
        "safety_reasons": verd.reasons,
        "pass": verd.action in ("LAND", "RETURN_TO_BASE") and r.level in ("HIGH", "CRITICAL"),
    })

    # ---- Test 3b: medium degradation → REDUCE_SPEED or CHANGE_ROLE ----
    h2 = health_from_status(1, "WARNING", fault_label=4, confidence=62.0, severity=0.85)
    r2 = risk_e.assess(h2)
    rec2 = dec_e.recommend(h2, r2)
    verd2 = safety.review(rec2, h2)
    tests.append({
        "test": "medium_degradation_conservative",
        "health_overall": h2.overall,
        "risk": r2.level,
        "ai_action": rec2.action,
        "final_action": verd2.action,
        "pass": verd2.action != "CONTINUE",
    })

    # ---- Test 3c: safety overrides CONTINUE when battery floor hit ----
    h3 = HealthState(
        node_id=2, motor=0.8, battery=0.12, bearing=0.8, thermal=0.8,
        overall=0.5, status="WARNING", fault_label=4, confidence=70.0,
    )
    # Force AI to propose CONTINUE (simulate optimistic AI)
    from zerotwin.autonomy.decision import MissionDecision
    optimistic = MissionDecision(2, "CONTINUE", "optimistic", 0.6)
    verd3 = safety.review(optimistic, h3)
    tests.append({
        "test": "safety_overrides_continue_on_battery_floor",
        "ai_action": "CONTINUE",
        "final_action": verd3.action,
        "reasons": verd3.reasons,
        "pass": verd3.action in ("LAND", "RETURN_TO_BASE", "REDUCE_SPEED") and verd3.action != "CONTINUE",
    })

    # ---- Test 4: swarm compensation ----
    healths = {
        1: HealthState(1, 0.95, 0.95, 0.95, 0.95, 0.95, "HEALTHY", 0, 96.0),
        2: HealthState(2, 0.9, 0.9, 0.9, 0.9, 0.9, "HEALTHY", 0, 94.0),
        3: HealthState(3, 0.2, 0.15, 0.2, 0.5, 0.15, "CRITICAL", 3, 40.0),
        4: HealthState(4, 0.88, 0.88, 0.88, 0.88, 0.88, "HEALTHY", 0, 93.0),
        5: HealthState(5, 0.92, 0.92, 0.92, 0.92, 0.92, "HEALTHY", 0, 95.0),
    }
    # Decisions: node 3 lands, others continue
    final_actions = {1: "CONTINUE", 2: "CONTINUE", 3: "LAND", 4: "CONTINUE", 5: "CONTINUE"}
    directives = coord.plan(healths, final_actions)
    roles = {d.node_id: d.role for d in directives}
    tests.append({
        "test": "swarm_compensation_on_land",
        "roles": roles,
        "notes": {d.node_id: d.note for d in directives},
        "pass": (
            roles.get(3) == "EGRESS"
            and any(roles.get(i) == "ESCORT" for i in (1, 2, 4, 5))
        ),
    })

    all_pass = all(t["pass"] for t in tests)
    out = {
        "suite": "autonomy_L7_L9",
        "all_pass": all_pass,
        "tests": tests,
        "claim": "AI proposes; safety disposes; swarm compensates on EGRESS.",
    }
    path = results_dir / "autonomy_validation.json"
    path.write_text(json.dumps(out, indent=2))

    print("=== Autonomy validation (L7–L9) ===")
    for t in tests:
        status = "PASS" if t["pass"] else "FAIL"
        print(f"  [{status}] {t['test']}")
        for k, v in t.items():
            if k not in ("test", "pass"):
                print(f"         {k}: {v}")
    print(f"all_pass={all_pass} → {path}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
