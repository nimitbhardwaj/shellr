"""The shellr client — the side that *calls* the phone.

Auto-resolves the phone's Tailscale IP from its tailnet hostname on init,
loads the HMAC secret, and exposes a clean Python API.

Typical use::

    from shellr import ShellrClient
    c = ShellrClient()                        # uses ~/.shellr_secret + nimits-a51
    print(c.ping())
    print(c.shell("uptime"))
"""

from __future__ import annotations

import base64
import json
import logging
import time
from pathlib import Path
from typing import Union

import requests

from shellr.crypto import sign
from shellr.resolve import resolve_tailscale_ip

log = logging.getLogger("shellr.client")

DEFAULT_PHONE_NAME = "nimits-a51"
DEFAULT_PORT = 7777
DEFAULT_SECRET_PATH = Path.home() / ".shellr_secret"
DEFAULT_TIMEOUT = 30.0


class ShellrError(RuntimeError):
    """Raised when an RPC call returns ``ok: false`` or transport fails."""


class ShellrClient:
    """HMAC-signed RPC client for the shellr daemon."""

    def __init__(
        self,
        phone: str = DEFAULT_PHONE_NAME,
        port: int = DEFAULT_PORT,
        secret_path: Union[str, Path, None] = None,
        phone_ip: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.phone_name = phone
        self.port = port
        self.secret_path = Path(secret_path or DEFAULT_SECRET_PATH)
        self.secret = self._load_secret(self.secret_path)
        self.phone_ip = phone_ip or resolve_tailscale_ip(phone)
        self.base = f"http://{self.phone_ip}:{port}"
        self.timeout = timeout
        log.info("shellr client ready — phone=%s ip=%s", phone, self.phone_ip)

    # ------------------------------------------------------------------
    # secret handling
    # ------------------------------------------------------------------

    @staticmethod
    def _load_secret(path: Path) -> bytes:
        if not path.exists():
            raise FileNotFoundError(
                f"shellr secret not found at {path}\n"
                f"  generate with: openssl rand -hex 32\n"
                f"  then:  echo '<hex>' > {path} && chmod 600 {path}"
            )
        return path.read_bytes().strip()

    # ------------------------------------------------------------------
    # low-level RPC
    # ------------------------------------------------------------------

    def call(
        self,
        method: str,
        params: dict | None = None,
        timeout: float | None = None,
    ) -> dict:
        """Sign and send one RPC. Always returns a dict (never raises on
        transport errors — those come back as ``{"ok": False, "error": ...}``)."""
        params = params or {}
        body = json.dumps(
            {"method": method, "params": params},
            separators=(",", ":"),
        ).encode()
        signature = sign(self.secret, body)

        t0 = time.monotonic()
        try:
            r = requests.post(
                self.base + "/",
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Shellr-Signature": signature,
                },
                timeout=timeout or self.timeout,
            )
        except requests.RequestException as exc:
            log.error("call %s failed: %s", method, exc)
            return {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "method": method,
            }
        dt = int((time.monotonic() - t0) * 1000)

        try:
            payload = r.json()
        except json.JSONDecodeError:
            payload = {
                "ok": False,
                "error": f"non-json response ({r.status_code}): {r.text[:200]}",
            }

        log.info("call %s -> %d in %dms", method, r.status_code, dt)
        payload.setdefault("_meta", {})["dt_ms"] = dt
        payload["_meta"]["phone_ip"] = self.phone_ip
        return payload

    # ------------------------------------------------------------------
    # convenience methods (one per daemon RPC)
    # ------------------------------------------------------------------

    def ping(self) -> dict:
        return self.call("ping")

    def info(self) -> dict:
        return self.call("info")

    def health(self) -> bool:
        try:
            return requests.get(self.base + "/health", timeout=3).ok
        except requests.RequestException:
            return False

    def shell(self, command: str, timeout: int = 30) -> dict:
        return self.call(
            "shell", {"command": command, "timeout": timeout},
            timeout=timeout + 5,
        )

    def exec(self, command: str, timeout: int = 30) -> dict:
        """Alias for :meth:`shell`."""
        return self.shell(command, timeout=timeout)

    def read(self, path: str, max_bytes: int = 1_048_576) -> dict:
        return self.call("read", {"path": path, "max_bytes": max_bytes})

    def write(self, path: str, content: Union[bytes, str], mode: str = "w") -> dict:
        if isinstance(content, str):
            content = content.encode()
        return self.call("write", {
            "path": path,
            "mode": mode,
            "content_b64": base64.b64encode(content).decode(),
        })

    def listdir(self, path: str) -> dict:
        return self.call("list", {"path": path})

    # ------------------------------------------------------------------
    # helpers built on shell
    # ------------------------------------------------------------------

    def notify(self, title: str, body: str) -> dict:
        """Post a notification to the phone's status bar.

        Runs ``cmd notification`` as the ``shell`` user (root's package
        context is rejected by NotificationManager).
        """
        tag = f"shellr_{int(time.time())}"
        cmd = (
            f"su shell -c '/system/bin/cmd notification post "
            f'-t "{title}" {tag} "{body}"\''
        )
        return self.shell(cmd)

    def __repr__(self) -> str:
        return f"<ShellrClient phone={self.phone_name} ip={self.phone_ip}>"
