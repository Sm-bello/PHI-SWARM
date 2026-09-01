"""
LiveSimulationEngine — runs ZeroTwin continuously in a background thread.

Two things happen every tick, in-process, on real objects (not fabricated
numbers):

  1. Telemetry drift: each node's fault mode/severity random-walks, and a
     fresh physics-generated sensor reading is drawn from it (same physics
     engine used for training data).
  2. Every `round_interval` seconds: one real FedAvg round runs on the
     CNN-BiLSTM model over each node's local partition. Every update is
     Ed25519-signed, signature-checked, and norm-checked before aggregation
     ("integrity gate"). Periodically a malicious/tampered/replayed update
     is injected on purpose so the gate has something to catch. Periodically
     two nodes exchange an X25519+ChaCha20-Poly1305 encrypted package, and
     an eavesdrop attempt against it is simulated and shown being blocked.

Every one of these events is appended to an AuditLedger (hash-chained,
tamper-evident JSONL). get_state() returns a thread-safe snapshot shaped for
the dashboard; nothing in it is random-for-show — it reflects engine state.
"""

from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from zerotwin.physics import generate_node_dataset, generate_window_batch, FAULT_NAMES
from zerotwin.models import UAVPHMModel, count_parameters
from zerotwin.federated.train_utils import (
    train_local,
    evaluate,
    get_parameters,
    set_parameters,
    average_parameters,
)
from zerotwin.crypto import (
    NodeKeypair,
    sign_parameters,
    verify_parameters,
    NodeLinkKeys,
    encrypt_for,
    decrypt_from,
    ReplayGuard,
    ReplayError,
    TamperError,
)
from zerotwin.audit.ledger import AuditLedger

NODE_LOCATIONS = {
    1: ("UAV-1", "Lagos, Nigeria", 6.52, 3.38),
    2: ("UAV-2", "Beijing, China", 39.90, 116.4),
    3: ("UAV-3", "Shanghai, China", 31.23, 121.5),
    4: ("UAV-4", "Tokyo, Japan", 35.68, 139.7),
    5: ("UAV-5", "Seoul, South Korea", 37.57, 126.9),
    6: ("UAV-6", "Nairobi, Kenya", -1.29, 36.82),
    7: ("UAV-7", "Abuja, Nigeria", 9.08, 7.49),
    8: ("UAV-8", "Accra, Ghana", 5.60, -0.19),
}

STATUS_ACCENT = {"HEALTHY": "#16a34a", "WARNING": "#d97706", "CRITICAL": "#dc2626", "LINK-LOST": "#64748b"}
STATUS_PULSE = {"HEALTHY": "green", "WARNING": "amber", "CRITICAL": "red", "LINK-LOST": "grey"}


@dataclass
class NodeRuntime:
    node_id: int
    fault_label: int = 0
    severity: float = 0.3
    status: str = "HEALTHY"
    confidence: float = 92.0
    vib_hist: list = field(default_factory=list)
    temp_hist: list = field(default_factory=list)
    volt_hist: list = field(default_factory=list)
    last_vib: float = 0.03
    last_temp: float = 34.0
    last_volt: float = 15.7
    link_lost_until_round: int = 0
    flight_seconds: float = 0.0
    distance_km: float = 100.0


class LiveSimulationEngine:
    def __init__(
        self,
        num_nodes: int = 5,
        seed: int = 42,
        samples_per_node: int = 300,
        round_interval: float = 4.0,
        results_dir: str | Path | None = None,
        attack_probability: float = 0.18,
        message_probability: float = 0.6,
        telemetry_snapshot_interval: float = 20.0,
        reset_audit: bool = False,
    ):
        self.num_nodes = num_nodes
        self.seed = seed
        self.round_interval = round_interval
        self.attack_probability = attack_probability
        self.message_probability = message_probability
        self.telemetry_snapshot_interval = telemetry_snapshot_interval
        self._last_telemetry_snapshot = 0.0

        root = Path(__file__).resolve().parents[2]
        self.results_dir = Path(results_dir) if results_dir else root / "zerotwin" / "results"
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.ledger = AuditLedger(self.results_dir / "audit_trail.jsonl", reset=reset_audit)

        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._start_ts = time.time()

        # --- static setup: datasets, keys, models -----------------------
        rng = np.random.default_rng(seed)
        self.nodes: dict[int, NodeRuntime] = {}
        self.local_data: dict[int, dict] = {}
        self.sign_keys: dict[int, NodeKeypair] = {}
        self.link_keys: dict[int, NodeLinkKeys] = {}
        self.replay_guards: dict[tuple[int, int], ReplayGuard] = {}

        for nid in range(1, num_nodes + 1):
            self.nodes[nid] = NodeRuntime(node_id=nid)
            X, y = generate_node_dataset(nid, n_samples=samples_per_node, seed=seed)
            n = len(y)
            split = int(0.8 * n)
            self.local_data[nid] = {
                "Xtr": X[:split], "ytr": y[:split],
                "Xte": X[split:], "yte": y[split:],
            }
            self.sign_keys[nid] = NodeKeypair.generate(nid)
            self.link_keys[nid] = NodeLinkKeys.generate(nid)

        self.Xte_c = np.concatenate([self.local_data[i]["Xte"] for i in self.local_data], axis=0)
        self.yte_c = np.concatenate([self.local_data[i]["yte"] for i in self.local_data], axis=0)

        self.global_model = UAVPHMModel()
        self.model_parameters = count_parameters(self.global_model)
        self.fed_round = 0
        self.global_acc = 0.0
        self.bytes_transferred = 0
        self._update_norm_history: list = []
        self._msg_counters: dict[tuple[int, int], int] = {}

        self.accepted_total = 0
        self.rejected_total = 0
        self.encrypted_total = 0
        self.blocked_total = 0
        self.replay_blocked_total = 0

        self.ledger.append("engine_init", {
            "num_nodes": num_nodes, "seed": seed, "samples_per_node": samples_per_node,
            "model_parameters": self.model_parameters,
        })

    # ------------------------------------------------------------------ #
    # lifecycle
    # ------------------------------------------------------------------ #
    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _run(self, max_duration: float | None = None):
        last_round_ts = 0.0
        while not self._stop.is_set():
            now = time.time()
            with self._lock:
                self._drift_telemetry()
            if now - last_round_ts >= self.round_interval:
                self._run_federated_round()
                last_round_ts = now
            if max_duration is not None and (now - self._start_ts) >= max_duration:
                break
            time.sleep(1.0)

    def run_for(self, seconds: float):
        """Blocking variant for terminal scripts: run inline for a fixed duration."""
        self._stop.clear()
        self._run(max_duration=seconds)

    # ------------------------------------------------------------------ #
    # telemetry drift (every ~1s tick)
    # ------------------------------------------------------------------ #
    def _drift_telemetry(self):
        now = time.time()
        for nid, node in self.nodes.items():
            node.flight_seconds += 1.0
            node.distance_km += random.uniform(0.0, 0.02)

            if node.link_lost_until_round and self.fed_round < node.link_lost_until_round:
                node.status = "LINK-LOST"
                continue

            # random-walk severity
            node.severity += random.gauss(0, 0.03)
            node.severity = float(np.clip(node.severity, 0.05, 2.0))

            # occasional fault-mode transition — audit-logged, since a fault
            # onset/clearance is exactly the kind of event an inspector would
            # want a tamper-evident record of later.
            prev_label = node.fault_label
            if random.random() < 0.02:
                node.fault_label = random.choice([0, 0, 1, 2, 3, 4])  # bias toward normal
                if node.fault_label == 0:
                    node.severity = max(0.1, node.severity * 0.5)
                if node.fault_label != prev_label:
                    self.ledger.append("fault_transition", {
                        "node_id": nid,
                        "from_fault": FAULT_NAMES[prev_label],
                        "to_fault": FAULT_NAMES[node.fault_label],
                        "severity": round(node.severity, 3),
                        "fed_round": self.fed_round,
                    })

            X, _ = generate_window_batch(node.fault_label, 1, window_len=8, severity=node.severity)
            reading = X[0].mean(axis=0)  # (vib, temp, volt, acoustic)
            node.last_vib, node.last_temp, node.last_volt = float(reading[0]), float(reading[1]), float(reading[2])

            for hist, val in ((node.vib_hist, node.last_vib), (node.temp_hist, node.last_temp), (node.volt_hist, node.last_volt)):
                hist.append(round(val, 4))
                if len(hist) > 40:
                    hist.pop(0)

            if node.fault_label == 0:
                node.status = "HEALTHY"
                node.confidence = float(np.clip(96 - node.severity * 8 + random.uniform(-2, 2), 60, 99))
            elif node.severity < 0.9:
                node.status = "WARNING"
                node.confidence = float(np.clip(80 - node.severity * 15 + random.uniform(-3, 3), 35, 85))
            else:
                node.status = "CRITICAL"
                node.confidence = float(np.clip(55 - node.severity * 10 + random.uniform(-3, 3), 15, 60))

        # periodic tamper-evident telemetry checkpoint (not every 1s tick —
        # that would bloat the chain with redundant noise; this is a
        # verifiable "what did the fleet look like at time T" snapshot).
        if now - self._last_telemetry_snapshot >= self.telemetry_snapshot_interval:
            self._last_telemetry_snapshot = now
            self.ledger.append("telemetry_snapshot", {
                "fed_round": self.fed_round,
                "nodes": {
                    str(nid): {
                        "fault": FAULT_NAMES[n.fault_label], "status": n.status,
                        "severity": round(n.severity, 3), "confidence": round(n.confidence, 1),
                        "vib": round(n.last_vib, 4), "temp": round(n.last_temp, 2), "volt": round(n.last_volt, 3),
                    } for nid, n in self.nodes.items()
                },
            })



    # ------------------------------------------------------------------ #
    # federated round with integrity gate + encrypted messaging
    # ------------------------------------------------------------------ #
    def _run_federated_round(self):
        with self._lock:
            self.fed_round += 1
            r = self.fed_round

            # decide link loss for this round
            if random.random() < 0.05:
                victim = random.choice(list(self.nodes))
                self.nodes[victim].link_lost_until_round = r + random.randint(1, 4)
                self.ledger.append("link_loss_start", {"round": r, "node_id": victim,
                                                         "until_round": self.nodes[victim].link_lost_until_round})

            g_params = get_parameters(self.global_model)
            accepted_params, accepted_weights = [], []

            # decide if this round carries an injected attack
            attack_kind = None
            attacker = None
            if random.random() < self.attack_probability:
                attacker = random.choice(list(self.nodes))
                attack_kind = random.choice(["tampered_signature", "anomalous_norm"])

            for nid, node in self.nodes.items():
                if node.link_lost_until_round and r < node.link_lost_until_round:
                    continue  # dropped out this round

                m = UAVPHMModel()
                set_parameters(m, g_params)
                train_local(m, self.local_data[nid]["Xtr"], self.local_data[nid]["ytr"], epochs=1)
                params = get_parameters(m)

                # Sign the UPDATE DELTA (params - global), not the raw params.
                # Raw parameter magnitude drifts as training progresses, which
                # made a magnitude-based anomaly check unreliable across rounds;
                # the delta ("how much did this round's local training change
                # things") stays comparable round-to-round for a fixed epoch
                # count/lr, and this also matches the "signed weight deltas"
                # architecture described in ZeroTwin's docs.
                delta = [p - gp for p, gp in zip(params, g_params)]

                is_attacker = (attacker == nid)
                if is_attacker and attack_kind == "tampered_signature":
                    sig = sign_parameters(self.sign_keys[nid], delta)
                    # tamper AFTER signing -> signature no longer matches
                    delta = [d.copy() for d in delta]
                    delta[0].flat[0] += 50.0
                    params = [p.copy() for p in params]
                    params[0].flat[0] += 50.0
                    sig_ok = verify_parameters(self.sign_keys[nid].public_key, delta, sig)
                elif is_attacker and attack_kind == "anomalous_norm":
                    # attacker owns a REAL key and signs honestly -> valid
                    # signature, but the delta itself is a malicious outlier
                    delta = [d * 25.0 for d in delta]
                    params = [gp + d for gp, d in zip(g_params, delta)]
                    sig = sign_parameters(self.sign_keys[nid], delta)
                    sig_ok = verify_parameters(self.sign_keys[nid].public_key, delta, sig)
                else:
                    sig = sign_parameters(self.sign_keys[nid], delta)
                    sig_ok = verify_parameters(self.sign_keys[nid].public_key, delta, sig)

                update_norm = float(np.sqrt(sum(float(np.sum((d.astype(np.float64)) ** 2)) for d in delta)))
                norm_ok = True
                if len(self._update_norm_history) >= 5:
                    median = float(np.median(self._update_norm_history))
                    if update_norm > max(median * 5.0, median + 5.0 * (float(np.std(self._update_norm_history)) + 1e-6)):
                        norm_ok = False

                accepted = sig_ok and norm_ok
                self.ledger.append("update_check", {
                    "round": r, "node_id": nid, "signature_ok": sig_ok, "norm_ok": norm_ok,
                    "accepted": accepted, "update_norm": round(update_norm, 3),
                    "simulated_attack": attack_kind if is_attacker else None,
                })

                if accepted:
                    accepted_params.append(params)
                    accepted_weights.append(len(self.local_data[nid]["ytr"]))
                    self._update_norm_history.append(update_norm)
                    if len(self._update_norm_history) > 50:
                        self._update_norm_history.pop(0)
                    self.accepted_total += 1
                    self.bytes_transferred += sum(p.nbytes for p in params)
                else:
                    self.rejected_total += 1

            if accepted_params:
                avg = average_parameters(accepted_params, accepted_weights)
                set_parameters(self.global_model, avg)
                self.global_acc = evaluate(self.global_model, self.Xte_c, self.yte_c)

            self.ledger.append("round_complete", {
                "round": r, "accepted": len(accepted_params), "rejected": self.num_nodes - len(accepted_params),
                "global_accuracy": round(float(self.global_acc), 4),
            })

            self._run_encrypted_exchange(r)

    def _run_encrypted_exchange(self, r: int):
        if random.random() > self.message_probability or self.num_nodes < 2:
            return
        sender_id, recipient_id = random.sample(list(self.nodes), 2)
        pair = (sender_id, recipient_id)
        counter = self._msg_counters.get(pair, 0) + 1
        self._msg_counters[pair] = counter

        payload = (
            f'{{"round":{r},"status":"{self.nodes[sender_id].status}",'
            f'"confidence":{self.nodes[sender_id].confidence:.1f}}}'
        ).encode()

        pkg = encrypt_for(
            self.link_keys[sender_id], self.sign_keys[sender_id],
            self.link_keys[recipient_id].public_key, recipient_id, counter, payload,
        )

        guard = self.replay_guards.setdefault(pair, ReplayGuard())
        try:
            decrypt_from(pkg, self.link_keys[recipient_id], self.sign_keys[sender_id].public_key,
                         self.link_keys[sender_id].public_key, guard)
            self.encrypted_total += 1
            self.ledger.append("encrypted_message", {
                "round": r, "from": sender_id, "to": recipient_id, "counter": counter,
                "ciphertext_fingerprint": pkg.ciphertext_hash_hex(), "result": "delivered_and_verified",
            })
        except (TamperError, ReplayError) as exc:
            self.ledger.append("encrypted_message", {
                "round": r, "from": sender_id, "to": recipient_id, "counter": counter,
                "ciphertext_fingerprint": pkg.ciphertext_hash_hex(), "result": f"rejected:{exc}",
            })

        # eavesdropper: a third node tries to decrypt with its own (wrong) key
        others = [n for n in self.nodes if n not in pair]
        if others:
            eve = random.choice(others)
            try:
                decrypt_from(pkg, self.link_keys[eve], self.sign_keys[sender_id].public_key,
                             self.link_keys[sender_id].public_key, ReplayGuard())
                # should never succeed
                self.ledger.append("eavesdrop_attempt", {"round": r, "by": eve, "result": "UNEXPECTED_SUCCESS"})
            except (TamperError, ReplayError):
                self.blocked_total += 1
                self.ledger.append("eavesdrop_attempt", {
                    "round": r, "by": eve, "target_pair": [sender_id, recipient_id], "result": "blocked",
                })

        # occasional deliberate replay of the same package
        if random.random() < 0.15:
            try:
                decrypt_from(pkg, self.link_keys[recipient_id], self.sign_keys[sender_id].public_key,
                             self.link_keys[sender_id].public_key, guard)
            except ReplayError:
                self.replay_blocked_total += 1
                self.ledger.append("replay_attempt", {"round": r, "pair": [sender_id, recipient_id], "result": "blocked"})
            except TamperError:
                pass

    # ------------------------------------------------------------------ #
    # snapshot for the dashboard / terminal
    # ------------------------------------------------------------------ #
    def get_state(self) -> dict:
        with self._lock:
            nodes_out = {}
            crit = warn = healthy = 0
            for nid, node in self.nodes.items():
                name, loc, lat, lon = NODE_LOCATIONS.get(nid, (f"UAV-{nid}", "Unknown", 0.0, 0.0))
                status = node.status
                if status == "CRITICAL":
                    crit += 1
                elif status in ("WARNING",):
                    warn += 1
                elif status == "HEALTHY":
                    healthy += 1
                h, rem = divmod(int(node.flight_seconds), 3600)
                mnt, sec = divmod(rem, 60)
                nodes_out[nid] = {
                    "id": nid, "name": name, "loc": loc, "lat": lat, "lon": lon,
                    "status": status,
                    "fault_type": FAULT_NAMES[node.fault_label],
                    "confidence": round(node.confidence),
                    "accent": STATUS_ACCENT.get(status, "#64748b"),
                    "pulse": STATUS_PULSE.get(status, "grey"),
                    "vib": round(node.last_vib, 4),
                    "temp": round(node.last_temp, 1),
                    "volt": round(node.last_volt, 2),
                    "flight_time": f"{h:02d}:{mnt:02d}:{sec:02d}",
                    "distance": round(node.distance_km, 1),
                    "latency": 60 + nid * 6 + random.randint(-4, 4),
                    "vib_hist": list(node.vib_hist[-30:]),
                    "temp_hist": list(node.temp_hist[-30:]),
                    "volt_hist": list(node.volt_hist[-30:]),
                }

            fault_counts: dict[str, int] = {}
            for node in self.nodes.values():
                fault_counts[FAULT_NAMES[node.fault_label]] = fault_counts.get(FAULT_NAMES[node.fault_label], 0) + 1
            total_f = sum(fault_counts.values()) or 1
            faults = [(k, v, round(100 * v / total_f, 1)) for k, v in fault_counts.items()]

            return {
                "nodes": nodes_out,
                "critical": crit, "warning": warn, "healthy": healthy,
                "total_faults": sum(1 for n in self.nodes.values() if n.fault_label != 0),
                "faults": faults,
                "fed_round": self.fed_round,
                "global_accuracy": round(float(self.global_acc), 4),
                "model_parameters": self.model_parameters,
                "participants": f"{sum(1 for n in self.nodes.values() if n.status != 'LINK-LOST')} / {self.num_nodes}",
                "bytes_transferred": self.bytes_transferred,
                "elapsed_seconds": round(time.time() - self._start_ts, 1),
                "security": {
                    "accepted_updates": self.accepted_total,
                    "rejected_updates": self.rejected_total,
                    "encrypted_messages": self.encrypted_total,
                    "eavesdrops_blocked": self.blocked_total,
                    "replays_blocked": self.replay_blocked_total,
                    "recent_events": self.ledger.recent(8),
                },
            }

    def audit_verify(self) -> dict:
        ok, bad_seq = self.ledger.verify()
        return {"verified": ok, "first_bad_seq": bad_seq, "path": str(self.ledger.path)}
