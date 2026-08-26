"""Tests for :mod:`shellr.resolve` (Tailscale IP discovery)."""

from __future__ import annotations

import json
from unittest import mock

import pytest

from shellr.resolve import resolve_tailscale_ip


def test_resolves_via_dns(monkeypatch):
    """When getaddrinfo returns a 100.x address, that's our result."""

    fake_addrinfo = [(2, 1, 6, "", ("100.111.121.72", 0))]

    with mock.patch("socket.getaddrinfo", return_value=fake_addrinfo):
        ip = resolve_tailscale_ip("nimits-a51")
    assert ip == "100.111.121.72"


def test_falls_back_to_tailscale_status_json(monkeypatch):
    """If DNS fails, try tailscale status --json."""

    import socket as _socket
    monkeypatch.setattr(_socket, "getaddrinfo",
                        mock.Mock(side_effect=_socket.gaierror))

    fake_status = json.dumps({
        "Peer": {
            "abc123": {
                "HostName": "nimits-a51",
                "TailscaleIPs": ["100.111.121.72", "fd7a:115c:a1e0::53"],
            }
        },
        "Self": {},
    })

    class FakeProc:
        returncode = 0
        stdout = fake_status
        stderr = ""

    with mock.patch("subprocess.run", return_value=FakeProc()) as run_mock:
        ip = resolve_tailscale_ip("nimits-a51")

    assert ip == "100.111.121.72"
    # Confirm we tried tailscale status --json
    args = run_mock.call_args[0][0]
    assert args[0] == "tailscale"
    assert args[1] == "status"


def test_raises_when_nothing_works(monkeypatch):
    import socket as _socket
    monkeypatch.setattr(_socket, "getaddrinfo",
                        mock.Mock(side_effect=_socket.gaierror))

    class FakeProc:
        returncode = 1
        stdout = ""
        stderr = "not running"

    with mock.patch("subprocess.run", return_value=FakeProc()):
        with pytest.raises(RuntimeError, match="could not resolve"):
            resolve_tailscale_ip("nowhere.invalid")
