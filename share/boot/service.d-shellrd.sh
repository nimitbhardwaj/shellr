#!/data/data/com.termux/files/usr/bin/bash
# shellrd auto-start for KernelSU — battery-tuned + Tailscale-aware.
#
# Run by KernelSU's service.d mechanism at every boot, as root, after
# /data is mounted. Discovers the current Tailscale tunnel IP from the
# tun0 interface, falls back to a cached IP or a hardcoded fallback,
# then launches the daemon bound to that IP.
#
# Drop this file at:  /data/adb/service.d/shellrd.sh
# Make it executable:  chmod +x /data/adb/service.d/shellrd.sh
#
# Environment:
#   - Adds Termux's bin dir to PATH so root can call python3, nmap,
#     curl, etc. by name (instead of needing absolute paths).
#   - PYTHONHOME points at Termux's stdlib (the only Termux dep left).

set -eu

# Canonical home for shellrd on rooted phones (KernelSU convention).
# /data/adb/shellrd is the only canonical location; /data/local/tmp/shellrd
# is no longer listed in ALLOWED_ROOTS.
DAEMON="/data/adb/shellrd/shellrd.py"
SECRET="/data/adb/shellrd/.shellr_secret"
LOG="/sdcard/shellr.log"
IP_CACHE="/data/adb/shellrd/.last_ip"
FALLBACK="100.111.121.72"
BOOT_WAIT=300
POLL_INTERVAL=5

# Termux's bin dir — gives root access to python3, nmap, curl, etc.
TERMUX_BIN="/data/data/com.termux/files/usr/bin"
TERMUX_HOME="/data/data/com.termux/files/usr"

export PATH="$TERMUX_BIN:$PATH"
export PYTHONHOME="$TERMUX_HOME"
export LD_LIBRARY_PATH="$TERMUX_HOME/lib:${LD_LIBRARY_PATH:-}"

[ -f "$DAEMON" ]  || { echo "[shellrd] daemon missing"; exit 0; }
[ -f "$SECRET" ]  || { echo "[shellrd] secret missing"; exit 0; }

echo "[shellrd] python3: $(which python3 2>/dev/null || echo MISSING)"
echo "[shellrd] nmap:    $(which nmap 2>/dev/null || echo 'not installed')"

discover_ip() {
    IP=$(ip -4 addr show tun0 2>/dev/null | awk '/inet 100\./ {print $2}' | cut -d/ -f1 | head -1)
    if [ -z "$IP" ] && [ -f "$IP_CACHE" ]; then
        CACHED=$(cat "$IP_CACHE" 2>/dev/null)
        case "$CACHED" in 100.*) IP="$CACHED" ;; esac
    fi
    [ -z "$IP" ] && IP="$FALLBACK"
    echo "$IP"
}

CURRENT_IP=$(discover_ip)

# If daemon already running, verify it's on the current IP.
if pgrep -f shellrd.py >/dev/null; then
    if [ -f "$IP_CACHE" ] && [ "$(cat "$IP_CACHE" 2>/dev/null)" != "$CURRENT_IP" ]; then
        echo "[shellrd] IP changed $(cat "$IP_CACHE") -> $CURRENT_IP, restarting"
        pkill -f shellrd.py
        sleep 2
    else
        echo "[shellrd] already running on $CURRENT_IP"
        exit 0
    fi
fi

echo "[shellrd] waiting for Tailscale tunnel (up to ${BOOT_WAIT}s)..."
end=$(( $(date +%s) + BOOT_WAIT ))
while [ $(date +%s) -lt $end ]; do
    if ip -4 addr show tun0 2>/dev/null | grep -q "inet 100\\."; then break; fi
    sleep $POLL_INTERVAL
done

CURRENT_IP=$(discover_ip)
echo "$CURRENT_IP" > "$IP_CACHE" 2>/dev/null
echo "[shellrd] starting on $CURRENT_IP"

# Inherit PATH so subprocess.Popen inside the daemon finds python3, nmap, etc.
# IMPORTANT: pass --host and --secret explicitly. Newer builds of shellrd
# require --host (default is "must specify Tailscale IP") and --secret
# so the daemon knows where to load the pre-shared key.
( setsid env PATH="$PATH" PYTHONHOME="$PYTHONHOME" \
    python3 "$DAEMON" --host "$CURRENT_IP" --secret "$SECRET" \
    > "$LOG" 2>&1 < /dev/null & )

sleep 2
if pgrep -f shellrd.py >/dev/null; then
    echo "[shellrd] started OK"
else
    echo "[shellrd] FAILED to start:"
    tail -5 "$LOG" 2>/dev/null
    exit 1
fi
exit 0
