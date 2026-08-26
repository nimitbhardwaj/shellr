"""Tests for :mod:`shellr.client.ShellrClient` — uses mock HTTP."""

from __future__ import annotations

from unittest import mock

import pytest
import requests

from shellr.client import ShellrClient


@pytest.fixture
def client(tmp_path):
    secret = tmp_path / ".shellr_secret"
    secret.write_bytes(b"a" * 64)
    secret.chmod(0o600)
    with mock.patch("shellr.client.resolve_tailscale_ip", return_value="100.111.121.72"):
        return ShellrClient(secret_path=secret)


def test_init_loads_secret(client):
    assert len(client.secret) == 64


def test_init_resolves_phone_ip(client):
    assert client.phone_ip == "100.111.121.72"


def test_ping_calls_rpc(client):
    with mock.patch.object(requests, "post") as post:
        post.return_value = mock.Mock(
            status_code=200,
            json=lambda: {"ok": True, "result": {"pong": True}},
        )
        result = client.ping()
    assert result["ok"] is True
    assert result["result"]["pong"] is True
    # Verify the body was signed
    body_arg = post.call_args.kwargs["data"]
    sig_header = post.call_args.kwargs["headers"]["X-Shellr-Signature"]
    assert len(sig_header) == 64
    assert "method" in body_arg.decode()


def test_call_handles_network_error(client):
    with mock.patch.object(requests, "post",
                           side_effect=requests.ConnectionError("nope")):
        result = client.shell("ls")
    assert result["ok"] is False
    assert "ConnectionError" in result["error"]


def test_write_encodes_content(client):
    with mock.patch.object(requests, "post") as post:
        post.return_value = mock.Mock(
            status_code=200, json=lambda: {"ok": True, "result": {"size": 5}},
        )
        client.write("/tmp/x", b"hello")
    body = post.call_args.kwargs["data"].decode()
    assert "content_b64" in body
    # base64("hello") = "aGVsbG8="
    assert "aGVsbG8=" in body


def test_notify_runs_cmd_notification_as_shell(client):
    with mock.patch.object(requests, "post") as post:
        post.return_value = mock.Mock(
            status_code=200, json=lambda: {
                "ok": True, "result": {"ok": True, "stdout": "posting: ...", "stderr": ""},
            },
        )
        result = client.notify("title", "body")
    body = post.call_args.kwargs["data"].decode()
    assert 'su shell' in body
    assert "cmd notification post" in body
    assert "title" in body
    assert result["ok"] is True
