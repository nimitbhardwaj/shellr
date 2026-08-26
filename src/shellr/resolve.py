"""Resolve a Tailscale hostname to its ``100.x.y.z`` tunnel IP.

Strategy (in order):

1. Native DNS resolution via :func:`socket.getaddrinfo` — works on any host
   that has MagicDNS resolvable (``nimits-a51`` → ``100.x.y.z``).
2. Local ``tailscale status --json`` lookup — works without DNS if the
   binary is on PATH and authenticated.
3. ``tailscale ip -4 <name>`` — last-resort CLI.

Raises :class:`RuntimeError` if nothing works; the caller should pass
``--phone-ip`` to override.
"""

from __future__ import annotations

import json
import socket
import subprocess
from typing import Iterable


def resolve_tailscale_ip(
    name: str,
    candidates: Iterable[str] | None = None,
    timeout: float = 5.0,
) -> str:
    """Return the Tailscale IPv4 address for ``name`` (e.g. ``nimits-a51``)."""
    hostnames = list(candidates) if candidates else [name, f"{name}.local"]

    # 1. Native DNS
    for host in hostnames:
        try:
            infos = socket.getaddrinfo(host, None, socket.AF_INET)
            for family, _type, _proto, _canon, sockaddr in infos:
                if family == socket.AF_INET and sockaddr[0].startswith("100."):
                    return sockaddr[0]
        except socket.gaierror:
            continue

    # 2. tailscale status --json
    try:
        out = subprocess.run(
            ["tailscale", "status", "--json"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if out.returncode == 0:
            data = json.loads(out.stdout)
            for peer in data.get("Peer", {}).values():
                host_name = peer.get("HostName", "").lower()
                if host_name == name.lower() or host_name.split(".")[0] == name.lower():
                    for ip in peer.get("TailscaleIPs", []):
                        if ip.startswith("100."):
                            return ip
            self_status = data.get("Self") or {}
            for ip in self_status.get("TailscaleIPs", []):
                if ip.startswith("100."):
                    return ip
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
        pass

    # 3. tailscale ip -4
    try:
        out = subprocess.run(
            ["tailscale", "ip", "-4", name],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip().splitlines()[0]
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    raise RuntimeError(
        f"could not resolve Tailscale IP for {name!r}. "
        "Is the host on the tailnet? Is `tailscale` installed? "
        "Pass --phone-ip to override."
    )
