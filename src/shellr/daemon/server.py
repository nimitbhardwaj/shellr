"""HTTP transport — the daemon's only network surface.

A :class:`ThreadingHTTPServer` subclass threads the secret into the
handler (one thread per request; cheap, sleeps on kernel epoll when idle).

Routes:
    GET  /health       — open liveness probe
    POST /             — RPC entry; HMAC + tailnet-CIDR enforced
"""

from __future__ import annotations

import json
import logging
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from shellr.crypto import verify
from shellr.daemon.exec import _make_dispatch, tailnet_check
from shellr.daemon.config import MAX_REQUEST_BYTES

log = logging.getLogger("shellrd.http")


# ---------------------------------------------------------------------------
# Server builder
# ---------------------------------------------------------------------------

def build_server(
    *,
    host: str,
    port: int,
    secret_path: str,
    log_path: str,
    use_su: bool,
    check_tailnet: bool,
):
    """Load the secret, wire up the handler, return an unstarted server."""
    from shellr.daemon.logging import setup_logging
    setup_logging(log_path)

    secret = _load_secret(secret_path)
    dispatch = _make_dispatch(use_su=use_su)

    handler_cls = _make_handler(
        secret=secret,
        dispatch=dispatch,
        check_tailnet=check_tailnet,
    )

    server = ShellrServer((host, port), handler_cls)
    log.info("shellrd listening on %s:%d (secret=%d bytes, log=%s)",
             host, port, len(secret), log_path)
    log.info("allowed roots: %s", _format_allowed_roots())
    return server


def _format_allowed_roots() -> str:
    from shellr.daemon.config import ALLOWED_ROOTS
    return ", ".join(ALLOWED_ROOTS)


def _load_secret(path: str) -> bytes:
    p = Path(path)
    if not p.exists():
        raise SystemExit(
            f"shellrd: secret not found at {path}\n"
            f"  generate one with: openssl rand -hex 32\n"
            f"  then: echo '<hex>' > {path} && chmod 600 {path}"
        )
    mode = p.stat().st_mode & 0o777
    if mode & 0o077:
        raise SystemExit(
            f"shellrd: REFUSING to start — {path} is mode {oct(mode)}, "
            "must be 600 or 400. Fix with: chmod 600 <path>"
        )
    return p.read_bytes().strip()


def run_server(server) -> int:
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("shellrd interrupted, shutting down")
        server.shutdown()
    return 0


# ---------------------------------------------------------------------------
# Handler factory
# ---------------------------------------------------------------------------

def _make_handler(*, secret: bytes, dispatch, check_tailnet: bool):
    """Closure → handler subclass with bound secret + dispatch."""

    class ShellrHandler(BaseHTTPRequestHandler):
        server_version = "shellrd/1.0"

        # Quiet the default per-request stderr noise.
        def log_message(self, fmt, *args):
            pass

        # ------------------------------------------------------------------
        # routing
        # ------------------------------------------------------------------

        def do_POST(self):  # noqa: N802
            if self.path == "/":
                self._handle_root()
            elif self.path == "/health":
                self._handle_health()
            else:
                self.send_error(404, "unknown path")

        def do_GET(self):  # noqa: N802
            if self.path == "/health":
                self._handle_health()
            else:
                self.send_error(404, "unknown path")

        # ------------------------------------------------------------------
        # handlers
        # ------------------------------------------------------------------

        def _handle_health(self):
            body = json.dumps({
                "ok": True, "service": "shellrd", "ts": int(time.time()),
            }).encode()
            self._write(200, body)

        def _handle_root(self):
            # Tailnet CIDR check — defence in depth on top of HMAC.
            if check_tailnet and not tailnet_check(self.client_address[0]):
                log.warning("rejected non-tailnet source %s",
                            self.client_address[0])
                return self._write_json(403, {
                    "ok": False, "error": "source not in tailnet",
                })

            # Read body
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                return self._write_json(400, {
                    "ok": False, "error": "bad Content-Length",
                })
            if length <= 0 or length > MAX_REQUEST_BYTES:
                return self._write_json(400, {
                    "ok": False, "error": "bad Content-Length",
                })
            body = self.rfile.read(length)

            # Verify HMAC
            sig = self.headers.get("X-Shellr-Signature", "")
            if not verify(secret, body, sig):
                log.warning("HMAC mismatch from %s — body=%d bytes sig=%s...",
                            self.client_address[0], len(body), sig[:8])
                return self._write_json(401, {
                    "ok": False, "error": "bad signature",
                })

            # Parse
            try:
                req = json.loads(body)
            except json.JSONDecodeError as exc:
                return self._write_json(400, {
                    "ok": False, "error": f"bad json: {exc}",
                })
            method = req.get("method")
            params = req.get("params") or {}
            if not isinstance(params, dict):
                return self._write_json(400, {
                    "ok": False, "error": "params must be object",
                })
            if not isinstance(method, str):
                return self._write_json(400, {
                    "ok": False, "error": "method must be string",
                })

            # Dispatch + audit
            t0 = time.monotonic()
            try:
                result = dispatch(method, params)
                err = None
            except Exception as exc:
                result = None
                err = f"{type(exc).__name__}: {exc}"
            dt_ms = int((time.monotonic() - t0) * 1000)

            log.info("rpc method=%s from=%s dt_ms=%d err=%s",
                     method, self.client_address[0], dt_ms, err)

            body_out = json.dumps({
                "ok": err is None,
                "method": method,
                "result": result,
                "error": err,
                "dt_ms": dt_ms,
            }).encode()
            self._write(200, body_out)

        # ------------------------------------------------------------------
        # helpers
        # ------------------------------------------------------------------

        def _write(self, code: int, body: bytes):
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _write_json(self, code: int, payload: Any):
            self._write(code, json.dumps(payload).encode())

    return ShellrHandler


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

class ShellrServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
