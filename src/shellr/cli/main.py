"""``shellr`` CLI entry point."""

from __future__ import annotations

import argparse
import base64
import json
import logging
import sys
from pathlib import Path

from shellr import ShellrClient, __version__, resolve_tailscale_ip

LOG_PATH = Path.home() / ".local" / "share" / "shellr" / "shellr.log"

log = logging.getLogger("shellr")


def setup_logging() -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-5s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    log.setLevel(logging.INFO)
    fh = logging.FileHandler(LOG_PATH, mode="a", encoding="utf-8")
    fh.setFormatter(fmt)
    log.addHandler(fh)
    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(fmt)
    log.addHandler(sh)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="shellr",
        description=f"shellr v{__version__} — control your phone over Tailscale",
    )
    ap.add_argument("--phone", default="nimits-a51",
                    help="Tailscale hostname (default: nimits-a51)")
    ap.add_argument("--port", type=int, default=7777)
    ap.add_argument("--secret", default=str(Path.home() / ".shellr_secret"))
    ap.add_argument("--phone-ip", default=None,
                    help="override Tailscale IP lookup")
    ap.add_argument("--resolve", action="store_true",
                    help="just print the resolved Tailscale IP and exit")
    ap.add_argument("--version", action="version",
                    version=f"shellr {__version__}")
    sub = ap.add_subparsers(dest="op")

    p_shell = sub.add_parser("shell", help="run a shell command on the phone")
    p_shell.add_argument("command", nargs=argparse.REMAINDER,
                         help="command (everything after 'shell')")

    p_info = sub.add_parser("info", help="phone info (uid, kernel, tailscale ip, ...)")
    p_ping = sub.add_parser("ping", help="ping the daemon")
    p_health = sub.add_parser("health", help="HTTP health check")

    p_list = sub.add_parser("list", help="list a directory on the phone")
    p_list.add_argument("path")

    p_read = sub.add_parser("read", help="read a file (writes bytes to stdout)")
    p_read.add_argument("path")

    p_write = sub.add_parser("write", help="write a file (text)")
    p_write.add_argument("path")
    p_write.add_argument("text")

    p_notify = sub.add_parser("notify", help="post a notification to the phone")
    p_notify.add_argument("title")
    p_notify.add_argument("body")

    sub.add_parser("repl", help="drop into an interactive shell")
    return ap


# ---------------------------------------------------------------------------
# subcommand handlers
# ---------------------------------------------------------------------------

def cmd_resolve(client: ShellrClient) -> int:
    print(client.phone_ip)
    return 0


def cmd_shell(client: ShellrClient, command: str) -> int:
    result = client.shell(command)
    if result.get("ok") and isinstance(result.get("result"), dict):
        r = result["result"]
        sys.stdout.write(r.get("stdout", ""))
        sys.stderr.write(r.get("stderr", ""))
        return 0 if r.get("ok") else 1
    print(json.dumps(result, indent=2), file=sys.stderr)
    return 1 if not result.get("ok") else 0


def cmd_info(client: ShellrClient) -> int:
    print(json.dumps(client.info(), indent=2))
    return 0


def cmd_ping(client: ShellrClient) -> int:
    print(json.dumps(client.ping(), indent=2))
    return 0


def cmd_health(client: ShellrClient) -> int:
    print("ok" if client.health() else "down")
    return 0 if client.health() else 1


def cmd_list(client: ShellrClient, path: str) -> int:
    print(json.dumps(client.listdir(path), indent=2))
    return 0


def cmd_read(client: ShellrClient, path: str) -> int:
    result = client.read(path)
    if result.get("ok") and isinstance(result.get("result"), dict):
        data = base64.b64decode(result["result"]["content_b64"])
        sys.stdout.buffer.write(data)
        return 0
    print(json.dumps(result, indent=2), file=sys.stderr)
    return 1


def cmd_write(client: ShellrClient, path: str, text: str) -> int:
    print(json.dumps(client.write(path, text), indent=2))
    return 0


def cmd_notify(client: ShellrClient, title: str, body: str) -> int:
    result = client.notify(title, body)
    if result.get("ok") and isinstance(result.get("result"), dict):
        r = result["result"]
        if r.get("ok"):
            print("notified")
            return 0
        sys.stderr.write(r.get("stderr", ""))
        return 1
    print(json.dumps(result, indent=2), file=sys.stderr)
    return 1


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------

def main() -> int:
    setup_logging()
    ap = build_parser()
    args = ap.parse_args()

    if args.resolve:
        try:
            print(resolve_tailscale_ip(args.phone))
            return 0
        except RuntimeError as exc:
            print(f"shellr: {exc}", file=sys.stderr)
            return 1

    client = ShellrClient(
        phone=args.phone,
        port=args.port,
        secret_path=Path(args.secret),
        phone_ip=args.phone_ip,
    )

    if args.op is None:
        ap.print_help()
        return 0

    if args.op == "shell":
        return cmd_shell(client, " ".join(args.command))
    if args.op == "info":
        return cmd_info(client)
    if args.op == "ping":
        return cmd_ping(client)
    if args.op == "health":
        return cmd_health(client)
    if args.op == "list":
        return cmd_list(client, args.path)
    if args.op == "read":
        return cmd_read(client, args.path)
    if args.op == "write":
        return cmd_write(client, args.path, args.text)
    if args.op == "notify":
        return cmd_notify(client, args.title, args.body)
    if args.op == "repl":
        from shellr.cli.repl import repl
        return repl(client)

    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
