#!/data/data/com.termux/files/usr/bin/bash
# shellr — install the daemon on a rooted Android phone.
#
# Run once in Termux on the phone. The script:
#   1. Verifies the python3 + secret are in place at /data/local/tmp/shellrd/
#   2. Writes the KernelSU service.d autostart script
#   3. Starts the daemon now
#   4. Prints the Tailscale IP you need to use from your VPS
#
# Requires: rooted Android (KernelSU or Magisk) + Termux installed
#           (only needed for the python3 binary; the daemon itself runs as root).
set -eu

PHONE_HOME="/data/local/tmp/shellrd"
PYTHON_BIN="/data/data/com.termux/files/usr/bin/python3"
SERVICE_D="/data/adb/service.d"

echo "[install] verifying phone-side files"

# 1. Daemon
if [ ! -f "$PHONE_HOME/shellrd.py" ]; then
    echo "[install] FATAL: $PHONE_HOME/shellrd.py missing"
    echo "  Copy the daemon first:"
    echo "    scp <vps>:/path/to/shellr/src/shellr/daemon/__init__.py $PHONE_HOME/shellrd.py"
    echo "  (or any other mechanism)"
    exit 1
fi
chmod 700 "$PHONE_HOME/shellrd.py"

# 2. Secret — generate one if missing
if [ ! -f "$PHONE_HOME/.shellr_secret" ]; then
    "$PYTHON_BIN" -c "import secrets; print(secrets.token_hex(32))" > "$PHONE_HOME/.shellr_secret"
    chmod 600 "$PHONE_HOME/.shellr_secret"
    echo "[install] generated new 64-char hex secret at $PHONE_HOME/.shellr_secret"
    echo "  COPY THIS to your VPS:"
    echo "    ssh hermes 'cat > ~/.shellr_secret'"
    echo "    ssh hermes 'chmod 600 ~/.shellr_secret'"
else
    echo "[install] secret already exists"
fi
chmod 600 "$PHONE_HOME/.shellr_secret"

# 3. Python runtime (Termux's binary is fine, just verify it exists)
[ -x "$PYTHON_BIN" ] || { echo "[install] FATAL: python3 missing at $PYTHON_BIN"; exit 1; }
echo "[install] python3 OK at $PYTHON_BIN"

# 4. KernelSU service.d autostart
mkdir -p "$SERVICE_D"
SCRIPT_SRC="$(dirname "$0")/../share/boot/service.d-shellrd.sh"
if [ ! -f "$SCRIPT_SRC" ]; then
    # Fallback: look next to the script
    SCRIPT_SRC="/data/local/tmp/shellrd/share/boot/service.d-shellrd.sh"
fi
if [ ! -f "$SCRIPT_SRC" ]; then
    echo "[install] FATAL: service.d script missing at $SCRIPT_SRC"
    echo "  Copy share/boot/service.d-shellrd.sh to $SERVICE_D/shellrd.sh and chmod +x"
    exit 1
fi
cp "$SCRIPT_SRC" "$SERVICE_D/shellrd.sh"
chmod 755 "$SERVICE_D/shellrd.sh"
echo "[install] wrote $SERVICE_D/shellrd.sh"

# 5. Start the daemon now (as root)
echo "[install] starting daemon..."
"$SERVICE_D/shellrd.sh"

# 6. Show the IP the VPS should target
echo
echo "[install] DONE. From your VPS:"
echo "  shellr --resolve                       # shows phone IP"
echo "  shellr ping                            # verify it's alive"
echo "  shellr shell 'uptime; whoami; uname -a' # first commands"
