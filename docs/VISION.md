# ZeroTwin — Project Core & Vision

This document is aligned with the **code and testbed in this repository**.  
Present-tense claims describe only what runs today. Horizon items are labeled as future work.

For paper wording, see `PAPER_FRAMING.md`. For stack detail, see `ARCHITECTURE.md`.

---

## What the Project Is Today (The Foundation)

ZeroTwin is an **open, physics-informed federated digital twin testbed** for quadrotor swarm prognostics and health management (PHM).

It is engineered so that geographically or organizationally separated edge nodes can collaboratively refine a **shared health model without sharing raw telemetry** — only signed model updates leave each node. That addresses a practical barrier for multi-party and cross-jurisdictional fleets: policy, data sovereignty, tactical sensitivity, and bandwidth often forbid pooling continuous sensor histories, so isolated models stay weak.

ZeroTwin is **not** a flight-control stack, not a solved tactical radio system, and not a theater-validated EW product. It is a research architecture plus a reproducible simulation testbed (TRL ~3–early 4 software breadboard).

### Why the centralized twin fails in the settings we care about

Traditional digital twins often stream high-rate sensor data to a central server. In multi-operator, cross-border, or bandwidth-limited settings that approach breaks down:

- **Data sovereignty & privacy** — Operators may refuse to exfiltrate raw acoustic, vibration, trajectory, or operational telemetry to a third party or foreign server.
- **Single point of failure** — If the aggregation host is unreachable, a purely centralized diagnostic service stalls; the federated design allows local inference to continue and updates to resume when connectivity returns.
- **Bandwidth** — Continuous multi-channel raw feeds scale poorly across many aircraft; model updates are far smaller.

ZeroTwin’s response is not “we guarantee contested-spectrum links.” It is: **keep data local, train on physics-grounded windows, exchange only integrity-protected parameters, measure recovery under simulated intermittent connectivity.**

### The ZeroTwin stack (today)

```
[Physics engines] → [Local sensor windows]
        ↓
[CNN-BiLSTM on node] → health logits + confidence
        ↓
[Ed25519-signed weight deltas only]  ← raw telemetry never leaves the node
        ↓
[FedAvg aggregation (Flower or in-process testbed)]
        ↓
[Global model = collective twin] + [Command Center observability]
```

DAG/Tangle-style asynchronous buffers are **not** on the critical path in this release. They remain optional future work under Horizon.

### The four working technical pillars

**1. Physics Hybrid Integrity**  
Each node’s training data is produced by deterministic degradation engines (not arbitrary labels):

- Harmonic rotor imbalance  
- ESC thermal runaway  
- Outer-race-style bearing content (BPFO-inspired)  
- LiPo / bus voltage sag  

These engines create Non-IID partitions across nodes and ground the “hybrid integrity” claim: local distributions remain physically meaningful so federation is not pure noise averaging.

**2. Edge-native PHM model**  
A lightweight 1D-CNN + bidirectional LSTM consumes multi-sensor windows (vibration, temperature, voltage, acoustic) and outputs fault-class logits. The design target is companion-computer class compute, characterized in experiments by parameter count and accuracy — not by claims of onboard flight certification.

**3. Zero-leakage federation**  
Nodes exchange **model parameters (weight deltas) only**, typically via Flower FedAvg or the in-process integrity experiment.  

- **Crypto role (today):** Ed25519 signatures over a canonical hash of the parameter payload support **update authenticity / integrity** (the receiver can check that a delta was signed by a known node key).  
- **What we do not claim:** that signing “eliminates model poisoning” or defeats all adversarial clients. Poisoning defense is a broader research area; signatures are one integrity layer, not a complete security proof.

**4. Open integrity testbed**  
`scripts/run_integrity_experiment.py` runs a reproducible comparison:

- Centralized (pooled data)  
- Isolated (local-only models)  
- Federated ZeroTwin (parameters only)  
- Optional **simulated link-loss** (skip aggregation for K rounds, then resume)

Metrics are written to `zerotwin/results/integrity_metrics.json`. **Do not cite a fixed accuracy such as 97.04%** unless that number is produced by a named config (seed, samples, rounds) in that file and can be re-run. Always report the measured values from your run.

**Command observability**  
A Flask Command Center (`python -m zerotwin.observability.dashboard`) provides a live visual of the swarm-twin narrative (topology, per-node cards, fault summary). It is a communication and inspection tool, not the scientific claim itself.

### Cross-border / international framing (today)

**Say this:**  
Nodes operated in different countries or by different organizations (e.g. Operator-NG and Operator-GH) can improve a **shared health model** without exchanging raw sensor streams. The only cross-silo traffic required is intermittent delivery of **signed model updates** to an aggregation point both can reach.

**Do not say this:**  
That ZeroTwin solves physical radio, MANET, spectrum, or regulatory airspace between airframes in Nigeria and Ghana (or any corridor). Packet transport is assumed to exist intermittently at IP level (localhost, LAN, or a cheap VPS). The gap we address is **collaborative PHM intelligence without data surrender**, not cross-border C2 radio.

### Electronic warfare / denied links (today)

**Today:** the testbed can **simulate intermittent connectivity** (delayed or skipped aggregation rounds) and measure recovery of the global model afterward.  

**Not today:** proof against real jamming, contested waveform design, or operational EW qualification.

---

## What ZeroTwin Will Be in the Long Run (Horizon)

*Everything below is future work. It is not delivered by this repository and must not be described in the present tense in papers about the current artifact.*

### H1. Hardware-in-the-Loop & real flight telemetry

- Port the PHM runtime to companion boards (e.g. Jetson Orin Nano, Raspberry Pi 5 class).  
- MAVLink (or equivalent) ingress so PX4 / ArduPilot / commercial stacks can feed live IMU, ESC, and battery metrics into the **local** twin during flight.  
- Satisfy the contract in `HARDWARE_ADAPTER.md` with a real node implementation.

### H2. Richer networking & autonomous consensus

- Move beyond loopback/gRPC-on-VPS to field radios or MANET where appropriate.  
- Optional asynchronous / DAG-style buffers for store-and-forward of updates when the aggregation host is unreachable for long periods.  
- On-device gossip of signed updates among airborne nodes — research prototype, not claimed in this release.

### H3. Cross-silo deployment patterns

- Operate the aggregation host as shared infrastructure for regional logistics or multi-operator fleets **under explicit data-sovereignty rules** (parameters only).  
- Integration paths with broader single-airframe twins (e.g. other PHM domains) inside a larger enterprise suite — organizational roadmap, not part of the open testbed claims.

### H4. Scientific & community impact

- Target venues appropriate to the contribution (e.g. AIAA SciTech, IEEE aerospace / industrial informatics tracks) with **honest scope**: architecture + open testbed + measured federation vs baselines.  
- Release and maintain the physics-hybrid synthetic corpus (CC-BY style) so others can standardize Non-IID swarm PHM experiments.  
- Invite hardware groups to implement the adapter interface.

---

## Stack diagram (honest)

**Critical path today**

```text
Physics engines → Local windows → CNN-BiLSTM → Sign(ΔW) → FedAvg → Global twin
                                      ↑
                         Command Center (observe)
```

**Horizon only (not required to run or publish the core experiment)**

```text
MAVLink / HIL · MANET radios · DAG store-and-forward · multi-product orchestrator
```

---

## Quick consistency checklist

| Topic | Today (this repo) | Horizon only |
|-------|-------------------|--------------|
| Physics 4-fault engines | Yes | — |
| CNN-BiLSTM | Yes | — |
| Federated params-only | Yes | — |
| Ed25519 update integrity | Yes | Full adversarial robustness |
| Simulated link-loss recovery | Yes (experiment flag) | Real EW / jam resistance |
| Fixed 97.04% accuracy | **No** — use metrics JSON | — |
| DAG on critical path | **No** | Optional |
| Cross-silo learning without raw data | Yes (framing + design) | Corridor product rollout |
| Tactical radio / MANET | **No** | Yes |
| HIL / MAVLink | **No** | Yes |
| Flight-proven TRL 5+ | **No** | Aspirational |

---

## Related docs

- `PAPER_FRAMING.md` — claim sentences, contribution bullets, vocabulary  
- `ARCHITECTURE.md` — pillars and data flow  
- `HARDWARE_ADAPTER.md` — future real-node contract  
- `RUN_SEQUENCE.md` — how to reproduce experiments  

When in doubt: if it is not runnable from `scripts/run_integrity_experiment.py` or the documented modules, it is not “today.”
