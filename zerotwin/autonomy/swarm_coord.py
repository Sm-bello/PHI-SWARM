"""
Multi-UAV coordination around health (L9 simulation).

Given per-node final actions, assign compensatory roles so the swarm
can maintain mission coverage when one node degrades.
"""

from __future__ import annotations

from dataclasses import dataclass

from .health_state import HealthState


@dataclass
class SwarmDirective:
    node_id: int
    role: str  # PRIMARY | SUPPORT | ESCORT | STANDBY | EGRESS
    note: str


class SwarmCoordinator:
    def plan(
        self,
        healths: dict[int, HealthState],
        final_actions: dict[int, str],
    ) -> list[SwarmDirective]:
        directives: list[SwarmDirective] = []
        healthy = [nid for nid, h in healths.items() if h.overall >= 0.65 and final_actions.get(nid) == "CONTINUE"]
        degraded = [nid for nid, a in final_actions.items() if a in ("RETURN_TO_BASE", "LAND", "CHANGE_ROLE", "REDUCE_SPEED")]

        for nid, action in final_actions.items():
            if action == "LAND":
                directives.append(SwarmDirective(nid, "EGRESS", "immediate landing"))
            elif action == "RETURN_TO_BASE":
                directives.append(SwarmDirective(nid, "EGRESS", "RTB"))
            elif action == "CHANGE_ROLE":
                directives.append(SwarmDirective(nid, "STANDBY", "shed primary load"))
            elif action == "REDUCE_SPEED":
                directives.append(SwarmDirective(nid, "SUPPORT", "reduced envelope"))
            else:
                directives.append(SwarmDirective(nid, "PRIMARY", "full mission role"))

        # Assign escort from healthiest CONTINUE node if someone is egressing
        egressing = [d for d in directives if d.role == "EGRESS"]
        if egressing and healthy:
            escort_id = max(healthy, key=lambda i: healths[i].overall)
            for d in directives:
                if d.node_id == escort_id and d.role == "PRIMARY":
                    d.role = "ESCORT"
                    d.note = f"escort/compensate for UAV-{egressing[0].node_id}"
                    break

        return directives
