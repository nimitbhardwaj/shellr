# shellr — root-controlled Android phone from a VPS over Tailscale

> HMAC-signed JSON-RPC over Tailscale. Zero APK installs. Kernel-resident
> autostart. Battery-efficient (idle = zero CPU). Full root access from
> any machine on the same tailnet.

```
VPS ──── HMAC-signed RPC over Tailscale ──── phone (root)
                                                │
                                                ▼
                                       /data/local/tmp/shellrd/shellrd.py
                                       └─ bound to 100.x.y.z:7777
                                       └─ autostart via KernelSU service.d
```

## What you get

| Capability | From your VPS |
|---|---|
| Run any shell command on the phone as root | `shellr shell 'uptime; whoami'` |
| Read/Write/List files (whitelisted paths) | `shellr read /sdcard/foo.txt` |
| Post a notification to the phone | `shellr notify 'Mom' 'Dinner at 8'` |
| Phone info (uid, kernel, tailnet IP, …) | `shellr info` |
| Tailscale IP discovery | `shellr --resolve` |
| Interactive REPL | `shellr repl` |

## Architecture in 30 seconds

- **Daemon** (`src/shellr/daemon/`) — runs on the phone, rooted. Pure stdlib
  Python. Listens on the Tailscale tunnel IP only. Verifies HMAC on every
  request. Refuses destructive commands and writes outside the whitelist.
- **Client** (`src/shellr/client.py`) — runs anywhere on the tailnet.
  Auto-resolves the phone's Tailscale IP. Signs every request with your
  shared secret. Returns the daemon's result.
- **Autostart** (`share/boot/service.d-shellrd.sh`) — KernelSU's `service.d`
  fires this at every boot, as root. Discovers the current tunnel IP from
  `tun0`, falls back to cache, starts the daemon. If your Tailscale IP
  ever changes, re-run this script (or reboot).
- **CLI** (`src/shellr/cli/main.py`) — thin argparse wrapper around the
  client. `shellr shell …`, `shellr notify …`, etc.

## Install

### VPS (anywhere on the tailnet)

```bash
git clone <repo> ~/Programs/shellr
cd ~/Programs/shellr
./scripts/install.sh vps          # editable pip install into .venv
.venv/bin/shellr --version
```

This installs two console scripts: `shellr` (the client) and `shellrd`
(the daemon). For development, prefer `pip install -e ".[dev]"` to pull
pytest too.

### Phone (run in Termux, after `adb push` of the repo)

```bash
# Make sure the daemon source is on the phone
scp <vps>:/path/to/shellr/src/shellr/daemon/__init__.py \
    /data/local/tmp/shellrd/shellrd.py

# Run the phone-side installer (in Termux)
bash /path/to/shellr/share/phone/install.sh
```

The phone-side installer:
1. Verifies `/data/local/tmp/shellrd/shellrd.py` exists
2. Generates `/data/local/tmp/shellrd/.shellr_secret` if missing
   (and tells you to copy it to your VPS at `~/.shellr_secret`)
3. Drops `/data/adb/service.d/shellrd.sh` for boot autostart
4. Starts the daemon now

### Required on the phone

- **Rooted Android** (KernelSU or Magisk). The daemon runs as uid 0.
- **Termux** installed (just for the `python3` binary at
  `/data/data/com.termux/files/usr/bin/python3`). The daemon itself
  does not depend on Termux:boot or any other Termux app — only the
  Python interpreter.
- **Tailscale** for Android (for the tunnel IP).

## Usage examples

```bash
# Verify connectivity
shellr --resolve                 # → 100.111.121.72
shellr ping                      # → { pong: true, uid: 0, ... }
shellr health                    # → "ok"

# Run commands as root
shellr shell 'uptime; whoami; uname -a'
shellr shell 'pm list packages | wc -l'      # → 256
shellr shell 'dumpsys battery | grep level' # → level: 100

# File ops (only under ALLOWED_ROOTS = /data/local/tmp/shellrd, /sdcard)
shellr list /sdcard
shellr read /sdcard/shellr.log
echo "hello from VPS" | shellr write /sdcard/from-vps.txt -

# Notifications
shellr notify 'Server down' 'api.weavee.in returned 502'

# Interactive
shellr repl
shellr> shell cat /proc/cpuinfo | head -5
shellr> info
shellr> exit
```

## Security model

| Layer | Defence |
|---|---|
| Network | Daemon binds to **only the Tailscale tunnel IP** (e.g. `100.111.121.72`). No `0.0.0.0`. Optional tailnet-CIDR filter on top. |
| Auth | Every request is `HMAC-SHA256(secret, body)`. Constant-time compare. Missing/bad sig → 401. |
| Secret | Lives in `chmod 600` files on both sides. Daemon **refuses to start** if permissions are looser. |
| Files | Read/Write/List only under `/data/local/tmp/shellrd`, `/sdcard`, `/data/local/tmp`. Path traversal blocked by `Path.resolve()`. |
| Shell | Refuses obvious destructive patterns (`rm -rf /`, `mkfs`, `dd if=/dev/zero of=/dev/`). Timeout default 30s. Output cap 256 KiB. |
| Audit | Every RPC logged: method, source IP, duration, error. Goes to stderr + `/sdcard/shellr.log`. |

> ⚠️ This is a power tool, not a sandbox. The HMAC stops strangers; it
> doesn't stop you from typing `pm uninstall --user 0 com.android.systemui`.
> Use with judgement.

## Repo layout

```
pyproject.toml                  build + entry points (shellr, shellrd)
README.md
src/shellr/
  __init__.py                   public API: ShellrClient, resolve_tailscale_ip
  client.py                     HMAC-signing RPC client
  crypto.py                     HMAC sign/verify
  resolve.py                    Tailscale IP discovery (DNS → status json → cli)
  cli/
    main.py                     argparse, subcommands
    repl.py                     interactive REPL
  daemon/
    __init__.py                 entry point (run as `python -m shellr.daemon`)
    config.py                   defaults, ALLOWED_ROOTS, DESTRUCTIVE_PATTERNS
    exec.py                     run_shell, file_read/write/list, dispatch
    server.py                   HTTP handler + ThreadingHTTPServer
    logging.py                  append-only audit trail

share/
  boot/service.d-shellrd.sh     KernelSU autostart (idempotent, IP-aware)
  phone/install.sh              phone-side installer (run in Termux)

tests/
  test_crypto.py                HMAC sign/verify
  test_config.py                config defaults, allowed roots
  test_resolve.py               Tailscale IP discovery (mocked)
  test_client.py                ShellrClient with mocked HTTP
  test_smoke.py                 end-to-end: real daemon + real HTTP

scripts/
  install.sh                    one-shot VPS / phone installer wrapper
```

## Testing

```bash
.venv/bin/pytest tests/        # 17 tests, ~2s
.venv/bin/pytest -v            # verbose
```

The smoke test boots a real daemon on a free port and exercises every
RPC. No external network needed; no phone needed.

## Development

```bash
# From a fresh clone
cd ~/Programs/shellr
./scripts/install.sh vps
. .venv/bin/activate
pytest -v

# Edit the daemon — it's run as a module
python -m shellr.daemon --host 127.0.0.1 --port 7799 \
    --secret /tmp/sec --no-su --no-tailnet-check

# Edit the client / CLI
shellr --help
```

## Future ideas

- **`shellr bt-scan`** — active Bluetooth discovery
- **`shellr netscan`** — quick WiFi subnet enumeration
- **`shellr snapshot`** — trigger a camera intent, fetch the photo back
- **`shellr apps`** — list installed apps with size + permissions
- **`shellr storage`** — disk usage breakdown

## License

MIT.
