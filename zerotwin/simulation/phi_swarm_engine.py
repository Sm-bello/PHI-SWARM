"""
PHI-SWARM integrated simulation engine (L0–L9, software only).

Wraps ZeroTwin live PHM + federation with:
  IntegrityGate, TrustFabric, Risk/Decision/Safety, SwarmCoordinator.

Continuous ticks update telemetry, FL rounds, trust, and swarm directives.
All security and decision events go to the AuditLedger.
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from zerotwin.simulation.live_engine import LiveSimulationEngine
from zerotwin.integrity.gate import IntegrityGate, UpdateEnvelope
from zerotwin.trust.reputation import TrustFabric
from zerotwin.autonomy.health_state import health_from_status
from zerotwin.autonomy.risk import RiskEngine
from zerotwin.autonomy.decision import DecisionEngine
from zerotwin.autonomy.safety import SafetyGovernor
from zerotwin.autonomy.swarm_coord import SwarmCoordinator
from zerotwin.federated.train_utils import (
    train_local,
    evaluate,
    get_parameters,
    set_parameters,
    average_parameters,
)
from zerotwin.models import UAVPHMModel
from zerotwin.crypto import sign_parameters


class PHISwarmEngine(LiveSimulationEngine):
    """Extends live engine with trust + autonomy stack."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.gate = IntegrityGate()
        self.trust = TrustFabric()
        self.risk_engine = RiskEngine()
        self.decision_engine = DecisionEngine()
        self.safety = SafetyGovernor()
        self.coordinator = SwarmCoordinator()
        self.last_directives: list[dict] = []
        self.last_decisions: list[dict] = []
        for nid in self.nodes:
            self.trust.ensure(nid)

    def _run_federated_round(self):
        """Override: delta updates through IntegrityGate + TrustFabric."""
        self.fed_round += 1
        g_params = get_parameters(self.global_model)
        accepted_params = []
        accepted_weights = []
        gate_log = []

        for nid, node in self.nodes.items():
            if node.link_lost_until_round and self.fed_round < node.link_lost_until_round:
                continue

            m = UAVPHMModel()
            set_parameters(m, g_params)
            train_local(m, self.local_data[nid]["Xtr"], self.local_data[nid]["ytr"], epochs=1)
            local_params = get_parameters(m)
            delta = [lp - gp for lp, gp in zip(local_params, g_params)]

            # intentional attacks (same spirit as parent)
            import random
            attack = None
            if random.random() < self.attack_probability:
                attack = random.choice(["tamper", "scale", "replay"])
                if attack == "tamper":
                    sig = sign_parameters(self.sign_keys[nid], delta)
                    delta = [d + np.random.randn(*d.shape).astype(d.dtype) * 0.5 for d in delta]
                elif attack == "scale":
                    delta = [d * 25.0 for d in delta]
                    sig = sign_parameters(self.sign_keys[nid], delta)
                else:  # replay: use old round id
                    sig = sign_parameters(self.sign_keys[nid], delta)
            else:
                sig = sign_parameters(self.sign_keys[nid], delta)

            health = health_from_status(
                nid, node.status, node.fault_label, node.confidence, node.severity
            )
            round_id = self.fed_round if attack != "replay" else max(0, self.fed_round - 3)

            env = UpdateEnvelope(
                node_id=nid,
                round_id=round_id,
                delta=delta,
                signature=sig,
                public_key=self.sign_keys[nid].public_key,
                local_health=health.overall,
                claimed_fault=node.fault_label,
            )
            node_trust = self.trust.weight(nid)
            decision = self.gate.check(env, node_trust=node_trust)

            bad_sig = "bad_signature" in decision.reasons
            self.trust.record_decision(
                nid,
                accepted=decision.accepted,
                physics_score=decision.physics_score,
                bad_signature=bad_sig,
            )

            if decision.accepted:
                # reconstruct absolute params = global + delta
                abs_params = [gp + d for gp, d in zip(g_params, delta)]
                accepted_params.append(abs_params)
                w = len(self.local_data[nid]["Xtr"]) * decision.weight
                accepted_weights.append(w)
                self.accepted_total += 1
                self.bytes_transferred += sum(d.nbytes for d in delta)
            else:
                self.rejected_total += 1

            gate_log.append({
                "node_id": nid,
                "accepted": decision.accepted,
                "weight": decision.weight,
                "reasons": decision.reasons,
                "attack": attack,
                "trust": round(self.trust.ensure(nid).score, 4),
            })
            self.ledger.append("integrity_gate", gate_log[-1] | {"fed_round": self.fed_round})

        if accepted_params:
            avg = average_parameters(accepted_params, accepted_weights)
            set_parameters(self.global_model, avg)

        self.global_acc = evaluate(self.global_model, self.Xte_c, self.yte_c)
        self.ledger.append("fed_round", {
            "round": self.fed_round,
            "global_acc": round(self.global_acc, 4),
            "accepted": len(accepted_params),
            "rejected": len(gate_log) - len(accepted_params),
        })

        # encrypted messages between random pairs (parent behavior)
        self._maybe_exchange_messages()

        # autonomy stack each FL round
        self._run_autonomy_cycle()

    def _maybe_exchange_messages(self):
        """Use parent encrypted exchange when available; else skip silently."""
        if hasattr(LiveSimulationEngine, "_run_encrypted_exchange"):
            try:
                LiveSimulationEngine._run_encrypted_exchange(self, self.fed_round)
            except Exception:
                pass

    def _run_autonomy_cycle(self):
        healths = {}
        final_actions = {}
        decisions_out = []
        for nid, node in self.nodes.items():
            h = health_from_status(nid, node.status, node.fault_label, node.confidence, node.severity)
            healths[nid] = h
            risk = self.risk_engine.assess(h)
            rec = self.decision_engine.recommend(h, risk)
            verdict = self.safety.review(rec, h)
            final_actions[nid] = verdict.action
            decisions_out.append({
                "node_id": nid,
                "health": h.as_dict(),
                "risk": risk.level,
                "risk_score": round(risk.score, 3),
                "ai_action": rec.action,
                "final_action": verdict.action,
                "safety_reasons": verdict.reasons,
            })
            self.ledger.append("autonomy_decision", decisions_out[-1] | {"fed_round": self.fed_round})

        directives = self.coordinator.plan(healths, final_actions)
        self.last_directives = [
            {"node_id": d.node_id, "role": d.role, "note": d.note} for d in directives
        ]
        self.last_decisions = decisions_out
        self.ledger.append("swarm_directives", {
            "fed_round": self.fed_round,
            "directives": self.last_directives,
        })

    def get_state(self) -> dict:
        state = super().get_state()
        state["trust"] = self.trust.snapshot()
        state["decisions"] = self.last_decisions
        state["directives"] = self.last_directives
        state["framework"] = "PHI-SWARM"
        state["levels_active"] = ["L0", "L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8", "L9"]
        return state
