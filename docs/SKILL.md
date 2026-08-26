## Note — this skill describes the daemon + protocol; for the VPS-side
## Python package source see `src/shellr/` and `pyproject.toml`.

---
name: shellr-phone-control
description: "Hermes skill — drive the rooted Android phone (nimits-a51) via the shellr daemon over Tailscale. Use when the user wants to run shell commands, read/write/list files, query sensors, or take actions on nimits-a51 from the VPS. Triggers: 'nimits-a51', 'shellr', 'phone shell', 'phone exec', 'phone ping', 'phone info', 'run on phone', 'remote shell on phone'."
version: 1.1.0
author: Hermes Agent
license: MIT
platforms: [linux, hermes]
metadata:
  hermes:
    tags: [android, phone, shellr, nimits-a51, tailscale, daemon, rooted, sensors, kernelsu]
    category: devops
when_to_use: |
  Whenever the user asks to control, query, or take an action on the
  nimits-a51 Android phone. The shellr daemon (Python, running as root
  on the phone under /data/local/tmp/shellrd/, autostarted by
  KernelSU service.d, bound to the Tailscale tunnel IP like
  100.111.121.72:7777, HMAC-signed) is the entry point.

  Triggers: 'phone', 'on the phone', 'nimits-a51', 'shellr', 'phone
  shell', 'phone exec', 'phone info', 'phone battery', 'run on
  nimits-a51', 'what's my phone doing', 'phone status'.

  Do NOT load for: scanning other devices, running this against a
  phone you don't own, or anything that would extend this past the
  user's own rooted phone (the rooted-android-llm-gateway skill has
  the scope guardrail for that).
---

# shellr — phone control from the VPS

The shellr daemon runs on `nimits-a51` (100.111.121.72 over Tailscale).
Hermes on the VPS is the brain; the phone is the hands. This skill
teaches Hermes the conventions, the safety guardrails, and the common
command recipes.

## TL;DR — first 30 seconds

```bash
# Confirm daemon is alive
shellr ping
# or, from Python in any tool:
python3 -c "from shellr import ShellrClient; print(ShellrClient().ping())"
```

If `shellr: command not found`, see "Install" below.

If `ping` returns an error, see "Troubleshooting" below.

## Endpoints (RPC methods)

All requests are `POST /` with body `{"method": "...", "params": {...}}`,
HMAC-SHA256 signed in `X-Shellr-Signature`.

| Method | Params | Returns | Notes |
|---|---|---|---|
| `ping` | — | `{pong, ts, uid, euid, host, uptime_s}` | fastest health check |
| `info` | — | `{host, kernel, android_sdk, termux, uid, euid, tailscale_ip}` | static snapshot |
| `shell` | `{command, timeout?}` | `{ok, stdout, stderr, code, duration_ms, timed_out, truncated}` | runs as root via `/system/bin/sh -c` (no su indirection — daemon itself is uid 0) |
| `read` | `{path, max_bytes?}` | `{path, size, truncated, content_b64}` | whitelist-checked |
| `write` | `{path, content_b64, mode?}` | `{path, size}` | whitelist-checked |
| `list` | `{path}` | `{path, entries: [{name, is_dir, size, mtime}]}` | whitelist-checked |

**Default timeout:** 30 s. Cap: 300 s.

**Allowed file roots** (everything outside is rejected):
- `/data/local/tmp/shellrd` (daemon home, holds `.shellr_secret`, `shellrd.py`, python runtime)
- `/sdcard`
- `/data/local/tmp`

**Bind address:** the daemon listens ONLY on the phone's Tailscale
tunnel IP (e.g. `100.111.121.72`). **Never `0.0.0.0`** — even with
the tailnet-CIDR source filter enabled, binding 0.0.0.0 exposes
port 7777 to LAN/cellular scanners (WiFi networks, neighbours, anyone
who can reach the device on its physical interface). The HMAC +
filter would refuse them, but the port should not be visible at all.
Bind the specific tunnel IP and let the autostart handle IP changes.

The KernelSU autostart (`/data/adb/service.d/shellrd.sh`) discovers the
current IP at boot from `ip -4 addr show tun0`, caches it to
`/data/local/tmp/shellrd/.last_ip`, and falls back to that cache or
a hardcoded IP if the tunnel isn't up yet. If Tailscale ever re-IPs
the phone, just rerun `/data/adb/service.d/shellrd.sh` to refresh.

If the daemon is unreachable: check the phone's current IP with
`ip -4 addr show tun0` and re-run the autostart. See
`references/kernelsu-autostart-recipe.md` for the full recipe.

## Standard recipes — copy these

### Battery / power

```bash
shellr shell 'dumpsys battery | head -20'
shellr shell 'cat /sys/class/power_supply/battery/capacity'
shellr shell 'settings get global low_power'
```

### Networking

```bash
shellr shell 'ip addr show wlan0 | grep inet'        # phone's Tailscale/LAN IP
shellr shell 'dumpsys connectivity | head -50'        # current network state
shellr shell 'dumpsys wifi | grep -A2 "Wi-Fi is"'    # SSID
shellr shell 'settings get global airplane_mode_on'
```

### Storage / apps

```bash
shellr shell 'df -h /sdcard /data'
shellr shell 'pm list packages -3'                    # user apps only
shellr shell 'dumpsys meminfo | head -30'             # RAM state
```

### Sensors

```bash
shellr shell 'dumpsys sensorservice | head -40'      # available sensors
# location — needs termux-location installed
shellr shell 'termux-location'
```

### System / package management

```bash
shellr shell 'pm list packages'                       # all packages
shellr shell 'pm path com.android.chrome'             # find APK path
shellr shell 'dumpsys package com.android.chrome | grep versionName'
shellr shell 'logcat -d -t 100 *:E'                   # recent errors
shellr shell 'getprop ro.build.version.release'       # Android version
```

### File ops

```bash
# write a file
shellr write /sdcard/Download/hello.txt 'hello from VPS'

# read a file
shellr shell 'cat /sdcard/Download/hello.txt'

# list a directory
shellr shell 'ls -la /sdcard/Download/'

# (read/write/list RPC methods exist too — use those for binary data)
```

### Termux-side scripts

```bash
# run a multi-line script via heredoc
shellr shell 'bash -s' <<'EOF'
set -e
cd /sdcard
echo "files: $(ls | wc -l)"
df -h /sdcard | tail -1
EOF
```

## Safety guardrails

These are non-negotiable — the daemon runs as root.

1. **Always confirm before destructive ops.** Show the user the exact
   command. Wait for explicit confirmation before:
   - `pm uninstall`, `pm clear`, `am force-stop`
   - `rm -rf`, `mv /sdcard/X /dev/null`, etc.
   - `settings put`, `setprop`
   - `iptables`, `ip route`, anything that changes networking
   - flashing / writing to /system, /vendor, /boot, recovery

2. **Pre-exec pattern block.** The daemon refuses any command matching
   `rm -rf /`, `mkfs`, or `dd if=/dev/zero of=/dev/`. Don't try to
   bypass it.

3. **File whitelist.** Reads/writes outside Termux-home, /sdcard, and
   /data/local/tmp are rejected by the daemon. If the user asks for
   /system/etc/hosts, stop and confirm — that's a system mutation.

4. **Timeout everything.** Pass `timeout` explicitly for anything that
   could hang: `shellr shell 'long-cmd', 60` or use `timeout 30 cmd`
   inside the command.

5. **No secrets in logs.** The daemon logs every method call. Avoid
   putting API keys, passwords, or personal data into commands.

## Phone-pushed state (Pattern B — proactive)

If the user wants the LLM to monitor and react to phone state, the
phone can push a state JSON to the VPS. The daemon supports `ping` for
on-demand; for proactive push, the phone needs a `cron` or a recurring
`shellr shell` from the phone side (separate `shellr-ping` script).

A scheduled Hermes cron job that polls phone state every N minutes is
the simpler path. See `~/.hermes/cron/` for examples.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `shellr: command not found` (VPS) | `~/.local/bin` not on PATH | `echo 'export PATH=$HOME/.local/bin:$PATH' >> ~/.bashrc && source ~/.bashrc` |
| `connection refused` on 7777 | daemon not running on phone | run `/data/adb/service.d/shellrd.sh` from ADB shell — it waits for Tailscale then starts daemon |
| `401 bad signature` | secret mismatch between phone and VPS | `cat /data/local/tmp/shellrd/.shellr_secret` on phone, `cat ~/.shellr_secret` on VPS, diff them |
| `HMAC mismatch from ...` in `/sdcard/shellr.log` | wrong secret OR clock skew | check `date` on both ends |
| `Read timed out` | command genuinely hung OR phone went to sleep | raise timeout; check phone battery |
| `could not resolve Tailscale IP for nimits-a51` (VPS) | VPS not on the tailnet | `tailscale up` on the VPS; or pass `--phone-ip 100.111.121.72` |
| `shellrd.py: error: the following arguments are required: --host` | older daemon missing `--host` arg | sync the latest daemon: `scp`/`adb push`/`write RPC` the current VPS daemon over and restart |
| `shellrd.py: error: unrecognized arguments: --no-tailnet-check` | older daemon doesn't have this flag | same fix — sync current daemon |
| Daemon dies hours after boot | Android killed it for battery | Settings → Apps → Termux → Battery → Unrestricted (KernelSU service.d itself survives reboot, so the daemon respawns on next boot) |

## Termux gotchas (load these into any future Android/Termux build)

Three things bite **every** Android/Termux daemon script. They are
not bugs in your code — they are how Android shells work. Future
sessions writing Android/Termux tools should bake them in from day
one. Full transcripts and reproduction notes are in
`references/termux-gotchas.md`.

1. **Termux default `sh` is mksh, not bash.** `set -o pipefail`,
   `[[ ... ]]`, `local`, and process substitution all fail. Always
   use bash explicitly:
   `#!/data/data/com.termux/files/usr/bin/bash` (absolute path —
   `/usr/bin/env bash` works if `bash` is installed but the absolute
   path is bulletproof).

2. **`su -c` strips `$PATH`.** Even if `python3` is on the user's
   PATH inside Termux, the moment you wrap a command in `su -c '...'`
   to run it as root, the root shell has a sparse PATH and won't
   find anything in `/data/data/com.termux/files/usr/bin`. Always use
   absolute paths to Termux binaries in any `su -c` invocation:
   `/data/data/com.termux/files/usr/bin/python3`, `/data/data/com.termux/files/usr/bin/bash`,
   `/data/data/com.termux/files/usr/bin/termux-wake-lock`. The same
   applies to `~/.termux/boot/*.sh` autostart scripts that call
   `su -c`.

3. **`set -e` + idempotent operations = silent death.** A `cp -f`
   that detects "source and destination are the same file" exits
   non-zero, which `set -e` turns into a script abort. The proper
   defense is to make install scripts conditional (e.g. "only copy
   if `$1` was passed and is a different file") rather than
   unconditional. Always read the script's error carefully — `set -e`
   aborts on the FIRST non-zero exit, so the line that printed the
   error is the line to fix.

## Audit trail

- Phone-side: `/sdcard/shellr.log` (every RPC, every exec, every read/write)
- Server-side: `~/.local/share/shellr/shellr.log` (every call from the VPS)

When investigating an incident or explaining to the user what the LLM
just did on the phone, both logs are the source of truth.

## Daemon restart: use ADB, not the shell RPC

The `shellr shell '...'` RPC runs **inside** the daemon's Python
process on the phone. If you ask it to kill the daemon, the
in-flight RPC dies too — and any `nohup ... &` you spawn from
within that RPC runs in a dead context and never starts a new
daemon. Result: daemon is dead, no new daemon is running, every
subsequent RPC fails with "Connection refused", and you're stuck
until the user restarts it manually.

**Pattern:**

```text
# GOOD — restart via ADB (separate process from daemon)
shellr shell 'pkill -f shellrd.py'         # daemon dies here, RPC fails. STOP.
# Tell the user to run on the phone:
/data/adb/service.d/shellrd.sh

# BAD — restart from inside the RPC
shellr shell 'pkill -f shellrd.py; sleep 1; nohup python3 ... &'
# pkill succeeds, but the nohup runs in dead context → no daemon
# → next RPC fails → user is stuck
```

The autostart script is idempotent — re-running it after a daemon
crash does the right thing (waits for tunnel, starts daemon,
verifies via `pgrep`). Re-run via ADB or `/data/adb/service.d/shellrd.sh`
on the phone, never from a VPS-side RPC.

## Companion skill

For the broader LLM-driven optimization loops (battery, bloatware
removal, network defense, pattern learning), load the
`rooted-android-llm-gateway` skill — it has the recipes, the math,
and the scope guardrail.

## Deployment pattern (the root-only architecture)

The current production setup is **fully root-driven, no Termux-as-a-shell
dependency**. Only the python runtime still comes from Termux's install
(its binary + stdlib). This is what worked after a session-long iteration
from a Termux-only design. Future sessions building similar daemons
should start here, not regress to Termux.

### Layout

```
/data/local/tmp/shellrd/                 # daemon home, root:root, chmod 755
├── shellrd.py                            # the daemon (chmod 700)
├── .shellr_secret                        # HMAC key (chmod 600)
├── .last_ip                              # last-known Tailscale tunnel IP (chmod 644)
├── python/                               # self-contained python runtime
│   ├── bin/python3                       # ~4.7KB wrapper, links to libs
│   └── lib/
│       ├── libpython3.13.so              # 5.1MB
│       └── libandroid-posix-semaphore.so # Termux's POSIX shim, 7KB
└── test-from-vps.txt                     # ad-hoc test artifact, can delete

/data/adb/service.d/shellrd.sh            # KernelSU autostart (chmod 755)
                                          # runs as root at every boot, after /data
```

### Why this layout (decision log)

- **`/data/local/tmp/`** is world-writable but on this Android it's
  effectively root-owned (no other process writes there). Survives
  reboots. **Not** wiped by Android's "clear cache" button the way
  `/data/data/<app>/cache` would be.
- **KernelSU `service.d/`** runs every script in that directory at
  boot as root, after `/data` is mounted, before userland is up.
  Same idea as Magisk's `service.d/` — KernelSU copied that
  convention. Path: `/data/adb/service.d/*.sh`, scripts run in
  alphabetical order. Battery cost: scripts run once and exit.
- **No Termux:boot dependency.** The whole "Termux:boot from F-Droid"
  dance is gone — KernelSU's service.d is built into the root solution.
- **No `su -c` indirection.** Daemon runs as root itself, executes
  commands via plain `/system/bin/sh -c`. Cleaner code, faster exec,
  simpler reasoning.

### Python isolation

Termux's python binary works fine as a runtime, but its install lives
under `/data/data/com.termux/files/usr/` (Termux app's private dir).
If you ever uninstall the Termux app, the runtime disappears.

To survive that, copy Termux's python binary + two needed libs to
`/data/local/tmp/shellrd/python/`:

```bash
mkdir -p /data/local/tmp/shellrd/python/{bin,lib}
cp /data/data/com.termux/files/usr/bin/python3 \
   /data/local/tmp/shellrd/python/bin/
cp /data/data/com.termux/files/usr/lib/libpython3.13.so \
   /data/local/tmp/shellrd/python/lib/
cp /data/data/com.termux/files/usr/lib/libandroid-posix-semaphore.so \
   /data/local/tmp/shellrd/python/lib/
chmod 755 /data/local/tmp/shellrd/python/bin/python3
chmod 644 /data/local/tmp/shellrd/python/lib/*.so
```

Then set `PYTHONHOME=/data/data/com.termux/files/usr` at launch so
the stdlib still resolves. (Future work: copy the 40MB stdlib too
for full Termux independence — see
`references/kernelsu-autostart-recipe.md` for the full pattern.)

### Why this layout (decision log) — continued

**Why `PYTHONHOME` instead of copying the 40 MB stdlib too?**

Trade-off: copying gives full Termux independence (clean
abstraction), staying with PYTHONHOME keeps the install lean
(~5 MB on the phone vs ~50 MB). For most use cases the lean
install wins — Termux isn't going anywhere, the stdlib
**will** get out of sync if we copy it and forget to update it,
and the cost of a 50 MB folder under `/data/local/tmp/` is
nontrivial on phones with limited internal storage.

If you ever do want full isolation, the copy is mechanical:

```bash
cp -r /data/data/com.termux/files/usr/lib/python3.13 \
      /data/local/tmp/shellrd/python/lib/
# Then remove PYTHONHOME_TERMUX from the autostart.
```

### KernelSU service.d autostart (resilient + battery-tuned)

The autostart script waits up to 5 minutes for the Tailscale tunnel,
then starts the daemon. Poll interval is 5 seconds, so the boot-window
battery cost is negligible (~60 wakeups × ~50ms CPU = ~3 seconds
total over 5 minutes, a few mA). After daemon starts, script exits;
daemon sleeps on kernel epoll.

Full script and the reasoning are in
`references/kernelsu-autostart-recipe.md`.

### Syncing the daemon from VPS (no scp, no adb push needed)

When you update `shellrd.py` on the VPS, push it to the phone using
the running daemon's own `write` RPC — base64-encode the new content,
POST it to `/write` with the destination path, then `chmod 700` over
`shell`:

```python
# VPS side (Python, from a cron job, from a skill, from a session)
import base64, requests, hmac, hashlib
SECRET = open("/home/hermes/.shellr_secret", "rb").read().strip()
PHONE = "100.111.121.72"

src = open("/home/hermes/Programs/shellr/src/shellr/daemon/__init__.py (or .py if running as single-file)", "rb").read()
body = json.dumps({"method": "write", "params": {
    "path": "/data/local/tmp/shellrd/shellrd.py",
    "content_b64": base64.b64encode(src).decode(),
}}).encode()
sig = hmac.new(SECRET, body, hashlib.sha256).hexdigest()
r = requests.post(f"http://{PHONE}:7777/", data=body,
                  headers={"X-Shellr-Signature": sig}, timeout=10)
print(r.json())  # → {"ok": true, "result": {"size": 19256}}
```

Why this matters: it works **through chat-mediated sessions** where
you can't run `adb push` or `scp`. The user only has to type something
like "sync the daemon" and the LLM can do it from the VPS. It also
survives without Termux SSH (which is off by default on phones).

After pushing, restart via ADB:

```bash
adb shell pkill -f shellrd.py
adb shell /data/adb/service.d/shellrd.sh
```

## Communication legibility (chat-mediated deploys)

When sending commands to the user through Telegram, Discord, Slack, or
any other chat that mangles multi-line content, **don't wrap multi-line
scripts in `cat <<EOF ... EOF` heredocs** — chat clients often collapse
them, garble the EOF marker, or render the wrapper as dead text. Use
plain fenced code blocks with one command per line, or send the
**base64-encoded** content via the daemon's own write RPC (see above).

```text
# DO send this:
echo '#!/system/bin/sh' > /data/adb/service.d/shellrd.sh
echo 'sleep 5' >> /data/adb/service.d/shellrd.sh
echo 'ip -4 addr show tun0' >> /data/adb/service.d/shellrd.sh
chmod +x /data/adb/service.d/shellrd.sh

# DON'T send this:
cat <<EOF > /data/adb/service.d/shellrd.sh
#!/system/bin/sh
sleep 5
ip -4 addr show tun0
EOF
```

The shell-wrapper version is unreadable in chat and prone to having
the EOF marker swallowed or the variables expanded. The plain-block
version is paste-ready and survives any chat client.

For more chat-specific failure modes (user types "next" instead of
pasting output, in-flight RPC dies with the daemon on restart, etc.)
see `references/chat-deploy-gotchas.md`.
