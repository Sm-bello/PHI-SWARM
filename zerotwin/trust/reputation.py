"""
Swarm Trust Fabric (L6).

Maintains per-node reputation from:
  - cryptographic validity rate
  - update consistency (gate accept rate)
  - physics consistency scores
  - historical behavior EMA

Suspicious nodes are not always disconnected; their aggregation weight drops
and they can enter quarantine.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TrustState:
    node_id: int
    score: float = 0.9  # 0..1
    accepts: int = 0
    rejects: int = 0
    physics_penalties: int = 0
    quarantined: bool = False

    @property
    def accept_rate(self) -> float:
        t = self.accepts + self.rejects
        return self.accepts / t if t else 1.0


class TrustFabric:
    def __init__(self, quarantine_below: float = 0.25, ema: float = 0.15):
        self.quarantine_below = quarantine_below
        self.ema = ema
        self._states: dict[int, TrustState] = {}

    def ensure(self, node_id: int) -> TrustState:
        if node_id not in self._states:
            self._states[node_id] = TrustState(node_id=node_id)
        return self._states[node_id]

    def record_decision(
        self,
        node_id: int,
        accepted: bool,
        physics_score: float | None = None,
        bad_signature: bool = False,
    ) -> TrustState:
        st = self.ensure(node_id)
        if accepted:
            st.accepts += 1
            target = 1.0
        else:
            st.rejects += 1
            # Crypto failure → hard zero. Behavioral rejects (norm/physics/replay)
            # must also be able to cross quarantine_below; target 0.3 asymptotes
            # *above* the default 0.25 threshold and made quarantine unreachable.
            target = 0.0 if bad_signature else 0.05

        if physics_score is not None and physics_score < 0.5:
            st.physics_penalties += 1
            target = min(target, physics_score)

        st.score = (1 - self.ema) * st.score + self.ema * target
        st.quarantined = st.score < self.quarantine_below
        return st

    def weight(self, node_id: int) -> float:
        st = self.ensure(node_id)
        if st.quarantined:
            return 0.0
        return float(max(0.0, min(1.0, st.score)))

    def snapshot(self) -> dict[int, dict]:
        out = {}
        for nid, st in self._states.items():
            out[nid] = {
                "score": round(st.score, 4),
                "accepts": st.accepts,
                "rejects": st.rejects,
                "physics_penalties": st.physics_penalties,
                "quarantined": st.quarantined,
                "accept_rate": round(st.accept_rate, 4),
            }
        return out
