"""
Safety Governor (L8): AI proposes; safety architecture disposes.

Never lets a recommendation execute if it violates hard constraints.
"""

from __future__ import annotations

from dataclasses import dataclass

from .decision import MissionDecision
from .health_state import HealthState


@dataclass
class SafetyVerdict:
    allowed: bool
    action: str  # final action after governor
    reasons: list[str]


class SafetyGovernor:
    def __init__(
        self,
        min_battery_for_continue: float = 0.2,
        min_overall_for_continue: float = 0.2,
        min_confidence: float = 40.0,
    ):
        self.min_battery_for_continue = min_battery_for_continue
        self.min_overall_for_continue = min_overall_for_continue
        self.min_confidence = min_confidence

    def review(self, decision: MissionDecision, health: HealthState) -> SafetyVerdict:
        reasons: list[str] = []
        action = decision.action

        # Hard: never CONTINUE if battery critically low
        if action in ("CONTINUE", "REDUCE_SPEED", "CHANGE_ROLE"):
            if health.battery < self.min_battery_for_continue:
                reasons.append("battery_floor")
                action = "LAND"
            if health.overall < self.min_overall_for_continue:
                reasons.append("overall_health_floor")
                action = "LAND"
            if health.confidence < self.min_confidence and action == "CONTINUE":
                reasons.append("low_phm_confidence")
                action = "REDUCE_SPEED"

        # Hard: LINK-LOST cannot claim CONTINUE with high autonomy
        if health.status == "LINK-LOST" and action == "CONTINUE":
            reasons.append("link_lost_no_full_continue")
            action = "REDUCE_SPEED"

        # LAND and RTB always allowed if AI asked (conservative)
        if decision.action in ("LAND", "RETURN_TO_BASE"):
            if action != decision.action and action in ("CONTINUE", "REDUCE_SPEED"):
                # don't upgrade riskier than AI asked
                action = decision.action

        allowed = True
        if not reasons:
            reasons.append("constraints_ok")
        return SafetyVerdict(allowed=allowed, action=action, reasons=reasons)
