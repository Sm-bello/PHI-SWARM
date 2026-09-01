"""
Confidential, authenticated node-to-node messaging.

This gives ZeroTwin nodes ("drones") a way to exchange packages such that:
  - Only the intended recipient can read the contents (X25519 ECDH + HKDF
    + ChaCha20-Poly1305 AEAD). Anyone else observing the channel sees only
    ciphertext.
  - The recipient can prove who sent it and that it was not modified in
    transit (Ed25519 signature over the ciphertext + metadata).
  - A captured/replayed package cannot be re-used later (monotonic
    per-sender-per-recipient counter, rejected on repeat or on decrease).

This is a software-simulation implementation (in-process objects, no real
radio/network layer) matching the rest of the ZeroTwin testbed. It is not a
claim about RF security, jamming resistance, or physical link hardening —
just standard end-to-end authenticated encryption applied to the FL/telemetry
payloads nodes exchange.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field

from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes, serialization

from .signing import NodeKeypair

_HKDF_INFO = b"zerotwin-drone-link-v1"
NONCE_LEN = 12


class ReplayError(Exception):
    """Raised when a package fails the monotonic-counter replay check."""


class TamperError(Exception):
    """Raised when signature verification or AEAD decryption fails."""


@dataclass
class NodeLinkKeys:
    """Per-node X25519 keypair, paired 1:1 with that node's Ed25519 NodeKeypair."""

    private_key: X25519PrivateKey
    public_key: X25519PublicKey
    node_id: int

    @classmethod
    def generate(cls, node_id: int) -> "NodeLinkKeys":
        priv = X25519PrivateKey.generate()
        return cls(priv, priv.public_key(), node_id)

    def public_bytes(self) -> bytes:
        return self.public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )


@dataclass
class EncryptedPackage:
    """What actually crosses the wire. Ciphertext + metadata, nothing readable."""

    sender_id: int
    recipient_id: int
    counter: int
    timestamp: float
    nonce: bytes
    ciphertext: bytes  # AEAD ciphertext, includes the 16-byte auth tag
    signature: bytes  # Ed25519 signature over (aad || ciphertext)

    def aad(self) -> bytes:
        """Additional authenticated data: binds sender/recipient/counter/time
        to this exact ciphertext so none of them can be swapped undetected."""
        return json.dumps(
            {
                "sender_id": self.sender_id,
                "recipient_id": self.recipient_id,
                "counter": self.counter,
                "timestamp": self.timestamp,
            },
            sort_keys=True,
        ).encode()

    def ciphertext_hash_hex(self) -> str:
        """Safe-to-log fingerprint. Never log plaintext or keys."""
        import hashlib

        return hashlib.sha256(self.ciphertext).hexdigest()[:16]


def _derive_key(shared_secret: bytes, sender_id: int, recipient_id: int) -> bytes:
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=_HKDF_INFO + f":{min(sender_id, recipient_id)}:{max(sender_id, recipient_id)}".encode(),
    )
    return hkdf.derive(shared_secret)


@dataclass
class ReplayGuard:
    """Tracks the last accepted counter per (sender, recipient) ordered pair.
    A package is only accepted if its counter is strictly greater than the
    last one seen from that sender to that recipient."""

    _last_counter: dict[tuple[int, int], int] = field(default_factory=dict)

    def check_and_advance(self, sender_id: int, recipient_id: int, counter: int) -> None:
        key = (sender_id, recipient_id)
        last = self._last_counter.get(key, -1)
        if counter <= last:
            raise ReplayError(
                f"package counter {counter} <= last accepted {last} "
                f"for node {sender_id} -> node {recipient_id}"
            )
        self._last_counter[key] = counter


def encrypt_for(
    sender_link: NodeLinkKeys,
    sender_sign: NodeKeypair,
    recipient_public: X25519PublicKey,
    recipient_id: int,
    counter: int,
    plaintext: bytes,
) -> EncryptedPackage:
    """Encrypt+sign a payload only `recipient_id` (holder of the matching
    X25519 private key) can decrypt, and only from `sender_link.node_id`
    (verifiable via Ed25519) can it have come."""
    shared = sender_link.private_key.exchange(recipient_public)
    key = _derive_key(shared, sender_link.node_id, recipient_id)
    aead = ChaCha20Poly1305(key)
    nonce = os.urandom(NONCE_LEN)

    pkg = EncryptedPackage(
        sender_id=sender_link.node_id,
        recipient_id=recipient_id,
        counter=counter,
        timestamp=time.time(),
        nonce=nonce,
        ciphertext=b"",
        signature=b"",
    )
    aad = pkg.aad()
    ciphertext = aead.encrypt(nonce, plaintext, aad)
    pkg.ciphertext = ciphertext
    pkg.signature = sender_sign.private_key.sign(aad + ciphertext)
    return pkg


def decrypt_from(
    pkg: EncryptedPackage,
    recipient_link: NodeLinkKeys,
    sender_public_sign,
    sender_public_link: X25519PublicKey,
    replay_guard: ReplayGuard,
) -> bytes:
    """Verify signature, check replay counter, then decrypt. Raises
    TamperError / ReplayError on any failure — callers should catch these
    and reject the package (log to the audit trail) rather than propagate
    plaintext."""
    aad = pkg.aad()
    try:
        sender_public_sign.verify(pkg.signature, aad + pkg.ciphertext)
    except Exception as exc:
        raise TamperError(f"signature verification failed: {exc}") from exc

    replay_guard.check_and_advance(pkg.sender_id, pkg.recipient_id, pkg.counter)

    shared = recipient_link.private_key.exchange(sender_public_link)
    key = _derive_key(shared, pkg.sender_id, pkg.recipient_id)
    aead = ChaCha20Poly1305(key)
    try:
        return aead.decrypt(pkg.nonce, pkg.ciphertext, aad)
    except Exception as exc:
        raise TamperError(f"AEAD decryption/auth failed: {exc}") from exc
