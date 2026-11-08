"""Homelab Watch — read-only monitoring of your home network, servers, sites and agents.

Tools answer "is everything OK at home?"; `hermes homelab tick` prints only what changed, so a
no_agent cron job runs it every minute and delivers alerts without spending model tokens.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from . import schemas
from .report import alert_text, spoken_summary, status_payload
from .service import Watch
from .targets import TargetsError
from .tools import make_handlers

_EXAMPLE = Path(__file__).parent / "targets.example.yaml"


def _cli_setup(parser) -> None:
    sub = parser.add_subparsers(dest="homelab_cmd")
    sub.add_parser("check", help="Check every target now and print the status")
    sub.add_parser("tick", help="Check and print only new or resolved incidents (for a no_agent cron job)")
    sub.add_parser("init", help="Copy the example targets.yaml into place")
    sub.add_parser("json", help="Check and print the full status as JSON")


def register(ctx) -> None:
    def get_watch() -> Watch:
        return Watch.from_settings(ctx.get_config("targets_file", default="") or "")

    handlers = make_handlers(get_watch)
    for schema in (schemas.HOMELAB_STATUS, schemas.HOMELAB_HEARTBEAT):
        ctx.register_tool(name=schema["name"], toolset="homelab", schema=schema,
                          handler=handlers[schema["name"]], emoji="🏠")

    def run_cli(args) -> int:
        watch = get_watch()
        cmd = getattr(args, "homelab_cmd", None) or "check"
        if cmd == "init":
            if watch.targets_path.exists():
                print(f"{watch.targets_path} already exists; edit it there.")
                return 0
            watch.targets_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(_EXAMPLE, watch.targets_path)
            print(f"Wrote {watch.targets_path}. Edit it, then run: hermes homelab check")
            return 0
        try:
            rnd, targets = watch.check()
        except TargetsError as exc:
            print(f"homelab-watch: {exc}", file=sys.stderr)
            return 2
        if cmd == "tick":
            text = alert_text(rnd, targets)
            if text:
                print(text)
        elif cmd == "json":
            print(json.dumps(status_payload(rnd, targets), indent=2))
        else:
            print(spoken_summary(rnd, targets))
        return 0

    ctx.register_cli_command("homelab", "Homelab Watch: check your home network and devices",
                             _cli_setup, run_cli)

    def slash(raw_args: str = "", **_) -> str:
        try:
            rnd, targets = get_watch().check()
        except TargetsError as exc:
            return f"Homelab Watch: {exc}"
        return spoken_summary(rnd, targets)

    ctx.register_command("homelab", slash, description="Check the homelab now")
