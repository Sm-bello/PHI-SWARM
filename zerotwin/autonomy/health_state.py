"""Machine-readable health state from PHM outputs (feeds decision layer)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class HealthState:
    node_id: int
    motor: float  # 0..1
    battery: float
    bearing: float
    thermal: float
    overall: float
    status: str  # HEALTHY | WARNING | CRITICAL | LINK-LOST
    fault_label: int
    confidence: float  # 0..100

    def as_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "motor": round(self.motor, 3),
            "battery": round(self.battery, 3),
            "bearing": round(self.bearing, 3),
            "thermal": round(self.thermal, 3),
            "overall": round(self.overall, 3),
            "status": self.status,
            "fault_label": self.fault_label,
            "confidence": round(self.confidence, 1),
        }


def health_from_status(
    node_id: int,
    status: str,
    fault_label: int,
    confidence: float,
    severity: float,
) -> HealthState:
    """Map live-engine status into component health scores (0=failed, 1=perfect)."""
    base = max(0.05, min(0.99, confidence / 100.0))
    motor = base
    battery = base
    bearing = base
    thermal = base
    if fault_label == 1:  # rotor
        motor = max(0.1, 1.0 - 0.55 * severity)
    elif fault_label == 2:  # thermal
        thermal = max(0.1, 1.0 - 0.6 * severity)
    elif fault_label == 3:  # bearing
        bearing = max(0.1, 1.0 - 0.55 * severity)
    elif fault_label == 4:  # voltage
        battery = max(0.1, 1.0 - 0.65 * severity)
    if status == "LINK-LOST":
        overall = base * 0.85
    else:
        overall = min(motor, battery, bearing, thermal)
    return HealthState(
        node_id=node_id,
        motor=motor,
        battery=battery,
        bearing=bearing,
        thermal=thermal,
        overall=overall,
        status=status,
        fault_label=fault_label,
        confidence=confidence,
    )
