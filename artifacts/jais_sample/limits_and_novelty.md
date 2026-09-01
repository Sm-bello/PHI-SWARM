# Limits and novelty (draft for JAIS)

## Novelty statement (tight)

We present a **software-only** multi-UAV prognostic health management (PHM) federation in which
**Ed25519-signed weight deltas** pass an **integrity gate** (signature, replay, norm/physics checks)
before aggregation, combined with **EMA trust -> quarantine** and **L7-L9 autonomy role reallocation**
(EGRESS / ESCORT / PRIMARY) under the same threat model. Prior FL-security work often stops at
authentication or robust aggregation; prior UAV-PHM federation rarely couples **signed integrity**,
**behavioral quarantine**, and **swarm role directives** in one reproducible stack with multi-seed
and link-loss evidence.

## Honest limits

1. **Simulation only** - no HIL, flight test, or real aircraft sensors.
2. **Synthetic faults** - physics twin labels (rotor imbalance, bearing BPFO, voltage sag, etc.), not field-labeled failures.
3. **Small models / 5 nodes** - PHM window classifier (~1.7e5 params); not large-scale vision/LLM FL.
4. **Network model** - link-loss rounds and message drop abstractions; not a full RF channel or ADS-B model.
5. **Edge timing** - measured on **dev/laptop CPU**, not Jetson/Pi-class hardware (future work).
6. **Audit trail** - local hash-chained JSONL (tamper-evident log), not a distributed ledger or certified PKI.
7. **Federation gain** - mean positive over isolated with non-trivial seed variance; report mean+/-std and win fraction.

## Threat model scope

In-scope: forged updates, anomalous signed updates, replay, sustained malicious behavior, eavesdrop on
software message channel, temporary link loss, endogenous platform degradation.

Out of scope: physical RF jamming with hardware, supply-chain key extraction, pilot-in-the-loop certification claims.

## Suggested table use

| Artifact | Paper use |
|----------|-----------|
| baseline_summary.csv / fig_baseline.png | Results: centralized vs isolated vs federated |
| fig_federation_gain.png | Variance honesty |
| resilience_curve.csv | Link-loss recovery |
| threat_model.csv | Threat model section |
| threat_evidence.csv | Mapping threats -> measured counters |
| ablation_results.csv / fig_ablation.png | Gate on/off x attack rate |
| edge_timing.csv | Software performance (clearly labeled dev CPU) |
