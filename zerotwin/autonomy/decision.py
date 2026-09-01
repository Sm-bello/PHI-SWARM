"""Health-informed mission decision recommendations (L7). AI proposes only."""

from __future__ import annotations

from dataclasses import dataclass

from .health_state import HealthState
from .risk import RiskAssessment


@dataclass
class MissionDecision:
    node_id: int
    action: str  # CONTINUE | REDUCE_SPEED | CHANGE_ROLE | RETURN_TO_BASE | LAND
    rationale: str
    confidence: float


class DecisionEngine:
    def recommend(self, health: HealthState, risk: RiskAssessment) -> MissionDecision:
        if risk.level == "CRITICAL" or health.overall < 0.25:
            return MissionDecision(
                health.node_id, "LAND",
                f"critical risk ({', '.join(risk.drivers)})",
                0.9,
            )
        if risk.level == "HIGH" or health.overall < 0.45:
            return MissionDecision(
                health.node_id, "RETURN_TO_BASE",
                f"high risk ({', '.join(risk.drivers)})",
                0.8,
            )
        if risk.level == "MEDIUM" or health.overall < 0.65:
            if health.battery < 0.5:
                return MissionDecision(
                    health.node_id, "CHANGE_ROLE",
                    "battery margin low — shed payload role",
                    0.7,
                )
            return MissionDecision(
                health.node_id, "REDUCE_SPEED",
                f"elevated degradation ({', '.join(risk.drivers)})",
                0.65,
            )
        return MissionDecision(
            health.node_id, "CONTINUE",
            "health nominal for current mission",
            0.85,
        )
