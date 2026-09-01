# Paper Framing — ZeroTwin

**Read this before writing abstracts, introductions, or talks.**  
These wordings are calibrated so the work stays profound and defensible.

---

## 1. The claim (use this or a close paraphrase)

**One sentence**

> ZeroTwin is an open, physics-informed federated digital twin that lets a swarm of quadrotor edge nodes collaboratively learn a collective health model without ever sharing raw telemetry — only signed model updates — under controlled degradation physics that match real rotor, thermal, bearing, and battery failure modes.

**Extended (abstract / intro)**

> Multi-party and cross-jurisdictional UAV fleets cannot freely pool continuous sensor histories for prognostics and health management (PHM): policy, data sovereignty, tactical sensitivity, and bandwidth forbid it. Isolated edge models therefore overfit to narrow local fault experience. ZeroTwin addresses this barrier with a physics-hybrid integrity architecture: (1) deterministic degradation engines generate physically grounded local data; (2) a lightweight temporal model trains on-node; (3) only Ed25519-signed weight deltas leave the node and are aggregated via federated averaging; (4) the resulting global model is the collective twin. We evaluate the architecture in an open, reproducible multi-process testbed against centralized and isolated baselines, including recovery after simulated link loss. We do not claim real-airframe flight validation; we release the testbed and an explicit hardware-adapter interface so others can attach real companion computers later.

---

## 2. What the international / cross-border story actually is

**Do say**

- Nodes operated in different countries or by different organizations can refine a **shared health model** without exchanging raw telemetry.
- The only cross-border (or cross-organization) traffic is **signed model updates**.
- This targets the long-standing barrier that multi-party fleets cannot pool sensor histories for PHM, so each remains limited to its own fault experience.
- Intermittent IP connectivity sufficient for model updates is assumed; store-and-forward / delayed aggregation is part of the design space we evaluate.

**Do not say**

- “ZeroTwin lets drones in Nigeria and Ghana communicate across borders — something impossible for years.”
- Any claim that ZeroTwin solves physical radio, spectrum, mesh routing, or regulatory airspace between airframes.
- “Real-time command-and-control across borders.”

**The thing that was hard (and that we address)**

> Collaborative improvement of a collective health/prognostic model when nodes are not allowed or not willing to share the raw sensor streams the model needs.

**The thing we do not solve**

> Guaranteed real-time packet delivery or flight-critical links between physical airframes in different countries.

---

## 3. Niche positioning

ZeroTwin is **not** trying to be:

- The first federated learning paper for UAVs
- The first digital twin for drones
- The first physics-informed PHM model
- A flight-control or autopilot product

ZeroTwin **is** trying to be:

> The most coherent, physics-grounded, zero-leakage, openly runnable **integrity twin** for quadrotor swarm health — architecture + testbed — with an explicit path for hardware attachment later.

---

## 4. Scope and TRL language

| Allowed | Avoid |
|---------|--------|
| Research architecture + simulation testbed | “Product ready for operational swarms” |
| TRL 3 – early 4 (lab / integrated software breadboard) | TRL 5+ or “flight proven” |
| Physics-informed synthetic degradation | “Validated on real flight fault data” (unless you have it) |
| Signed updates and recovery after simulated blackout | “EW-hardened in theater” |
| Open interface for future companion computers | “Works with PX4 out of the box today” |

AIAA and similar venues accept simulation-only work when the contribution is architectural/algorithmic, limits are stated, and numerical claims are reproducible. Over-claiming is what gets rejected.

---

## 5. Suggested contribution bullets (papers)

1. A **physics-hybrid integrity** formulation for quadrotor PHM: four deterministic degradation engines (rotor imbalance, ESC thermal runaway, bearing BPFO, battery voltage sag) that generate non-IID local data and ground the learning problem.
2. A **zero-leakage federated pipeline**: on-node CNN-BiLSTM training, Ed25519-signed weight deltas, Flower aggregation; raw multi-sensor time series never leave the node.
3. An **open integrity testbed** that reproduces accuracy vs centralized and isolated baselines, communication volume, and recovery after multi-round link loss, with public configs and metrics.
4. An explicit **hardware-adapter interface** so real edge boards can later satisfy the same contract the simulated nodes use.

---

## 6. Story arc (talk / paper narrative)

1. **Problem** — Swarm and multi-party operators cannot pool raw telemetry (privacy, sovereignty, bandwidth, contested links). Isolated models stay weak.
2. **Insight** — If degradation is governed by shared physics, nodes can learn a collective twin by exchanging only signed parameter updates; physics keeps local distributions meaningful.
3. **Method** — Physics engines → local hybrid model → signed federated rounds → global twin. Integrity = signatures + recovery experiments.
4. **Evidence** — Testbed results: accuracy gap, bytes moved, recovery dynamics, ablation of physics.
5. **Invitation** — Dataset, code, and adapter contract released for hardware follow-on.

---

## 7. Vocabulary to prefer

| Prefer | Avoid as primary framing |
|--------|---------------------------|
| Physics-hybrid integrity twin | “Military command center product” |
| Zero-leakage / signed model updates | “Fully secure against all adversaries” |
| Cross-silo / multi-party collaborative PHM | “Cross-border drone radio solved” |
| Open reproducible testbed | “NASA TRL 5 edge of 5 ready” |
| Collective health model | “Digital twin of the entire battlespace” |

---

## 8. Suggested short citation stub

```bibtex
@misc{zerotwin2026,
  title  = {ZeroTwin: Physics-Hybrid Integrity Digital Twin for Quadrotor Swarm PHM},
  author = {{PHI Lab} and Bello},
  year   = {2026},
  note   = {Architecture and open simulation testbed. Raw telemetry never leaves the node; only signed model updates are aggregated.}
}
```

Update authors and venue when you submit.
