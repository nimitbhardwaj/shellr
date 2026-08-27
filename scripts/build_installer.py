"""Build the single-file self-extracting shellr installer.

Run from the repo root: ``python scripts/build_installer.py``.
Produces ``share/phone/install.sh`` — a single shell script that
bundles the entire daemon source inline, plus the service.d
autostart, plus the install choreography.

After running, ``share/phone/install.sh`` is a hermetic installer
you can give to a fresh Android device.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DAEMON_MOD = ROOT / "src" / "shellr" / "daemon"
INSTALLER_OUT = ROOT / "share" / "phone" / "install.sh"


def _read_modules() -> list[tuple[str, str, str]]:
    """Return (display_name, path, content) for each daemon module.

    Files are read in import order so the monolith's imports resolve.
    Modules don't actually ``import`` anything at runtime — the
    server module embeds all the helpers — so order is presentation
    only, but it's nicer to read top-down.

    NOTE: shellr.crypto and shellr.resolve are top-level modules in
    src/shellr/ (sibling of shellr.daemon), and daemon/__init__.py
    imports from them. They must be included in the monolith OR the
    `from shellr.crypto import verify` line will fail with
    ModuleNotFoundError. We include them as separate sections so
    the daemon is fully self-contained.
    """
    # Order matters: dependencies first, then consumers.
    # Toplevel utility modules first, then daemon.
    files = [
        "../crypto.py",         # shellr.crypto (imported by daemon/__init__.py)
        "../resolve.py",         # shellr.resolve (imported by daemon)
        "config.py",            # shellr.daemon.config
        "logging.py",           # shellr.daemon.logging
        "exec.py",              # shellr.daemon.exec
        "server.py",            # shellr.daemon.server
        "__init__.py",          # shellr.daemon (main, has imports)
    ]
    out = []
    for fn in files:
        p = (DAEMON_MOD / fn).resolve()
        out.append((fn, str(p), p.read_text(encoding="utf-8")))
    return out


def _make_monolith() -> str:
    """Stitch daemon modules into a single self-contained Python file.

    Strategy:
    - Files are concatenated in order.
    - The `from shellr.daemon.X import ...` imports at the top of
      ``__init__.py`` are stripped; in the monolith all top-level
      defs live in one module namespace already.
    - Section banners separate the source of each file for grepability.
    """
    parts = [
        '#!/data/data/com.termux/files/usr/bin/python3\n',
        '"""shellrd — bundled as a single self-contained file.\n\n',
        'Auto-generated from src/shellr/daemon/*.py by\n',
        'scripts/build_installer.py. Do not edit by hand; edit the\n',
        'source modules and rerun the builder.\n',
        '"""\n\n',
        'import argparse\n',
        'import base64\n',
        'import hashlib\n',
        'import hmac\n',
        'import ipaddress\n',
        'import json\n',
        'import logging\n',
        'import os\n',
        'import shutil\n',
        'import socket\n',
        'import subprocess\n',
        'import sys\n',
        'import time\n',
        'from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer\n',
        'from pathlib import Path\n\n',
        '# Shellr version\n',
        '__version__ = "0.2.0"\n\n',
    ]

    for fn, path, content in _read_modules():
        parts.append(f"\n# ======= {fn} =======\n")
        # Strip the `from __future__ import annotations` line (only allowed
        # at top of a module).
        cleaned = content.replace("from __future__ import annotations\n", "")
        # Strip `from shellr.daemon.X import ...` lines — these are
        # cross-module references inside the daemon package; in the
        # monolith all symbols live in one namespace.
        # IMPORTANT: match optional leading whitespace (4 spaces for
        # function-body imports like `from shellr.daemon.logging import
        # setup_logging` that lives inside build_server()).
        cleaned = re.sub(
            r"^[ \t]*from shellr\.daemon\.[a-z_]+ import \(\n"
            r"(?:[ \t]*[\w_,\n]+)+"
            r"[ \t]*\)\n",
            "",
            cleaned,
            flags=re.MULTILINE,
        )
        # And the single-line variant.
        cleaned = re.sub(
            r"^[ \t]*from shellr\.daemon\.[a-z_]+ import [^\n]+\n",
            "",
            cleaned,
            flags=re.MULTILINE,
        )
        # Also strip `from shellr.crypto import ...` and
        # `from shellr.resolve import ...` — top-level utilities
        # are bundled at the top of the monolith, so their symbols
        # are already in scope. Same indentation handling.
        cleaned = re.sub(
            r"^[ \t]*from shellr\.(crypto|resolve) import [^\n]+\n",
            "",
            cleaned,
            flags=re.MULTILINE,
        )
        # Same for `from shellr.crypto/resolve import (...)` multiline
        cleaned = re.sub(
            r"^[ \t]*from shellr\.(crypto|resolve) import \(\n"
            r"(?:[ \t]*[\w_,\n]+)+"
            r"[ \t]*\)\n",
            "",
            cleaned,
            flags=re.MULTILINE,
        )
        parts.append(cleaned)
        parts.append("\n")

    # NOTE: `from X import Y as Z` aliases used to be a problem here because
    # we stripped the imports. server.py has been refactored to use the
    # direct name (`verify` not `hmac_verify`), so no alias re-injection
    # is needed. If a future refactor reintroduces `as`-aliases inside
    # function bodies, add them here.

    return "".join(parts)


def _build_installer() -> str:
    """Build the installer shell script with the daemon bundled inside."""
    template = INSTERPLATE = (
        HERE / "_install_template.sh"
    ).read_text(encoding="utf-8")
    monolith = _make_monolith()
    # Replace the DAEMON_HEREDOC_PLACEHOLDER marker with the monolith.
    return INSTERPLATE.replace("DAEMON_HEREDOC_PLACEHOLDER", monolith)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=INSTALLER_OUT)
    ap.add_argument("--check", action="store_true",
                    help="only check the template exists, don't write")
    args = ap.parse_args()

    template_path = HERE / "_install_template.sh"
    if not template_path.exists():
        print(f"missing template: {template_path}", file=sys.stderr)
        return 1

    if args.check:
        print(f"template: {template_path}")
        return 0

    out = _build_installer()
    args.out.write_text(out, encoding="utf-8")
    args.out.chmod(0o755)

    # Sanity check: bash syntax + size
    r = subprocess.run(
        ["bash", "-n", str(args.out)], capture_output=True, text=True,
    )
    if r.returncode:
        print(f"bash syntax error:\n{r.stderr}", file=sys.stderr)
        return 1

    print(f"wrote {args.out} ({args.out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
