# LLM-driven install (for agents)

> **Read this first** if you (the LLM) are installing shellr on a fresh
> Android device on behalf of your user.

## Setup you need to do

You (the LLM) drive the install through Tailscale + ADB + your
existing tool set. **Do not** ask the user to run shell commands.
Guide them through the few USB + buttons steps, and run everything
else yourself.

The user only needs to do these physical steps:

1. Plug the phone into USB on a machine where you (the LLM) have
   an ADB shell. (Many LLMs have a controller VPS with ADB access
   to the phone via Tailscale SSH-tunneled ADB; the user doesn't
   need to be at the laptop.)
2. On the phone, enable Developer options → USB debugging (one-time).
3. Accept the ADB RSA fingerprint prompt the first time ADB connects
   (one-time).
4. Make sure Tailscale is installed and logged in on the phone (so
   the phone has a `100.x.y.z` tailnet IP).

Everything below is *you*, not the user, executing commands.

## Your install playbook

### Step 1 — confirm ADB sees the phone

```bash
adb devices
# Expect:   <serial>   device   (if so, you're good)
# If "unauthorized": tell the user to tap "Always allow from this
# computer" on the phone.
# If "offline": probably a driver issue on Windows controllers.
```

### Step 2 — confirm Tailscale is up on the phone

```bash
adb shell 'ip -4 addr show tun0 | grep "inet 100\\."'
# If empty: tell the user to open the Tailscale app on the phone
# and wait for it to log in. Then retry.
```

### Step 3 — confirm Termux + python3 are present

```bash
adb shell 'ls -la /data/data/com.termux/files/usr/bin/python3'
# If "No such file": tell the user to open Termux and run
# `pkg install python`. Then retry.
```

### Step 4 — push the installer and run it

```bash
adb push share/phone/install.sh /sdcard/install.sh
adb shell 'su -c "bash /sdcard/install.sh" 2>&1 | tee /sdcard/install.log'
```

Read the install log. The installer prints:

1. A block saying **"INSTALL COMPLETE"**.
2. The phone's **Tailscale IP** (e.g. `100.111.121.72`).
3. A **HMAC secret** (64 hex chars) — this is the important part.

### Step 5 — save the secret on the controller

The installer printed the secret verbatim. Save it as `~/.shellr_secret`
on the controller so the `shellr` command can sign requests:

```bash
echo "<paste-secret-here>" | tr -d '[:space:]' > ~/.shellr_secret
chmod 600 ~/.shellr_secret
# Verify
ls -la ~/.shellr_secret         # mode 600
wc -c ~/.shellr_secret          # 64 bytes
```

> **Do not** paste the secret in chat messages. Save it to a file
> directly via your file-write tool (requests module, `with open(...)`
> in execute_code, etc.). Never include it in the user-visible reply.

### Step 6 — verify connectivity from this LLM

Connect via Tailscale (not via ADB; that's a separate path).
Use your shellr client:

```python
# execute_code on the controller
from hermes_tools import terminal
import sys
sys.path.insert(0, "/home/hermes/Programs/shellr/src")
from shellr import ShellrClient
c = ShellrClient(phone_ip="<phone's Tailscale IP>")
print(c.ping())      # → pong, uid 0
print(c.info())      # → kernel, sdk, etc.
```

If `c.ping()` returns `{"ok": false, "error": "ConnectionError"}`:

- The phone and controller must be on the same Tailscale tailnet.
  Run `tailscale status` on the controller and confirm the phone
  appears as `active`.
- The autostart may not have started. Run via ADB:
  `adb shell 'su -c "bash /data/adb/service.d/shellrd.sh"'`
- The Tailscale IP may be wrong. Run `adb shell 'cat /data/local/tmp/shellrd/.last_ip'`
  and use that value.

### Step 7 — register the phone

If your shellr config keeps phone IPs in a profile (recommended),
write them now:

```yaml
# ~/.shellr/profiles.yaml
phones:
  <user-chosen-name>:
    ip: 100.111.121.72    # from step 4
    secret_path: ~/.shellr_secret
```

Or — for the common case — keep using the existing
`SHELLR_PHONE_IP` env var and `~/.shellr_secret`.

### Step 8 — give the user a one-line summary

Reply to the user with:

- The phone's Tailscale IP
- A confirmation you can reach it (`shellr ping → pong in <N>ms`)
- What you can now do (whatever shellr commands help the user's task)

## Tool installation post-install

If the user wants features requiring Termux packages (`nmap`,
`tcpdump`, `termux-api`, …), drive those via `shellr shell` yourself:

```bash
# Don't ask the user to open Termux and run pkg install.
# The daemon runs as root, so this works on its behalf:
shellr shell 'pkg install -y nmap'
# Same for tcpdump, termux-api, etc.
shellr shell 'pkg install -y tcpdump'
```

For packages whose companion app is a separate F-Droid install
(`Termux:API` requires the helper app), give the user one
clear instruction:

> "Open F-Droid on your phone, install Termux:API, then tell me
> when it's done — I'll install the matching package."

Then continue yourself. Don't ask the user to run shell commands
they could have run earlier.

## Common LLM mistakes to avoid

| Don't | Do |
|---|---|
| Ask the user to `adb push` something | You `adb push`, the user just presses buttons on the phone. |
| Show the secret in chat output | Save to file via tool calls, never inline |
| Run `pkg install` on the laptop | Run it via `shellr shell 'pkg install ...'` against the phone |
| Restart the daemon via `shellr shell 'kill <pid>'` | The skill warns against this. Use ADB for daemon restart: `adb shell 'bash /data/adb/service.d/shellrd.sh'` |
| Run the installer with `--no-su` to test on a non-rooted laptop | Use the smoke test in `tests/test_smoke.py` for that |
| Bundle services by hardcoding `nimits-a51` in code/config | Use the user's phone name + the `SHELLR_PHONE` env var |

## When something doesn't work

If install fails:

1. Read `/sdcard/install.log` (or your shell `tee` of it).
2. The most common reason: Tailscale isn't up yet on the phone
   when the autostart runs. The autostart waits up to 5 minutes.
   If you see the install succeeded but the daemon isn't
   reachable, run via ADB:
   `adb shell 'cat /sdcard/shellr.log | tail -20'`
3. If the secret is wrong, both sides won't match — generate a new
   one on the controller and push it via:
   `adb push ~/.shellr_secret /data/local/tmp/shellrd/.shellr_secret`
   then `adb shell 'pkill -f shellrd.py' && bash /data/adb/service.d/shellrd.sh`.

## Why this matters

**The user is busy.** Every shell command they have to run is a
pause, a context switch, and a chance for a typo. Run shell yourself.
Read phone state yourself. Generate secrets yourself. Your job is
to keep the human out of the loop as much as possible while
keeping the install verifiable and reversible.
