"""shellr — root-controlled Android phone from a VPS over Tailscale.

Public API:

    from shellr import ShellrClient
    c = ShellrClient()
    print(c.ping())
    print(c.shell("whoami"))
    print(c.info())
"""

from __future__ import annotations

__version__ = "0.2.0"

# Public re-exports
from shellr.client import ShellrClient  # noqa: E402,F401
from shellr.resolve import resolve_tailscale_ip  # noqa: E402,F401

__all__ = ["ShellrClient", "resolve_tailscale_ip", "__version__"]
