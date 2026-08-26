"""Tests for :mod:`shellr.crypto`."""

from __future__ import annotations

import pytest

from shellr.crypto import sign, verify


def test_sign_returns_hex():
    sig = sign(b"key", b"body")
    assert isinstance(sig, str)
    assert len(sig) == 64     # SHA-256 hex
    int(sig, 16)              # raises if non-hex


def test_verify_accepts_correct_signature():
    sig = sign(b"secret", b"hello")
    assert verify(b"secret", b"hello", sig) is True


def test_verify_rejects_wrong_signature():
    sig = sign(b"secret", b"hello")
    assert verify(b"WRONG", b"hello", sig) is False


def test_verify_rejects_tampered_body():
    sig = sign(b"secret", b"hello")
    assert verify(b"secret", b"hellp", sig) is False


def test_verify_rejects_empty_signature():
    assert verify(b"secret", b"hello", "") is False


def test_sign_is_deterministic():
    a = sign(b"k", b"b")
    b = sign(b"k", b"b")
    assert a == b
