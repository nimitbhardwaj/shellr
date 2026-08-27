"""shellrd — the phone-side daemon.

Runs on the rooted Android, listens ONLY on the Tailscale tunnel IP, talks
JSON-RPC over HTTP. Every request is HMAC-SHA256 signed. Every exec runs
as root directly (no ``su`` indirection when running as uid 0). Every
request is audit-logged to ``/sdcard/shellr.log``.

Module layout:

    shellr.daemon        # you are here — main entry point
    shellr.daemon.config  # DEFAULT_HOST, DEFAULT_PORT, ALLOWED_ROOTS, ...
    shellr.daemon.exec    # run_shell(), file_read/write/list(), dispatch
    shellr.daemon.server  # HTTP handler + ThreadingHTTPServer subclass

Run with::

    python -m shellr.daemon --host 100.x.y.z --port 7777 \\
        --secret /data/adb/shellrd/.shellr_secret
"""

from __future__ import annotations

import argparse
import logging
import sys

from shellr.daemon.config import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    DEFAULT_SECRET_PATH,
    DEFAULT_LOG_PATH,
)
from shellr.daemon.server import build_server, run_server

log = logging.getLogger("shellrd")


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        prog="shellrd",
        description="shellr daemon — phone-side RPC over Tailscale",
    )
    ap.add_argument("--host", default=DEFAULT_HOST,
                    help="IP to bind to (default: %(default)s)")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT,
                    help="port to listen on (default: %(default)s)")
    ap.add_argument("--secret", default=DEFAULT_SECRET_PATH,
                    help="path to the HMAC pre-shared key (hex)")
    ap.add_argument("--log", default=DEFAULT_LOG_PATH,
                    help="audit log path")
    ap.add_argument("--no-su", action="store_true",
                    help="never use `su -c`; run commands directly "
                         "(only safe when already root, useful for tests)")
    ap.add_argument("--no-tailnet-check", action="store_true",
                    help="disable the tailnet CIDR source-IP check "
                         "(useful when the daemon is bound directly to "
                         "the Tailscale tunnel IP)")
    return ap.parse_args()


def main() -> int:
    args = _parse_args()

    if not args.host:
        sys.stderr.write(
            "shellrd: --host is required (the IP to bind to). "
            "Pick a Tailscale tunnel IP like 100.x.y.z, not 0.0.0.0.\n"
            "  e.g. --host 100.111.121.72\n"
        )
        return 2
    if args.host in ("0.0.0.0", "") and not args.no_tailnet_check:
        sys.stderr.write(
            "shellrd: refusing to bind to 0.0.0.0 without --no-tailnet-check\n"
            "  bind to a specific Tailscale tunnel IP instead\n"
        )
        return 2

    server = build_server(
        host=args.host,
        port=args.port,
        secret_path=args.secret,
        log_path=args.log,
        use_su=not args.no_su,
        check_tailnet=not args.no_tailnet_check,
    )
    return run_server(server)


if __name__ == "__main__":
    sys.exit(main())
