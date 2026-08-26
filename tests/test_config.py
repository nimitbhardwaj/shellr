"""Tests for :mod:`shellr.daemon.config`."""

from __future__ import annotations

from shellr.daemon import config


def test_defaults_present():
    # The daemon refuses to start without --host, so DEFAULT_HOST is None.
    assert config.DEFAULT_HOST is None
    assert isinstance(config.DEFAULT_PORT, int)
    assert config.DEFAULT_PORT > 0


def test_tailnet_cidr_is_tailscale_ipv4():
    assert config.TAILNET_CIDR == "100.64.0.0/10"


def test_allowed_roots_includes_phone_home():
    roots = " ".join(config.ALLOWED_ROOTS)
    assert "/data/local/tmp/shellrd" in roots
    assert "/sdcard" in roots


def test_destructive_patterns_blocked():
    assert any("rm -rf /" in p for p in config.DESTRUCTIVE_PATTERNS)
