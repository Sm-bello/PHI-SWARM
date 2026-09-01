# Threat model (simulation)

Threats considered in the software experiments (T1–T7 style):

| ID | Threat | Mitigations exercised in code |
|----|--------|-------------------------------|
| T1 | Poisoned / manipulated local model updates | Integrity gate (L5), signature checks |
| T2 | Impersonation of nodes | Ed25519 signed deltas |
| T3 | Replay of stale updates | Nonce / sequence handling in messaging |
| T4 | Intermittent / lossy links | Link-loss sweeps (L4) |
| T5 | Byzantine or low-trust peers | Trust fabric / reputation (L6) |
| T6 | Decision under degraded health evidence | Decision + safety layers (L7) |
| T7 | Coordination under partial visibility | Swarm coordination (L8–L9) |

## Out of scope

- Physical capture of airframes
- Side-channel attacks on real hardware crypto
- Full spectrum denial against RF links (only simulated drop rates)
- Supply-chain compromise of the training pipeline outside the documented injection points

See also `docs/limits.md` and `artifacts/jais_sample/limits_and_novelty.md`.
