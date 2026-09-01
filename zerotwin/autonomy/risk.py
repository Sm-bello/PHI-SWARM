"""Risk assessment from health state + mission context (L7 input)."""

from __future__ import annotations

from dataclasses import dataclass

from .health_state import HealthState


@dataclass
class RiskAssessment:
    node_id: int
    level: str  # LOW | MEDIUM | HIGH | CRITICAL
    score: float  # 0..1 higher = riskier
    drivers: list[str]


class RiskEngine:
    def assess(self, health: HealthState, mission_priority: float = 0.5) -> RiskAssessment:
        drivers = []
        score = 1.0 - health.overall
        if health.battery < 0.4:
            drivers.append("battery_low")
            score = max(score, 0.7)
        if health.bearing < 0.4:
            drivers.append("bearing_degraded")
            score = max(score, 0.75)
        if health.thermal < 0.4:
            drivers.append("thermal_stress")
            score = max(score, 0.7)
        if health.motor < 0.4:
            drivers.append("motor_degraded")
            score = max(score, 0.8)
        if health.status == "CRITICAL":
            drivers.append("status_critical")
            score = max(score, 0.85)
        if health.status == "LINK-LOST":
            drivers.append("link_lost")
            score = max(score, 0.5)
        # mission priority slightly raises tolerance (higher priority → accept more risk)
        score = float(max(0.0, min(1.0, score * (1.1 - 0.2 * mission_priority))))
        if score < 0.25:
            level = "LOW"
        elif score < 0.5:
            level = "MEDIUM"
        elif score < 0.75:
            level = "HIGH"
        else:
            level = "CRITICAL"
        if not drivers:
            drivers.append("nominal")
        return RiskAssessment(health.node_id, level, score, drivers)
