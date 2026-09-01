#!/usr/bin/env python3
"""
Deterministic validation of L5-L9: the four scenarios proposed for turning
"implemented" into "experimentally proven" (malicious signed update, replay,
degraded-UAV autonomous decision, swarm compensation).

These are built as direct, deterministic tests against the actual gate/
trust/autonomy classes rather than hoping a short randomized live run
happens to trigger each scenario naturally (which is why the original
phi_swarm_summary.json showed 0 replays blocked — it wasn't that replay
protection doesn't work, it's that a 2-minute run at low attack probability
just didn't roll one).
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
from zerotwin.autonomy.health_state import HealthState
from zerotwin.autonomy.risk import RiskEngine
from zerotwin.autonomy.decision import DecisionEngine
from zerotwin.autonomy.safety import SafetyGovernor
from zerotwin.autonomy.swarm_coord import SwarmCoordinator

PASS, FAIL = [], []


def check(name: str, condition: bool, detail: str = ""):
    (PASS if condition else FAIL).append(name)
    print(f"[{'PASS' if condition else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def fake_delta(shapes, scale=1.0, rng=None):
    rng = rng or np.random.default_rng(0)
    return [rng.normal(0, 0.01, size=s).astype(np.float32) * scale for s in shapes]


SHAPES = [(32, 4, 3), (32,), (32, 32), (32,), (5, 32), (5,)]  # arbitrary small param-shaped arrays


def test1_malicious_signed_update():
    print("\n=== TEST 1: valid signature + physics-inconsistent + oversized update ===")
    gate = IntegrityGate()
    trust = TrustFabric()
    key = NodeKeypair.generate(4)
    rng = np.random.default_rng(1)

    # First establish an honest norm history so the anomaly check has a baseline
    for _ in range(6):
        d = fake_delta(SHAPES, scale=1.0, rng=rng)
        sig = sign_parameters(key, d)
        env = UpdateEnvelope(node_id=4, round_id=gate._last_round_seen.get(4, 0) + 1, delta=d,
                              signature=sig, public_key=key.public_key, local_health=0.9, claimed_fault=0)
        decision = gate.check(env, node_trust=trust.weight(4))
        trust.record_decision(4, decision.accepted, decision.physics_score, "bad_signature" in decision.reasons)

    baseline_trust = trust.ensure(4).score
    check("honest baseline established", decision.accepted, f"trust after 6 honest rounds = {baseline_trust:.3f}")

    # Now: VALID signature (attacker owns real key), but content is malicious —
    # claims healthy (fault=0) while its own reported health is critically low,
    # AND the delta magnitude is a 30x outlier.
    d_attack = fake_delta(SHAPES, scale=30.0, rng=rng)
    sig_attack = sign_parameters(key, d_attack)  # genuinely valid signature over the attack payload
    env_attack = UpdateEnvelope(node_id=4, round_id=gate._last_round_seen.get(4, 0) + 1, delta=d_attack,
                                 signature=sig_attack, public_key=key.public_key,
                                 local_health=0.30, claimed_fault=0)  # lying: claims healthy at 30% health
    decision = gate.check(env_attack, node_trust=trust.weight(4))
    trust.record_decision(4, decision.accepted, decision.physics_score, "bad_signature" in decision.reasons)

    check("signature itself verifies (attacker has a real key)", "bad_signature" not in decision.reasons)
    check("malicious update rejected despite valid signature", not decision.accepted, str(decision.reasons))
    check("trust score drops after malicious update", trust.ensure(4).score < baseline_trust,
          f"{baseline_trust:.3f} -> {trust.ensure(4).score:.3f}")

    # Repeat enough rounds to confirm quarantine is actually reachable, not
    # just a lower asymptote. EMA alpha=0.15 has a ~6-round time constant,
    # so convergence from a high starting trust takes ~22+ rounds to cross
    # the 0.25 quarantine line — real detection-latency tradeoff (attacker
    # keeps shrinking influence for many rounds before full quarantine).
    # EMA alpha=0.15 → ~6-round time constant. From ~0.96 starting trust,
    # need ~22+ sustained reject rounds to cross quarantine_below=0.25.
    for _ in range(28):
        d_attack = fake_delta(SHAPES, scale=30.0, rng=rng)
        sig_attack = sign_parameters(key, d_attack)
        env_attack = UpdateEnvelope(node_id=4, round_id=gate._last_round_seen.get(4, 0) + 1, delta=d_attack,
                                     signature=sig_attack, public_key=key.public_key,
                                     local_health=0.30, claimed_fault=0)
        decision = gate.check(env_attack, node_trust=trust.weight(4))
        trust.record_decision(4, decision.accepted, decision.physics_score, "bad_signature" in decision.reasons)
    check("sustained malicious behavior -> quarantined", trust.ensure(4).quarantined,
          f"final trust = {trust.ensure(4).score:.3f} (after 28 sustained attack rounds; quarantine_below=0.25)")


def test2_replay_attack():
    print("\n=== TEST 2: genuine replay — resend an actual previously-accepted signed package ===")
    gate = IntegrityGate()
    key = NodeKeypair.generate(7)
    rng = np.random.default_rng(2)

    d = fake_delta(SHAPES, scale=1.0, rng=rng)
    sig = sign_parameters(key, d)
    env_round4 = UpdateEnvelope(node_id=7, round_id=4, delta=d, signature=sig, public_key=key.public_key)
    first = gate.check(env_round4)
    check("original round-4 update accepted", first.accepted, str(first.reasons))

    # advance a couple of honest rounds so there's a "later" state
    for rid in (5, 6):
        d2 = fake_delta(SHAPES, scale=1.0, rng=rng)
        sig2 = sign_parameters(key, d2)
        gate.check(UpdateEnvelope(node_id=7, round_id=rid, delta=d2, signature=sig2, public_key=key.public_key))

    # now literally resend the EXACT round-4 envelope (same bytes, same signature)
    replay = gate.check(env_round4)
    check("identical round-4 package rejected on replay", not replay.accepted, str(replay.reasons))
    check("rejection reason is specifically replay/stale, not a signature failure",
          "replay_or_stale_round" in replay.reasons)


def test3_degraded_uav_decision():
    print("\n=== TEST 3: degraded UAV (battery=0.35, bearing=0.30) -> autonomous decision ===")
    health = HealthState(node_id=3, motor=0.8, battery=0.35, bearing=0.30, thermal=0.8,
                          overall=min(0.8, 0.35, 0.30, 0.8), status="WARNING", fault_label=3, confidence=55.0)
    risk = RiskEngine().assess(health)
    rec = DecisionEngine().recommend(health, risk)
    verdict = SafetyGovernor().review(rec, health)

    check("risk level elevated (HIGH or CRITICAL)", risk.level in ("HIGH", "CRITICAL"), risk.level)
    check("AI recommends stepping back from full mission (not CONTINUE)", rec.action != "CONTINUE", rec.action)
    check("safety governor did not upgrade to something riskier than the AI asked",
          verdict.action in (rec.action, "LAND"), f"ai={rec.action} final={verdict.action}")
    print(f"    risk={risk.level} ({risk.score:.2f}, drivers={risk.drivers})  "
          f"ai_action={rec.action}  final_action={verdict.action}  reasons={verdict.reasons}")


def test4_swarm_compensation():
    print("\n=== TEST 4: degraded UAV egresses -> healthiest UAV escorts/compensates ===")
    healths = {
        1: HealthState(1, 0.9, 0.9, 0.9, 0.9, 0.9, "HEALTHY", 0, 95.0),
        2: HealthState(2, 0.85, 0.88, 0.9, 0.85, 0.85, "HEALTHY", 0, 90.0),
        3: HealthState(3, 0.8, 0.35, 0.30, 0.8, 0.30, "WARNING", 3, 55.0),  # degraded
        4: HealthState(4, 0.97, 0.98, 0.97, 0.96, 0.96, "HEALTHY", 0, 98.0),  # unambiguously healthiest
        5: HealthState(5, 0.87, 0.86, 0.85, 0.87, 0.85, "HEALTHY", 0, 91.0),
    }
    risk_engine, decision_engine, safety = RiskEngine(), DecisionEngine(), SafetyGovernor()
    final_actions = {}
    for nid, h in healths.items():
        r = risk_engine.assess(h)
        rec = decision_engine.recommend(h, r)
        v = safety.review(rec, h)
        final_actions[nid] = v.action

    directives = SwarmCoordinator().plan(healths, final_actions)
    by_node = {d.node_id: d for d in directives}

    check("degraded UAV-3 assigned EGRESS", by_node[3].role == "EGRESS", by_node[3].role)
    check("healthiest node (UAV-4) reassigned to ESCORT", by_node[4].role == "ESCORT",
          f"UAV-4 role={by_node[4].role}, note={by_node[4].note}")
    check("remaining healthy nodes still cover PRIMARY role",
          any(d.role == "PRIMARY" for nid, d in by_node.items() if nid not in (3, 4)))
    for d in directives:
        print(f"    UAV-{d.node_id}: {d.role:<8} ({d.note})")


if __name__ == "__main__":
    test1_malicious_signed_update()
    test2_replay_attack()
    test3_degraded_uav_decision()
    test4_swarm_compensation()

    print(f"\n=== RESULT: {len(PASS)} passed / {len(FAIL)} failed ===")
    if FAIL:
        print("FAILED:", FAIL)
        sys.exit(1)
