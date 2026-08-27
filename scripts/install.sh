#!/usr/bin/env bash
# install.sh — one-shot setup for both VPS-side and phone-side.
#
# Usage (on the VPS):
#   git clone <repo> ~/Programs/shellr
#   cd ~/Programs/shellr
#   ./scripts/install.sh vps
#
# Usage (on the phone, in Termux):
#   bash <scp-path>/scripts/install.sh phone
#
# This is a thin wrapper around pip + the phone installer; the heavy
# lifting lives in pyproject.toml and share/phone/install.sh.

set -eu

CMD="${1:-help}"

vps_install() {
    echo "[vps] installing shellr client into the current environment"
    if [ ! -d .venv ]; then
        python3 -m venv .venv
        echo "[vps] created .venv"
    fi
    # shellcheck disable=SC1091
    source .venv/bin/activate
    pip install --upgrade pip >/dev/null
    pip install -e ".[dev]"
    echo "[vps] installed. Try: shellr --resolve"
    echo "[vps] ensure ~/.shellr_secret exists (chmod 600) — it must match"
    echo "      /data/adb/shellrd/.shellr_secret on the phone"
}

phone_install() {
    echo "[phone] this script is meant to be run ON THE PHONE"
    echo "[phone] Usage:  bash scripts/install.sh phone"
    echo
    if [ ! -d /data/adb/shellrd ]; then
        echo "[phone] installing daemon to /data/adb/shellrd/"
        mkdir -p /data/adb/shellrd
        # Copy the daemon source
        cp ../src/shellr/daemon/__init__.py /data/adb/shellrd/shellrd.py
        chmod 700 /data/adb/shellrd/shellrd.py
    fi
    echo "[phone] done. Run 'bash share/phone/install.sh' to set up the secret"
    echo "[phone] and the service.d autostart."
}

case "$CMD" in
    vps)
        vps_install
        ;;
    phone)
        phone_install
        ;;
    help|--help|-h|"")
        cat <<EOF
shellr install.sh — subcommand installer

usage:
  ./scripts/install.sh vps        # install the Python client (editable mode)
  ./scripts/install.sh phone      # bootstrap the phone side (run on device)

For the full phone-side install (autostart + secret + daemon), run
  bash share/phone/install.sh
on the phone.
EOF
        ;;
    *)
        echo "unknown command: $CMD" >&2
        exit 1
        ;;
esac
