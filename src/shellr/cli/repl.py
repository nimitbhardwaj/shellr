"""Interactive shellr REPL.

Type ``shell`` commands, ``read``, ``write``, ``list``, ``info``, ``ping``,
``health`` at the ``shellr>`` prompt. ``exit`` or ``quit`` to leave.
"""

from __future__ import annotations

import json
import shlex
import sys
from typing import Callable

from shellr import ShellrClient

HELP_TEXT = """\
commands:
  shell <cmd>    run shell command on phone
  read <path>    read file
  write <p> <t>  write file
  list <path>    list directory
  info           phone info
  ping           ping daemon
  health         HTTP health check
  help           this help
  exit / quit    leave the REPL\
"""


def repl(client: ShellrClient) -> int:
    print("shellr REPL — type 'help' for commands, 'exit' to quit", file=sys.stderr)
    handlers: dict[str, Callable[[list[str]], int]] = {
        "shell":  lambda a: _echo_shell(client, a),
        "read":   lambda a: _echo_json(client.read(a[0])) if a else _usage("read <path>"),
        "write":  lambda a: _echo_json(client.write(a[0], " ".join(a[1:]))) if len(a) >= 2 else _usage("write <path> <text>"),
        "list":   lambda a: _echo_json(client.listdir(a[0])) if a else _usage("list <path>"),
        "info":   lambda a: _echo_json(client.info()),
        "ping":   lambda a: _echo_json(client.ping()),
        "health": lambda a: print("ok" if client.health() else "down"),
    }

    while True:
        try:
            line = input("shellr> ").strip()
        except (EOFError, KeyboardInterrupt):
            print(file=sys.stderr)
            return 0
        if not line:
            continue
        if line in ("exit", "quit"):
            return 0
        if line in ("help", "?"):
            print(HELP_TEXT, file=sys.stderr)
            continue

        try:
            parts = shlex.split(line)
        except ValueError as exc:
            print(f"parse error: {exc}", file=sys.stderr)
            continue

        cmd, args = parts[0], parts[1:]
        handler = handlers.get(cmd)
        if handler is None:
            print(f"unknown command: {cmd!r} (try 'help')", file=sys.stderr)
            continue
        try:
            handler(args)
        except Exception as exc:
            print(f"error: {exc}", file=sys.stderr)


def _echo_shell(client: ShellrClient, args: list[str]) -> int:
    if not args:
        return _usage("shell <cmd>")
    cmd = " ".join(args)
    result = client.shell(cmd)
    if isinstance(result.get("result"), dict):
        r = result["result"]
        sys.stdout.write(r.get("stdout", ""))
        sys.stderr.write(r.get("stderr", ""))
    else:
        print(json.dumps(result, indent=2))
    return 0


def _echo_json(d: dict) -> int:
    print(json.dumps(d, indent=2))
    return 0


def _usage(msg: str) -> int:
    print(f"usage: {msg}", file=sys.stderr)
    return 1
