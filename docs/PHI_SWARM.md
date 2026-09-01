# PHI-SWARM

**Physics-Hybrid Integrity Framework for Secure Autonomous UAV Swarms**

ZeroTwin is the **federated health-intelligence foundation** (collective PHM twin).  
PHI-SWARM is the **research framework** that stacks trust, decision, safety, and coordination on top of ZeroTwin — still in software simulation through L9. **HIL and real flight remain future work (L10–L11).**

---

## Maturity ladder

| Level | Capability | Status in this repo |
|-------|------------|---------------------|
| L0 | Physics simulation | Implemented |
| L1 | Local UAV PHM | Implemented |
| L2 | Federated collective learning | Implemented |
| L3 | Cryptographic update integrity | Implemented |
| L4 | Connectivity resilience (simulated) | Implemented |
| L5 | Physics-aware malicious-update detection | Implemented (`integrity/gate.py`) |
| L6 | Swarm trust / reputation | Implemented (`trust/reputation.py`) |
| L7 | Health-informed mission decisions | Implemented (`autonomy/decision.py`) |
| L8 | Safety-governed autonomous behavior | Implemented (`autonomy/safety.py`) |
| L9 | Multi-UAV autonomous coordination | Implemented (`autonomy/swarm_coord.py`) |
| L10 | HIL / representative hardware | **Not in this repo** |
| L11 | Real flight validation | **Not in this repo** |

---

## Honest claim

> We propose and progressively validate a physics-informed security and autonomy framework for collaborative UAV swarm intelligence, with ZeroTwin providing the demonstrated federated health-intelligence foundation in a reproducible software testbed. We do not claim to have solved secure autonomous UAV swarm intelligence in operational environments.

---

## Stack (software)

```
Sensors (simulated physics)
    → Local PHM (CNN-BiLSTM)
    → ΔW + Ed25519
    → Integrity Gate (crypto, replay, norm, physics score)
    → Trust Fabric (reputation / quarantine)
    → FedAvg (trust-weighted)
    → Global twin
    → Health state → Risk → Decision (AI proposes)
    → Safety Governor (constraints dispose)
    → Swarm Coordinator (roles)
    → Audit ledger (hash-chained)
```

Encrypted node-to-node packages (X25519 + ChaCha20-Poly1305 + Ed25519) protect confidentiality of inter-drone messages in simulation; this is not an RF/EW claim.

---

## How to run

```bash
# Full continuous PHI-SWARM sim (default 10 minutes)
python scripts/run_phi_swarm.py --minutes 10

# Validation suite (integrity + sweeps + short live)
python scripts/run_full_validation.py

# Dashboard (ZeroTwin observability)
python -m zerotwin.observability.dashboard
```

See `RUN_SEQUENCE.md` for the full gate list.
