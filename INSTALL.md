# INSTALL — fresh device setup

Two hosts:
- **Controller** — your laptop, VPS, or any Linux/Unix machine on the
  same Tailscale network as the phone. Has the `shellr` command.
- **Phone** — a rooted Android (KernelSU or Magisk). Has the `shellrd`
  daemon.

You need the HMAC secret to match on both sides — the easy way is to
generate it on the controller and `adb push` (or scp/Tailscale) it to
the phone.

---

## 1. Controller setup

```bash
# 1. Install the tool
git clone https://github.com/nimitbhardwaj/shellr.git ~/shellr
cd ~/shellr
pip install -e ".[dev]"                  # adds 'shellr' and 'shellrd' to PATH

# 2. Generate the HMAC secret (NEVER commit this anywhere)
openssl rand -hex 32 | tee ~/.shellr_secret
chmod 600 ~/.shellr_secret
cat  ~/.shellr_secret                    # 64 hex chars (32 random bytes)
```

Connect to Tailscale if you haven't already:

```bash
tailscale up
```

---

## 2. Phone setup

### 2a. Prerequisites

The phone must have:
- **Root** — either KernelSU (recommended) or Magisk
- **Tailscale for Android** (from Play Store or F-Droid)
- **Termux** (from F-Droid) — only needed as the python interpreter
  source. The daemon itself doesn't use Termux as a shell.

### 2b. Required Termux packages

Open the Termux app on the phone and run:

```bash
pkg update
pkg install python        # python3 binary
```

(Do NOT install `termux-bluetooth-scan` — that package does not exist.
BT scanning works through **Termux:API**. See below.)

### 2c. Bootstrap the daemon over ADB

Plug the phone in via USB, enable USB debugging, then from the
controller:

```bash
# 1. adb public key exchange (one-time per host)
adb devices                          # confirm phone shows up

# 2. Push the current daemon source to /data/local/tmp/shellrd/
adb shell 'mkdir -p /data/local/tmp/shellrd'
adb push ~/shellr/src/shellr/daemon/__init__.py /data/local/tmp/shellrd/shellrd.py
adb shell 'chmod 700 /data/local/tmp/shellrd/shellrd.py'

# 3. Push the autostart (KernelSU service.d)
adb shell 'mkdir -p /data/adb/service.d'
adb push ~/shellr/share/boot/service.d-shellrd.sh /data/adb/service.d/shellrd.sh
adb shell 'chmod 755 /data/adb/service.d/shellrd.sh'

# 4. Generate (or push) the matching HMAC secret.
# Easiest: have the phone generate and you copy paste to the controller.
adb shell 'mkdir -p /data/local/tmp/shellrd'
adb shell "python3 -c 'import secrets; print(secrets.token_hex(32))' > /data/local/tmp/shellrd/.shellr_secret"
adb shell 'chmod 600 /data/local/tmp/shellrd/.shellr_secret'
adb pull /data/local/tmp/shellrd/.shellr_secret ~/.shellr_secret_vps     # one-time copy
# CRITICAL: the secret on the phone and on the controller MUST be identical.
# Either: paste the controller's value into the phone's file
#   adb push ~/.shellr_secret /data/local/tmp/shellrd/.shellr_secret
# OR copy the adb-pull file over your controller's secret
#   cp ~/.shellr_secret_vps ~/.shellr_secret
# Then:
chmod 600 ~/.shellr_secret
```

### 2d. Start the daemon

```bash
# Tell the phone to start now (also auto-starts at every reboot)
adb shell /data/adb/service.d/shellrd.sh

# Confirm the daemon is bound and listening
adb shell 'cat /sdcard/shellr.log | tail -10'
```

You should see:

```
[shellrd] python3: /data/data/com.termux/files/usr/bin/python3
[shellrd] nmap: /data/data/com.termux/files/usr/bin/nmap   (if installed)
[shellrd] starting on 100.<your-tailscale-ip>
[shellrd] started OK
```

### 2e. Verify from the controller

```bash
shellr --resolve                     # → 100.x.y.z (the phone's tailnet IP)
shellr ping                          # → {"ok": true, "result": {"pong": true, ...}}
shellr info                          # → kernel, android_sdk, uid, ...
```

If `connection refused` or `connection timed out`, see `TROUBLESHOOTING`
below.

---

## 3. Optional: install command-line tools on the phone

The shellr daemon adds Termux's `bin/` to its PATH so subprocesses
can call `python3`, `nmap`, etc. by name. To add a tool:

```bash
# Open Termux on the phone, run:
pkg install <package>

# Or via shellr from the controller (uses the daemon's run_shell RPC):
shellr shell 'pkg install -y nmap'   # 1 call, as root, no su indirection
```

The phone accepts `pkg install` directly because the daemon runs as
root and its child processes inherit the PATH (with Termux prepended).
The daemon does **NOT** automatically install anything — you, the
user, decide which tools you need.

| Package | Gives you | When needed |
|---|---|---|
| `nmap` | Full port + service + OS scans | LAN reconnaissance |
| `tcpdump` | Packet capture (run as root via shellr) | Capturing traffic |
| `termux-api` + **Termux:API** app | BT scan/locate/photo, sensors, etc. | Active BT discovery, location, camera |

`Termux:API` is a two-part install:
1. The **Termux:API helper app** from F-Droid
2. `pkg install termux-api` in Termux

Both must be present; if only one is, calls fail silently.

---

## 4. Uninstall

```bash
# Phone side
adb shell 'rm /data/adb/service.d/shellrd.sh'
adb shell 'pkill -f shellrd.py'
adb shell 'rm -rf /data/local/tmp/shellrd'

# Controller side
pip uninstall shellr
rm ~/shellr                          # if you want
rm ~/.shellr_secret
```

After uninstalling, the secret in your password manager should also
be retired.

---

## TROUBLESHOOTING

### `connection refused` on `shellr ping`

Run on the phone (via ADB):
```bash
adb shell 'ps -ef | grep shellrd | grep -v grep'   # is it running?
adb shell 'cat /sdcard/shellr.log | tail -20'      # why not?
adb shell 'cat /data/local/tmp/shellrd/.last_ip'   # what IP does it know?
```

Then restart:
```bash
adb shell /data/adb/service.d/shellrd.sh
```

### `401 bad signature`

The HMAC secrets don't match. Verify:
```bash
adb shell 'cat /data/local/tmp/shellrd/.shellr_secret'   # phone
cat ~/.shellr_secret                                     # controller
```

Diff them visually; they should be byte-identical (modulo trailing
newlines, which both sides strip).

### `error: the following arguments are required: --host`

The daemon binary on the phone is out of date. Re-push:
```bash
adb push ~/shellr/src/shellr/daemon/__init__.py /data/local/tmp/shellrd/shellrd.py
adb shell 'pkill -f shellrd.py'
adb shell /data/adb/service.d/shellrd.sh
```

### Tailscale IP rotation

If the phone's `100.x.y.z` IP changes (rare but happens on tailscale
re-auth):
```bash
adb shell /data/adb/service.d/shellrd.sh   # auto-detects the new IP
```

The autostart kills the old daemon only when the IP has actually
changed.

### Active Bluetooth scanning (`cmd bluetooth_manager start-discovery` fails)

Modern Android (Samsung, Pixel 8+, anything with the Bluetooth GD
stack) doesn't expose `start-discovery` via `cmd`. The supported
way is **Termux:API**:
```bash
# Phone side
pkg install termux-api   # the package
# + install Termux:API app from F-Droid (a separate Android APK)

# Then test from the phone:
termux-bluetooth-scan

# From the controller:
shellr shell "su 10256 -c 'PATH=/data/data/com.termux/files/usr/bin PREFIX=/data/data/com.termux/files/usr HOME=/data/data/com.termux/files/home /data/data/com.termux/files/usr/bin/termux-bluetooth-scan'"
```

If `termux-bluetooth-scan` returns nothing, no BLE devices are
broadcasting nearby (the scan only sees **advertising** devices).
Try walking past wearables or a smart TV, or briefly disabling/re-
enabling Bluetooth to trigger more broadcasts.
