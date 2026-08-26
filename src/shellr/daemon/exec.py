"""Daemon execution layer.

Three capabilities:

- :func:`run_shell` — run a command as root, with timeout and output cap.
- :func:`file_read`, :func:`file_write`, :func:`file_list` — file ops
  restricted to :data:`shellr.daemon.config.ALLOWED_ROOTS`.
- :func:`dispatch` — RPC method → handler dispatch.

The daemon runs as root in production. On the VPS-side smoke test we
invoke with ``--no-su`` so commands run directly without root.
"""

from __future__ import annotations

import base64
import ipaddress
import os
import shutil
import subprocess
import time
from pathlib import Path

from shellr.daemon.config import (
    ALLOWED_ROOTS,
    DEFAULT_TIMEOUT,
    DESTRUCTIVE_PATTERNS,
    MAX_FILE_READ_BYTES,
    MAX_OUTPUT_BYTES,
    TAILNET_CIDR,
)


# ---------------------------------------------------------------------------
# Pre-flight: where's `su`?
# ---------------------------------------------------------------------------

def _has_su() -> bool:
    """True if ``su`` is somewhere on PATH or at the standard locations."""
    return (
        os.path.isfile("/system/bin/su")
        or os.path.isfile("/system/xbin/su")
        or os.path.isfile("/sbin/su")
        or shutil.which("su") is not None
    )


# ---------------------------------------------------------------------------
# Shell exec
# ---------------------------------------------------------------------------

def run_shell(command: str, timeout: int, force_su: bool = False) -> dict:
    """Run ``command`` as root via ``/system/bin/sh -c``.

    On a daemon already running as root, ``force_su=False`` runs the
    command directly (no ``su -c`` indirection). On a daemon running as
    a non-root user with ``su`` available, falls back to ``su -c``.

    Returns::

        {"ok": bool, "stdout": str, "stderr": str, "code": int,
         "duration_ms": int, "timed_out": bool, "truncated": bool}
    """
    if timeout <= 0 or timeout > 300:
        timeout = DEFAULT_TIMEOUT

    # Pre-exec safety: refuse obviously hostile patterns.
    if any(p in command for p in DESTRUCTIVE_PATTERNS):
        return {
            "ok": False,
            "stdout": "",
            "stderr": "refused: command matches destructive pattern",
            "code": -1,
            "duration_ms": 0,
            "timed_out": False,
            "truncated": False,
        }

    # --no-su (force_su=False): never use su, even if we're not root.
    # default (force_su=True): use su only when we're not already root.
    use_su = force_su and os.geteuid() != 0
    # /system/bin/sh is Android-specific; /bin/sh is portable. Detect.
    shell_bin = "/system/bin/sh" if os.path.isfile("/system/bin/sh") else "/bin/sh"
    full = ["su", "-c", command] if use_su else [shell_bin, "-c", command]

    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            full,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            start_new_session=True,
        )
    except subprocess.TimeoutExpired as exc:
        duration_ms = int((time.monotonic() - t0) * 1000)
        return {
            "ok": False,
            "stdout": (exc.stdout or b"").decode(errors="replace")[:MAX_OUTPUT_BYTES],
            "stderr": (exc.stderr or b"").decode(errors="replace")[:MAX_OUTPUT_BYTES],
            "code": -1,
            "duration_ms": duration_ms,
            "timed_out": True,
            "truncated": False,
        }

    duration_ms = int((time.monotonic() - t0) * 1000)
    out, err = proc.stdout, proc.stderr
    truncated = False
    if len(out) > MAX_OUTPUT_BYTES:
        out = out[:MAX_OUTPUT_BYTES] + "\n...[truncated]"
        truncated = True
    if len(err) > MAX_OUTPUT_BYTES:
        err = err[:MAX_OUTPUT_BYTES] + "\n...[truncated]"
        truncated = True

    return {
        "ok": proc.returncode == 0,
        "stdout": out,
        "stderr": err,
        "code": proc.returncode,
        "duration_ms": duration_ms,
        "timed_out": False,
        "truncated": truncated,
    }


# ---------------------------------------------------------------------------
# File ops (whitelisted)
# ---------------------------------------------------------------------------

def _check_path(p: str) -> str:
    """Resolve ``p``; raise :class:`ValueError` if outside ALLOWED_ROOTS."""
    rp = str(Path(p).expanduser().resolve(strict=False))
    rp_path = Path(rp)
    for root in ALLOWED_ROOTS:
        try:
            rp_path.resolve(strict=False).relative_to(Path(root).resolve(strict=False))
            return rp
        except ValueError:
            continue
    raise ValueError(f"path {p!r} not under any allowed root")


def file_read(path: str, max_bytes: int = MAX_FILE_READ_BYTES) -> dict:
    rp = _check_path(path)
    with open(rp, "rb") as f:
        data = f.read(max_bytes + 1)
    truncated = len(data) > max_bytes
    if truncated:
        data = data[:max_bytes]
    return {
        "path": rp,
        "size": len(data),
        "truncated": truncated,
        "content_b64": base64.b64encode(data).decode(),
    }


def file_write(path: str, content_b64: str) -> dict:
    rp = _check_path(path)
    data = base64.b64decode(content_b64)
    with open(rp, "wb") as f:
        f.write(data)
    return {"path": rp, "size": len(data)}


def file_list(path: str) -> dict:
    rp = _check_path(path)
    entries = []
    for entry in sorted(Path(rp).iterdir()):
        try:
            st = entry.stat()
            entries.append({
                "name": entry.name,
                "is_dir": entry.is_dir(),
                "size": st.st_size,
                "mtime": int(st.st_mtime),
            })
        except OSError:
            entries.append({"name": entry.name, "error": "stat failed"})
    return {"path": rp, "entries": entries}


# ---------------------------------------------------------------------------
# Method dispatch
# ---------------------------------------------------------------------------

def _android_sdk() -> str:
    try:
        with open("/system/build.prop") as f:
            for line in f:
                if line.startswith("ro.build.version.sdk="):
                    return line.split("=", 1)[1].strip()
                if line.startswith("ro.build.version.release="):
                    return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return "unknown"


def _tailscale_ip() -> str:
    try:
        out = subprocess.run(
            ["tailscale", "ip", "-4"],
            capture_output=True, text=True, timeout=3,
        )
        return out.stdout.strip().splitlines()[0] if out.stdout else ""
    except Exception:
        return ""


def _make_dispatch(use_su: bool):
    """Build a dispatch() closure bound to ``use_su`` policy."""
    def dispatch(method: str, params: dict) -> dict:
        if method == "ping":
            return {
                "pong": True,
                "ts": int(time.time()),
                "uid": os.getuid(),
                "euid": os.geteuid(),
                "host": os.uname().nodename,
                "uptime_s": int(time.time() - Path("/proc").stat().st_mtime),
            }

        if method in ("shell", "shell_sudo"):
            cmd = params.get("command") or params.get("cmd")
            if not cmd or not isinstance(cmd, str):
                return {"ok": False, "error": "missing 'command' string"}
            timeout = int(params.get("timeout", DEFAULT_TIMEOUT))
            return run_shell(cmd, timeout, force_su=use_su)

        if method == "read":
            return file_read(params["path"], int(params.get("max_bytes", MAX_FILE_READ_BYTES)))

        if method == "write":
            return file_write(params["path"], params["content_b64"])

        if method == "list":
            return file_list(params["path"])

        if method == "info":
            return {
                "host": os.uname().nodename,
                "kernel": os.uname().release,
                "android_sdk": _android_sdk(),
                "termux": os.environ.get("PREFIX", ""),
                "uid": os.getuid(),
                "euid": os.geteuid(),
                "tailscale_ip": _tailscale_ip(),
            }

        return {"ok": False, "error": f"unknown method {method!r}"}

    return dispatch


def tailnet_check(source_ip: str) -> bool:
    """Return True if ``source_ip`` is in the configured Tailscale CIDR."""
    if not TAILNET_CIDR:
        return True
    try:
        addr = ipaddress.ip_address(source_ip)
        net = ipaddress.ip_network(TAILNET_CIDR, strict=False)
        return addr in net
    except ValueError:
        return False
