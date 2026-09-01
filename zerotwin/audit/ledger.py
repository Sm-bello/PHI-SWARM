"""
Tamper-evident audit trail.

Every event is one JSON line. Each entry embeds the SHA-256 of the previous
entry's hash, forming an append-only chain. verify() recomputes the chain
from disk.

Hash preimage is the canonical JSON of {seq, ts, event_type, details, prev_hash}
— never an f-string of floats — so write and verify cannot diverge.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

GENESIS_HASH = "0" * 64


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=_json_default)


def _json_default(o: Any) -> Any:
    # numpy / odd scalars → plain Python so hash is stable
    try:
        import numpy as np
        if isinstance(o, np.generic):
            return o.item()
        if isinstance(o, np.ndarray):
            return o.tolist()
    except Exception:
        pass
    if hasattr(o, "item"):
        try:
            return o.item()
        except Exception:
            pass
    return str(o)


def _clean(obj: Any) -> Any:
    """JSON round-trip so in-memory details match on-disk form exactly."""
    return json.loads(_canonical(obj if obj is not None else {}))


@dataclass
class AuditEntry:
    seq: int
    ts: float
    event_type: str
    details: dict
    prev_hash: str
    entry_hash: str = ""

    def body_dict(self) -> dict:
        return {
            "seq": self.seq,
            "ts": self.ts,
            "event_type": self.event_type,
            "details": self.details,
            "prev_hash": self.prev_hash,
        }

    def compute_hash(self) -> str:
        return hashlib.sha256(_canonical(self.body_dict()).encode("utf-8")).hexdigest()


class AuditLedger:
    """Thread-safe, append-only, hash-chained audit log backed by a JSONL file."""

    def __init__(self, path: str | Path, *, reset: bool = False):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._last_hash = GENESIS_HASH
        self._seq = 0
        self._recent: list[AuditEntry] = []
        if reset and self.path.exists():
            self.path.unlink()
        self._load_existing()

    def _load_existing(self) -> None:
        if not self.path.exists():
            return
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                self._seq = int(d["seq"])
                self._last_hash = d["entry_hash"]

    def append(self, event_type: str, details: dict) -> AuditEntry:
        with self._lock:
            self._seq += 1
            clean_details = _clean(details)
            # Freeze ts through JSON so hash uses the exact value written to disk
            ts = _clean(float(time.time()))
            entry = AuditEntry(
                seq=self._seq,
                ts=ts,
                event_type=str(event_type),
                details=clean_details,
                prev_hash=self._last_hash,
            )
            entry.entry_hash = entry.compute_hash()
            record = entry.body_dict()
            record["entry_hash"] = entry.entry_hash
            line = _canonical(record) + "\n"
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line)
                f.flush()
            self._last_hash = entry.entry_hash
            self._recent.append(entry)
            if len(self._recent) > 200:
                self._recent.pop(0)
            return entry

    def recent(self, n: int = 20) -> list[dict]:
        with self._lock:
            out = []
            for e in self._recent[-n:]:
                d = e.body_dict()
                d["entry_hash"] = e.entry_hash
                out.append(d)
            return out

    def verify(self) -> tuple[bool, int | None]:
        """Recompute the chain from disk. Returns (ok, first_bad_seq)."""
        if not self.path.exists():
            return True, None
        prev = GENESIS_HASH
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    return False, None
                body = {
                    "seq": d["seq"],
                    "ts": d["ts"],
                    "event_type": d["event_type"],
                    "details": d["details"],
                    "prev_hash": d["prev_hash"],
                }
                expected = hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()
                if d.get("prev_hash") != prev or d.get("entry_hash") != expected:
                    return False, d.get("seq")
                prev = d["entry_hash"]
        return True, None

    def verify_report(self) -> dict:
        ok, bad = self.verify()
        n = 0
        if self.path.exists():
            with open(self.path, "r", encoding="utf-8") as f:
                n = sum(1 for line in f if line.strip())
        return {
            "verified": ok,
            "first_bad_seq": bad,
            "chain_length": n,
            "path": str(self.path.resolve()),
        }
