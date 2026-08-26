"""End-to-end smoke test — boots the daemon in-process, hits it over HTTP.

Run with::

    python -m pytest tests/test_smoke.py -v

The daemon binds to ``127.0.0.1`` on a random free port, runs every RPC,
asserts the expected behaviour, then shuts down.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
import requests

from shellr.crypto import sign


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _wait_for_port(port: int, timeout: float = 5.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return True
        except OSError:
            time.sleep(0.05)
    return False


def _post_rpc(base: str, secret: bytes, method: str, params: dict | None = None):
    body = json.dumps({"method": method, "params": params or {}},
                      separators=(",", ":")).encode()
    sig = sign(secret, body)
    return requests.post(base + "/", data=body,
                         headers={"X-Shellr-Signature": sig}, timeout=5)


# ---------------------------------------------------------------------------
# fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def daemon():
    """Boot the daemon on a free port. Yield (base_url, secret, proc)."""
    port = _free_port()
    base = f"http://127.0.0.1:{port}"

    secret_path = Path("/tmp/shellr_smoke_secret")
    secret = b"a" * 64
    secret_path.write_bytes(secret)
    os.chmod(secret_path, 0o600)

    # Use the daemon from the installed package, not a script path
    proc = subprocess.Popen(
        [sys.executable, "-m", "shellr.daemon",
         "--host", "127.0.0.1", "--port", str(port),
         "--secret", str(secret_path),
         "--log", "/tmp/shellrd_smoke.log",
         "--no-su", "--no-tailnet-check"],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        start_new_session=True,
    )
    if not _wait_for_port(port):
        stderr = proc.stderr.read().decode(errors="replace")
        proc.kill()
        raise RuntimeError(f"daemon failed to start:\n{stderr}")
    yield base, secret, proc
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------

def test_health_open(daemon):
    base, _, _ = daemon
    r = requests.get(base + "/health", timeout=3)
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_ping(daemon):
    base, secret, _ = daemon
    r = _post_rpc(base, secret, "ping")
    assert r.json()["result"]["pong"] is True


def test_info(daemon):
    base, secret, _ = daemon
    r = _post_rpc(base, secret, "info")
    assert "host" in r.json()["result"]


def test_shell_echo(daemon):
    base, secret, _ = daemon
    r = _post_rpc(base, secret, "shell", {"command": "echo hello-from-daemon"})
    body = r.json()
    assert body["ok"] is True
    assert "hello-from-daemon" in body["result"]["stdout"]


def test_shell_timeout(daemon):
    base, secret, _ = daemon
    r = _post_rpc(base, secret, "shell", {"command": "sleep 5", "timeout": 1})
    body = r.json()
    assert body["result"]["timed_out"] is True


def test_bad_signature_rejected(daemon):
    base, secret, _ = daemon
    r = requests.post(base + "/", data=b'{"method":"ping","params":{}}',
                      headers={"X-Shellr-Signature": "deadbeef" * 8}, timeout=5)
    assert r.status_code == 401


def test_unknown_method(daemon):
    base, secret, _ = daemon
    r = _post_rpc(base, secret, "nonsense")
    body = r.json()
    # The error is nested in result.error (the RPC handler wraps it there)
    inner_error = (body.get("result") or {}).get("error") or ""
    assert "unknown method" in inner_error


def test_destructive_refused(daemon):
    base, secret, _ = daemon
    r = _post_rpc(base, secret, "shell", {"command": "rm -rf /tmp/whatever"})
    body = r.json()
    assert body["result"]["ok"] is False
    assert "destructive" in body["result"]["stderr"]


def test_path_outside_roots_refused(daemon):
    base, secret, _ = daemon
    r = _post_rpc(base, secret, "read", {"path": "/etc/passwd"})
    body = r.json()
    assert body["ok"] is False
    assert "not under" in (body.get("error") or body["result"].get("stderr", ""))
