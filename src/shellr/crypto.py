"""HMAC-SHA256 request signing.

The daemon and the client share a pre-shared secret. Every request body is
signed; the daemon verifies the signature before dispatching.

Header on the wire: ``X-Shellr-Signature: <hex>``.

The daemon refuses to start if the secret file's permissions are looser than
``0600`` — defence in depth against accidental world-readable secrets.
"""

from __future__ import annotations

import hashlib
import hmac


def sign(secret: bytes, body: bytes) -> str:
    """Return the hex-encoded HMAC-SHA256 of ``body`` keyed by ``secret``."""
    return hmac.new(secret, body, hashlib.sha256).hexdigest()


def verify(secret: bytes, body: bytes, signature: str) -> bool:
    """Constant-time signature check."""
    expected = sign(secret, body)
    return hmac.compare_digest(expected, signature or "")
