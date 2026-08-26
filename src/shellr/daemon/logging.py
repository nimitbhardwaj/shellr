"""Daemon logging — append-only audit trail.

Every RPC call is logged with: timestamp, method, source IP, duration,
error (if any). Logs go to a file (append, no fsync loop) and stderr
(visible in the calling shell).
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

LOG_FORMAT = "%(asctime)s %(levelname)-5s %(message)s"
DATE_FORMAT = "%Y-%m-%dT%H:%M:%S%z"


def setup_logging(log_path: str) -> logging.Logger:
    """Configure the ``shellrd`` logger: stderr + append-only file."""
    log = logging.getLogger("shellrd")
    log.setLevel(logging.INFO)
    # Avoid duplicate handlers on reload
    log.handlers.clear()

    fmt = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(fmt)
    log.addHandler(sh)

    try:
        fh = logging.FileHandler(log_path, mode="a", encoding="utf-8")
        fh.setFormatter(fmt)
        log.addHandler(fh)
    except OSError as exc:
        # /sdcard may not be mounted in every boot context — fall back
        # to a tmpfs path so we still have a trail.
        fallback = "/data/local/tmp/shellr.log"
        fh = logging.FileHandler(fallback, mode="a", encoding="utf-8")
        fh.setFormatter(fmt)
        log.addHandler(fh)
        log.warning("could not open %s (%s); logging to %s instead",
                    log_path, exc, fallback)

    return log
