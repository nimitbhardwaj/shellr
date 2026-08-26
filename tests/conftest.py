"""conftest — pytest fixtures."""

from __future__ import annotations

import pytest


@pytest.fixture
def secret() -> bytes:
    """64-char hex secret (32 bytes) for HMAC."""
    return b"a" * 64
