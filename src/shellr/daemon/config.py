"""Daemon configuration — defaults, paths, security policy.

Override on the command line via ``--host``, ``--port``, ``--secret``,
``--log``, ``--no-su``, ``--no-tailnet-check``.
"""

from __future__ import annotations

# Bind defaults — refuse to start without an explicit --host.
DEFAULT_HOST: str | None = None
DEFAULT_PORT: int = 7777
DEFAULT_SECRET_PATH: str = "/data/adb/shellrd/.shellr_secret"
DEFAULT_LOG_PATH: str = "/sdcard/shellr.log"
DEFAULT_TIMEOUT: int = 30

# Output caps
MAX_OUTPUT_BYTES: int = 256 * 1024     # 256 KiB cap on shell stdout/stderr
MAX_REQUEST_BYTES: int = 1_048_576     # 1 MiB cap on request body
MAX_FILE_READ_BYTES: int = 1_048_576   # 1 MiB cap on a single read

# Tailscale IPv4 CIDR — only accept connections from this range.
# Defence-in-depth on top of HMAC. The boot script passes
# --no-tailnet-check because it binds the daemon directly to a
# Tailscale tunnel IP, so only tunnel traffic can reach it.
TAILNET_CIDR: str | None = "100.64.0.0/10"

# File ops whitelist: paths under these roots are allowed.
# /data/adb/shellrd is the canonical home on rooted phones; we also
# keep legacy /data/local/tmp/shellrd for backward compatibility with
# installs that pre-date the migration.
ALLOWED_ROOTS: tuple[str, ...] = (
    "/data/adb/shellrd",
    "/data/local/tmp/shellrd",
    "/sdcard",
    "/data/local/tmp",
)

# Command patterns to refuse even with root. These are not a sandbox —
# root is root — but they stop stupid copy-paste typos from taking out
# the device.
DESTRUCTIVE_PATTERNS: tuple[str, ...] = (
    "rm -rf /",
    "mkfs",
    "dd if=/dev/zero of=/dev/",
)
