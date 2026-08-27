---
name: shellr-phone-control
description: "Hermes skill — drive a rooted Android phone via the shellr daemon over Tailscale. Use when the user wants to run shell commands, read/write/list files, query Bluetooth/WiFi/battery/sensors, post notifications, or take any action on a rooted phone from a remote machine. Triggers: 'phone shell', 'phone exec', 'phone info', 'phone battery', 'phone bluetooth', 'phone bluetooth scan', 'phone wifi', 'phone battery', 'run on phone', 'remote shell on phone', 'send notification to phone', 'reboot phone', 'take photo on phone'."
version: 1.2.0
author: Hermes Agent
license: MIT
platforms: [linux, hermes]
metadata:
  hermes:
    tags: [android, phone, shellr, tailscale, daemon, rooted, sensors, kernelsu, bluetooth, wifi, notifications, network-scan]
    category: devops
when_to_use: |
  Whenever the user asks to control, query, or take an action on a
  rooted Android phone connected over Tailscale. The shellr daemon
  (Python, running as root, autostarted by KernelSU service.d, bound
  to the Tailscale tunnel IP like 100.x.y.z:7777, HMAC-signed) is
  the entry point.

  Triggers: 'phone', 'on the phone', 'shellr shell ...', 'phone
  info', 'phone battery', 'phone bluetooth', 'phone wifi', 'send
  notification to phone', 'phone camera', 'phone sensors', 'what's
  my phone doing', 'phone status'.

  Do NOT load for: scanning networks/devices the user doesn't own,
  running against an unrooted or unknown phone, or anything that
  would extend this past the user's own authenticated phone.

  This skill is evolutionary — when a new capability is proved to
  work on the actual phone, add a recipe here AND push the change
  to the shellr repo (docs/SKILL.md) so other users benefit.
---

# shellr — phone control from a remote machine

The shellr daemon runs on the rooted phone as a JSON-RPC HTTP server,
authenticated with HMAC-SHA256, bound to the Tailscale tunnel IP only.
Hermes on the controlling machine is the brain; the phone is the hands.
This skill teaches Hermes the conventions, safety guardrails, and
common command recipes.

## TL;DR — first 30 seconds

```bash
# Confirm daemon is alive
shellr ping

# From Python in any tool
python3 -c "from shellr import ShellrClient; print(ShellrClient().ping())"
```

If `shellr: command not found`, see **Install** below.

If `ping` returns an error, see **Troubleshooting** below.

## Phone profile (configurable)

The skill itself is **phone-agnostic** — the IP, hostname, and secret
path are pulled from the environment or a config file so other users
can install the same skill without modification. Override these:

| Setting | Default | Override |
|---|---|---|
| Phone Tailscale hostname | `<phone-hostname>` | `SHELLR_PHONE` env var or `--phone` CLI flag |
| Phone port | `7777` | `SHELLR_PORT` env var or `--port` flag |
| HMAC secret path | `~/.shellr_secret` | `SHELLR_SECRET` env var or `--secret` flag |
| Direct IP override | (auto-resolve) | `SHELLR_PHONE_IP` env var or `--phone-ip` flag |

For other users to adapt the skill, edit the table; do **not** commit
changes to phone-unique data into the public `docs/SKILL.md` — keep
that generic. The master skill in `~/.hermes/` is yours to add user-
specific recipes; the public copy stays generic.

## Endpoints (RPC methods)

All requests are `POST /` with body `{"method": "...", "params": {...}}`,
HMAC-SHA256 signed in `X-Shellr-Signature`.

| Method | Params | Returns | Notes |
|---|---|---|---|
| `ping` | — | `{pong, ts, uid, euid, host, uptime_s}` | fastest health check |
| `info` | — | `{host, kernel, android_sdk, termux, uid, euid, tailscale_ip}` | static snapshot |
| `shell` | `{command, timeout?}` | `{ok, stdout, stderr, code, duration_ms, timed_out, truncated}` | runs as root via `/system/bin/sh -c` (no `su` indirection — daemon itself is uid 0) |
| `read` | `{path, max_bytes?}` | `{path, size, truncated, content_b64}` | whitelist-checked |
| `write` | `{path, content_b64, mode?}` | `{path, size}` | whitelist-checked |
| `list` | `{path}` | `{path, entries: [{name, is_dir, size, mtime}]}` | whitelist-checked |

**Default timeout:** 30 s. **Cap:** 300 s.

**Allowed file roots** (everything outside is rejected):
- `/data/adb/shellrd` (daemon home — canonical; legacy `/data/local/tmp/shellrd` still allowed for migration grace period)
- `/sdcard`
- `/data/local/tmp`

**Bind address:** the daemon listens **only on the Tailscale tunnel IP**
(e.g. `100.x.y.z`). Never `0.0.0.0`. The HMAC + tailnet-CIDR filter
would refuse outside traffic, but the port should not even be visible.

The KernelSU autostart (`/data/adb/service.d/shellrd.sh`) discovers
the current IP at boot from `ip -4 addr show tun0` and updates the
cache. If Tailscale ever re-IPs the phone, re-run that script.

## Standard recipes — copy these

Each recipe is a working command. **Run them with the safety guardrails
below in mind.** Add new recipes here when the user asks for a new
capability and it works end-to-end. Remove ones that don't.

### Battery / power

```bash
shellr shell 'dumpsys battery | head -20'
shellr shell 'cat /sys/class/power_supply/battery/capacity'
shellr shell 'settings get global low_power'
shellr shell 'cat /sys/class/power_supply/battery/{status,health,voltage_now,temp}'
```

### WiFi / networking

```bash
shellr shell 'ip addr show wlan0 | grep inet'        # phone's LAN/Tailscale IP
shellr shell 'dumpsys connectivity | head -50'        # current network state
shellr shell 'dumpsys wifi | grep -A2 "Wi-Fi is"'    # connected SSID
shellr shell 'settings get global airplane_mode_on'

# Force a WiFi rescan (results in `cmd wifi scan-results`)
shellr shell 'cmd wifi start-scan; sleep 5; cmd wifi scan-results | head -50'

# ARP table (known devices on current WiFi)
shellr shell 'ip neigh show'
shellr shell 'cat /proc/net/arp'
```

### Bluetooth

```bash
# Full adapter state (paired devices, scan mode, BLE state)
shellr shell 'dumpsys bluetooth_manager'

# Just enable, disable, scanmode
shellr shell 'cmd bluetooth_manager enable'
shellr shell 'cmd bluetooth_manager disable'
shellr shell 'cmd bluetooth_manager 2>&1'      # only enable/disable supported

# Bonded devices only
shellr shell 'dumpsys bluetooth_manager 2>&1 | sed -n "/Bonded devices:/,/^$/p"'

# Apps with BLUETOOTH_SCAN granted (surveillance: who's actively scanning?)
shellr shell 'appops query-op BLUETOOTH_SCAN allow'
shellr shell 'appops query-op BLUETOOTH_CONNECT allow'  # who can talk to paired

# Make the phone discoverable for 30 seconds (others can SEE us, we don't see them)
shellr shell 'am broadcast -a android.bluetooth.adapter.action.REQUEST_DISCOVERABLE --ei android.bluetooth.adapter.extra.DISCOVERABLE_DURATION 30'
```

### Active BT scan (PULL nearby devices)

`cmd bluetooth_manager` does NOT support `start-discovery` on most
modern Android (Samsung's GD stack). To actively find nearby BLE/
classic devices you need **Termux:API** — see "Tools to install"
below. Without it, you can:

1. **Watch who's talking to us** (`adb logcat -d *:S Bluetooth`)
2. **Watch paired devices' last-seen in `btsnoop`** (`adb pull /data/misc/bluetooth/logs/btsnoop_hci.log` + Wireshark)

### TCP/IP scanning tools on phone

`/data/data/com.termux/files/usr/bin/nmap` (install via Termux
`pkg install nmap`) is callable as root because the daemon adds
Termux's bin dir to PATH. Useful:

```bash
shellr shell 'nmap --version'          # verify it's reachable
shellr shell 'nmap -sn 192.168.1.0/24' # device discovery on current WiFi
shellr shell 'nmap -sV -p- 192.168.1.6 2>&1' # full port scan + service detection
shellr shell 'nmap -O 192.168.1.6 2>&1' # OS detection
```

The `nmap` binary lives under Termux's prefix; the daemon's autostart
adds that dir to PATH. If you uninstall Termux, nmap dies with it.

### Sensors

```bash
shellr shell 'dumpsys sensorservice | head -40'      # available sensors
# location — needs termux-location (Termux:API)
shellr shell 'termux-location'
```

### System / package management

```bash
shellr shell 'pm list packages'                       # all packages
shellr shell 'pm list packages -3'                    # user apps only
shellr shell 'pm path com.android.chrome'             # find APK path
shellr shell 'dumpsys package com.android.chrome | grep versionName'
shellr shell 'logcat -d -t 100 *:E'                   # recent errors
shellr shell 'getprop ro.build.version.release'       # Android version
```

### File ops

```bash
# Write then read back
shellr write /sdcard/Download/hello.txt 'hello from VPS'
shellr shell 'cat /sdcard/Download/hello.txt'

# List directory
shellr shell 'ls -la /sdcard/Download/'

# Binary file transfer (encode locally, decode on phone)
echo "base64-payload" | base64 -d | shellr write /sdcard/foo.bin
```

### Notifications (proactive alerts from any caller)

```bash
shellr notify 'Mom' 'Dinner at 8 pm'           # basic
shellr notify 'Server down' 'api.weavee.in returned 502'   # ops alerting
```

The client uses `cmd notification post` as the shell UID, which
gets past Android's "root has no package" rejection. The notification
shows up in the shade but may not heads-up depending on phone's
notification config.

### Camera (trigger an intent; user must snap)

```bash
# Open the camera app — user takes photo manually
shellr shell 'am start -a android.media.action.IMAGE_CAPTURE --eu android.intent.extras.CAMERA_FACING 1'
# Read back any new photo in /sdcard/DCIM/Camera/
shellr shell 'ls -lat /sdcard/DCIM/Camera/ | head -3'
```

Programmatic photo capture needs Camera2 API + Termux:API install.

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

3. **File whitelist.** Reads/writes outside the daemon home, /sdcard,
   and /data/local/tmp are rejected by the daemon. If the user asks
   for /system/etc/hosts, stop and confirm — that's a system mutation.

4. **Timeout everything.** Pass `timeout` explicitly for anything that
   could hang: `shellr shell '<cmd>', 60` or use `timeout 30 cmd`
   inside the command.

5. **No secrets in logs.** The daemon logs every method call. Avoid
   putting API keys, passwords, or personal data into commands.

6. **Never bind to `0.0.0.0`.** Always pass `--host <tunnel-IP>`. The
   autostart script discovers the right IP from `tun0`; trust it.

## Tools you may need to install on the phone (per user choice)

When a feature needs a tool not bundled with Android, **ask the user
to install it on the phone** — don't write fresh root scripts that
vendor a static binary. List of common ones:

| Tool | When needed | Install |
|---|---|---|
| `nmap` | Subnet scanning, OS detection | `pkg install nmap` (in Termux) |
| `tcpdump` | Packet capture | `pkg install tcpdump` |
| `termux-api` + `Termux:API` app | BT scan, location, sensors, photo capture | F-Droid: Termux:API + `pkg install termux-api` |
| `python` + `requests` | Custom Python scripts on phone | Already installed via Termux |

If the user accepts the install, the next call is straightforward:

```bash
shellr shell 'pkg install -y nmap'
# Then:
shellr shell 'nmap -sn 192.168.1.0/24'
```

## Phone-pushed state (Pattern B — proactive)

If the user wants the LLM to monitor and react to phone state, the
phone can push a state JSON to the VPS. The daemon supports `ping`
for on-demand; for proactive push, the phone needs a `cron` or a
recurring `shellr shell` from the phone side.

A scheduled Hermes cron job that polls phone state every N minutes is
the simpler path. See `~/.hermes/cron/` for examples.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `shellr: command not found` (caller) | `~/.local/bin` not on PATH | `echo 'export PATH=$HOME/.local/bin:$PATH' >> ~/.bashrc && source ~/.bashrc` |
| `connection refused` on 7777 | daemon not running on phone | run `/data/adb/service.d/shellrd.sh` from ADB — it waits for Tailscale then starts daemon |
| `401 bad signature` | secret mismatch between phone and caller | compare `<secret_path>` on both ends; same value, same permissions (chmod 600) |
| `HMAC mismatch from ...` in `/sdcard/shellr.log` | wrong secret OR clock skew | check `date` on both ends |
| `Read timed out` | command genuinely hung OR phone went to sleep | raise timeout; check phone battery |
| `could not resolve Tailscale IP for <name>` | caller not on tailnet, or wrong hostname | `tailscale status` on the caller; or pass `--phone-ip 100.x.y.z` |
| `error: the following arguments are required: --host` | old daemon missing `--host` arg | sync the latest daemon source |
| Daemon dies hours after boot | Android killed it for battery | Daemon is respawned by `service.d` on next boot; for now, set Termux/Python to "Unrestricted" |
| `Bluetooth: Unknown command: start-discovery` | `cmd bluetooth_manager` is crippled on modern Android | Use Termux:API (`termux-bluetooth-scan`) or read state via `dumpsys bluetooth_manager` |

## Termux gotchas that affect all Android builds

These bite every Android/Termux daemon script. They are not bugs in
your code — they are how Android shells work. Future sessions building
Android/Termux tools should bake them in from day one.

1. **Termux default `sh` is mksh, not bash.** `set -o pipefail`,
   `[[ ... ]]`, `local`, and process substitution all fail. Always
   use bash explicitly: `#!/data/data/com.termux/files/usr/bin/bash`
   (absolute path — `/usr/bin/env bash` works but the absolute path
   is bulletproof).

2. **`su -c` strips `$PATH`.** Even if `python3` is on the user's
   PATH inside Termux, the moment you wrap a command in `su -c '...'`
   to run it as root, the root shell has a sparse PATH and won't
   find anything in `/data/data/com.termux/files/usr/bin`. Always
   use absolute paths to Termux binaries in any `su -c` invocation.

3. **`set -e` + idempotent operations = silent death.** A `cp -f`
   that detects "source and destination are the same file" exits
   non-zero, which `set -e` turns into a script abort. The proper
   defense is to make install scripts conditional rather than
   unconditional. Always read the script's error carefully — `set -e`
   aborts on the FIRST non-zero exit.

## Audit trail

- Phone-side: `/sdcard/shellr.log` (every RPC, every exec, every read/write)
- Caller-side: `~/.local/share/shellr/shellr.log` (every call)
- Bluetooth: `/data/misc/bluetooth/logs/btsnoop_hci.log` (HCI snoop, pull + Wireshark to inspect)

When investigating an incident or explaining to the user what the
agent just did on the phone, both logs are the source of truth.

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
```

The autostart script is idempotent — re-running it after a daemon
crash does the right thing (waits for tunnel, starts daemon,
verifies via `pgrep`).

## Companion skills

- **`rooted-android-llm-gateway`** — broader LLM-driven phone
  optimization loops (battery, bloatware, network defense, pattern
  learning). Has the scope guardrail and the math.

## Evolving this skill

This skill is **iterative**. When a user request reveals a new
capability, prove it on the phone first, then add the working
recipe to this file. Use this checklist:

1. **Probe.** Use `shellr shell '<cmd>'` (or chained probes) to see
   what works and what doesn't. Look at `dumpsys`, `/proc`, `/sys`,
   `cmd`, the various `am` broadcasts, and `logcat` traces.
2. **If a tool is missing** (e.g. `nmap`, `termux-api`), **stop and
   ask the user** to install it. Do NOT vendor prebuilt binaries.
3. **If a recipe is novel and works**, add it to:
   - `~/.hermes/skills/shellr-phone-control/SKILL.md` (this file, master copy)
   - `~/Programs/shellr/docs/SKILL.md` (public repo copy)
   Then commit + push to the shellr GitHub repo so other users
   inherit the new command. Push via `gh sync` if `gh` is
   authenticated, or `git push origin main`.
4. **If a recipe is BROKEN** (relies on tools not on the phone),
   document it under "Tools you may need" with the install command
   the user can run themselves when needed. Do **not** assume the
   tool exists.
5. **Never bake in user-specific data** to the public `docs/SKILL.md`:
   use the `SHELLR_*` env vars or the table at the top.

## Communication legibility (chat-mediated deploys)

When sending commands to the user through Telegram, Discord, Slack,
or any other chat that mangles multi-line content, **don't wrap
multi-line scripts in `cat <<EOF ... EOF` heredocs** — chat clients
often collapse them, garble the EOF marker, or render the wrapper
as dead text. Use plain fenced code blocks with one command per
line, or send the **base64-encoded** content via the daemon's own
`write` RPC.

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
the EOF marker swallowed. The plain-block version is paste-ready
and survives any chat client.
