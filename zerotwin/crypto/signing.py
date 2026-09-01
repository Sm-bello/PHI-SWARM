"""Ed25519 signing of model parameter payloads (integrity of updates)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives import serialization
import numpy as np


def _canonical_hash(arrays: list[np.ndarray]) -> bytes:
    h = hashlib.sha256()
    for a in arrays:
        arr = np.ascontiguousarray(a)
        h.update(arr.dtype.str.encode())
        h.update(np.array(arr.shape, dtype=np.int64).tobytes())
        h.update(arr.tobytes())
    return h.digest()


@dataclass
class NodeKeypair:
    private_key: Ed25519PrivateKey
    public_key: Ed25519PublicKey
    node_id: int

    @classmethod
    def generate(cls, node_id: int) -> "NodeKeypair":
        priv = Ed25519PrivateKey.generate()
        return cls(priv, priv.public_key(), node_id)

    def public_bytes(self) -> bytes:
        return self.public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )


def sign_parameters(keypair: NodeKeypair, arrays: list[np.ndarray]) -> bytes:
    digest = _canonical_hash(arrays)
    return keypair.private_key.sign(digest)


def verify_parameters(public_key: Ed25519PublicKey, arrays: list[np.ndarray], signature: bytes) -> bool:
    digest = _canonical_hash(arrays)
    try:
        public_key.verify(signature, digest)
        return True
    except Exception:
        return False
