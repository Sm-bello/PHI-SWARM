# Architecture — ZeroTwin

## Design principle

Every component must serve at least one of:

1. Make the **physics** more trustworthy  
2. Make the **federation** more private (zero raw telemetry leakage)  
3. Make the **model** more edge-viable  
4. Make the **experiment** more reproducible  

If it does none of these, it is out of scope.

---

## Data flow (integrity path)

```
┌─────────────────────────────────────────────────────────────┐
│  NODE i (simulated edge / future companion computer)        │
│                                                             │
│  Physics engine ──► local multi-sensor windows              │
│       │                                                     │
│       ▼                                                     │
│  CNN-BiLSTM (local train / fine-tune)                       │
│       │                                                     │
│       ▼                                                     │
│  Weight delta ──► Ed25519 sign ──► outbound update only     │
│                                                             │
│  Raw telemetry NEVER leaves this box                        │
└───────────────────────────┬─────────────────────────────────┘
                            │ signed delta only
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  AGGREGATION (Flower server / SuperLink)                    │
│  • Verify signatures (optional strict mode)                 │
│  • FedAvg (or documented robust variant)                    │
│  • Emit global weights                                      │
└───────────────────────────┬─────────────────────────────────┘
                            │ global model
                            ▼
              back to nodes (collective twin)
```

Cross-silo / cross-border interpretation: Node A (e.g. Operator-NG) and Node B (Operator-GH) never exchange time series. Both send signed updates to an aggregation point they can reach intermittently; both receive the improved global model. That is the collaborative intelligence path without data surrender.

---

## Pillar details

### A. Physics Hybrid Integrity

Four deterministic degradation processes (see `zerotwin/physics/`):

| Fault | Physical idea (summary) |
|-------|-------------------------|
| Rotor imbalance | Progressive centrifugal mass offset → vibration at rotational harmonics |
| ESC thermal runaway | Lumped thermal dynamics under sustained current → temperature rise |
| Bearing (BPFO-style) | Outer-race fault frequency content → vibration bursts |
| Battery voltage sag | Internal resistance growth + OCV decay under load |

These engines:

- Generate synthetic multi-sensor streams (vibration, temperature, voltage, acoustic)
- Create **non-IID** partitions across nodes (different fault onset / severity)
- Provide the “hybrid” grounding: learning is not pure black-box labels

### B. Edge-native PHM model

- Input: window of multi-sensor samples  
- Architecture: 1D-CNN feature extractor + bidirectional LSTM + classifier  
- Output: fault class + health confidence  
- Design goal: small enough for companion-computer class hardware; characterized by parameter count and simple latency notes in experiments

### C. Zero-leakage federation

- Framework: Flower (FedAvg baseline)  
- Payload: model weight deltas only  
- Integrity: Ed25519 signature over hash of the delta (verify on server in strict mode)  
- Evaluation must report: accuracy vs centralized gold standard, vs isolated local models, bytes per round, recovery after multi-round disconnection

### D. Open integrity testbed

- Multi-process clients + one aggregation server on a single machine (or multi-machine with a reachable server address)  
- Fixed seeds, logged metrics JSON  
- Optional live dashboard for qualitative inspection  
- Hardware adapter document defines the contract a real node must satisfy

---

## What is intentionally not in the critical path

- DAG/Tangle as primary aggregator (optional research note only)  
- Full product UI as scientific contribution  
- Real-time flight control, MAVLink autopilot integration (documented as future adapter work)  
- Physical radio / mesh / spectrum solutions between airframes  

---

## Integrity guarantees (software testbed)

| Guarantee | Mechanism |
|-----------|-----------|
| No raw telemetry in federation messages | Clients send parameters only |
| Update authenticity (when strict crypto enabled) | Ed25519 sign/verify |
| Reproducibility | Seeded generators + experiment script + saved configs |
| Resilience narrative | Explicit multi-round link-loss experiment in testbed |

These are **software integrity** properties of the architecture and testbed, not claims about operational EW or cryptographic systems under nation-state attack.
