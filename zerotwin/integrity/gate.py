"""
Integrity Gate — multi-stage filter for federated updates (L3 + L5).

Pipeline for each update ΔW:
  1. Cryptographic verification (Ed25519)
  2. Replay protection (round_id monotonic per node)
  3. Norm anomaly check (vs recent honest history)
  4. Physics-consistency score (optional local health vs claimed direction)
  5. Trust-weighted accept / down-weight / reject

Authentication ≠ behavioral trust: a valid signature can still be rejected
for anomalous magnitude or physics inconsistency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from zerotwin.crypto.signing import NodeKeypair, verify_parameters


@dataclass
class UpdateEnvelope:
    node_id: int
    round_id: int
    delta: list[np.ndarray]
    signature: bytes
    public_key: Any  # Ed25519PublicKey
    # Optional physics context from the sender's local state
    local_health: float | None = None  # 0..1 overall health
    claimed_fault: int | None = None


@dataclass
class GateDecision:
    accepted: bool
    weight: float  # aggregation weight multiplier in [0, 1]
    reasons: list[str] = field(default_factory=list)
    physics_score: float | None = None
    norm: float | None = None


def _delta_norm(delta: list[np.ndarray]) -> float:
    total = 0.0
    for a in delta:
        total += float(np.sum(a.astype(np.float64) ** 2))
    return float(np.sqrt(total))


class IntegrityGate:
    def __init__(
        self,
        norm_z_threshold: float = 3.5,
        min_history: int = 5,
        physics_reject_below: float = 0.25,
    ):
        self.norm_z_threshold = norm_z_threshold
        self.min_history = min_history
        self.physics_reject_below = physics_reject_below
        self._norm_history: list[float] = []
        self._last_round_seen: dict[int, int] = {}

    def check(self, env: UpdateEnvelope, node_trust: float = 1.0) -> GateDecision:
        reasons: list[str] = []

        # 1) Signature
        if not verify_parameters(env.public_key, env.delta, env.signature):
            return GateDecision(False, 0.0, ["bad_signature"])

        # 2) Replay / monotonic round
        last = self._last_round_seen.get(env.node_id, -1)
        if env.round_id <= last:
            return GateDecision(False, 0.0, ["replay_or_stale_round"])
        self._last_round_seen[env.node_id] = env.round_id

        # 3) Norm anomaly
        norm = _delta_norm(env.delta)
        if len(self._norm_history) >= self.min_history:
            mu = float(np.mean(self._norm_history))
            sigma = float(np.std(self._norm_history)) + 1e-9
            z = abs(norm - mu) / sigma
            if z > self.norm_z_threshold:
                return GateDecision(False, 0.0, [f"norm_anomaly_z={z:.2f}"], norm=norm)
        # only record norms that passed crypto (candidates for honest baseline)
        self._norm_history.append(norm)
        if len(self._norm_history) > 200:
            self._norm_history.pop(0)

        # 4) Physics consistency (soft): very low local health should not
        # produce near-zero updates if the node claims "all healthy" — simple heuristic
        physics_score = 1.0
        if env.local_health is not None and env.claimed_fault is not None:
            # If health is poor but claimed fault is normal (0), penalize
            if env.local_health < 0.45 and env.claimed_fault == 0:
                physics_score = 0.2
                reasons.append("physics_inconsistent_healthy_claim")
            elif env.local_health > 0.9 and env.claimed_fault != 0:
                physics_score = 0.5
                reasons.append("physics_inconsistent_fault_claim")

        if physics_score < self.physics_reject_below:
            return GateDecision(False, 0.0, reasons + ["physics_reject"], physics_score=physics_score, norm=norm)

        # 5) Trust-modulated weight
        weight = float(np.clip(node_trust * physics_score, 0.0, 1.0))
        if weight < 0.15:
            return GateDecision(False, 0.0, reasons + ["trust_too_low"], physics_score=physics_score, norm=norm)

        if not reasons:
            reasons.append("ok")
        return GateDecision(True, weight, reasons, physics_score=physics_score, norm=norm)
