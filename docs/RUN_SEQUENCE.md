# Launch / verification sequence — PHI-SWARM

Work from the project root after unzip.

```bash
cd PHI\\\_SWARM
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\\\\Scripts\\\\activate
pip install -r requirements.txt
```

## Gate 1 — Core integrity (L0–L3)

```bash
python scripts/run\_integrity\_experiment.py --nodes 5 --rounds 8 --samples 500 --seed 42
```

Expect: console metrics + `zerotwin/results/integrity\\\_metrics.json`.

## Gate 2 — Multi-seed statistics

```bash
python scripts/run\_seed\_sweep.py
```

Expect: `zerotwin/results/seed\\\_sweep.json`.

## Gate 3 — Link-loss resilience (L4)

```bash
python scripts/run\_link\_loss\_sweep.py
```

Expect: `zerotwin/results/resilience\\\_results.json`.

## Gate 4 — Edge software benchmark

```bash
python scripts/benchmark\_edge.py
```

Expect: `zerotwin/results/edge\\\_benchmark.json`.

## Gate 5 — PHI-SWARM continuous sim (L0–L9)

```bash
# Short check (~2 min)
python scripts/run\_phi\_swarm.py --minutes 2 --round-interval 2

# Stress / demo (~10 min)
python scripts/run\_phi\_swarm.py --minutes 10 --nodes 5
```

Expect: terminal stream of rounds, trust, swarm roles;
`zerotwin/results/audit\\\_trail.jsonl` (hash-chained);
`zerotwin/results/phi\\\_swarm\\\_summary.json` with audit verification.

## Gate 5b — Deterministic L5-L9 validation

```bash
python scripts/validate\_l5\_l9.py
```

Expect: 14/14 checks pass. This is the gate that actually proves malicious-
update rejection + quarantine, replay rejection, degraded-UAV decisioning,
and swarm compensation — Gate 5 above only proves it if a short randomized
run happens to roll each scenario; this doesn't rely on luck.

## Gate 6 — Full validation suite

```bash
python scripts/run\_full\_validation.py
```

Expect: `zerotwin/results/validation\\\_suite.json`.

## Gate 6b — Figures for the paper

```bash
python scripts/run\\\_seed\\\_sweep.py           # figures/seed\\\_sweep\\\_accuracy.png
python scripts/run\\\_link\\\_loss\\\_sweep.py      # figures/resilience\\\_curve.png
python scripts/figure\\\_trust\\\_convergence.py # figures/trust\\\_convergence.png
```

## Gate 7 — Dashboard

```bash
python -m zerotwin.observability.dashboard
# http://127.0.0.1:5000
```

Use `dashboard\\\_live`, not `dashboard` — the latter is a static mockup with no
real engine behind it. `dashboard\\\_live` is wired to the full `PHISwarmEngine`
(trust scores, autonomy decisions, swarm directives all real).

## What LIVE means

Continuous **software** simulation of nodes, faults, FL, integrity, trust, decisions, swarm roles, and audit trail — **not** real aircraft or HIL (L10+).



## Command Center

```bash
python -m zerotwin.observability.command\_center
```

## Paper export

```bash
python scripts/export\_paper\_artifacts.py
```



















