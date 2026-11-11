"""Homelab Watch — read-only monitoring of your home network, servers, sites and agents.

Tools answer "is everything OK at home?"; `/homelab alerts on` creates a no_agent cron job that posts only
what changed each minute, without spending model tokens (see alerts.py).
"""

from __future__ import annotations

import json
import logging
import shutil
import sys
from pathlib import Path

from . import alerts, schemas, usage
from .report import alert_text, spoken_summary, status_payload, usage_sentence
from .service import Watch, scripts_dir
from .targets import TargetsError
from .tools import make_handlers

_EXAMPLE = Path(__file__).parent / "targets.example.yaml"
logger = logging.getLogger(__name__)


def _cli_setup(parser) -> None:
    sub = parser.add_subparsers(dest="homelab_cmd")
    sub.add_parser("check", help="Check every target now and print the status")
    sub.add_parser("tick", help="Check and print only new or resolved incidents (for a no_agent cron job)")
    sub.add_parser("init", help="Copy the example targets.yaml into place")
    sub.add_parser("json", help="Check and print the full status as JSON")


def register(ctx) -> None:
    def get_watch() -> Watch:
        return Watch.from_settings(ctx.get_config("targets_file", default="") or "")

    prices = usage.load_prices(ctx.get_config("prices", default={}) or {})

    def baseline_model() -> str:
        configured = ctx.get_config("baseline_model", default="") or ""
        if configured:
            return configured
        from hermes_cli.config import load_config_readonly
        model = load_config_readonly().get("model") or {}
        return model.get("default", "") if isinstance(model, dict) else str(model)

    def on_api_request(model: str = "", provider: str = "", base_url: str = "", usage: dict | None = None, **_) -> None:
        try:
            get_watch().record_usage(
                model=model, provider=provider, base_url=base_url, usage=usage, prices=prices,
                baseline_model=baseline_model(),
                extra_subscriptions=tuple(ctx.get_config("subscription_providers", default=[]) or ()))
        except Exception:  # an accounting slip must never touch the agent's turn
            logger.debug("homelab-watch: usage not recorded", exc_info=True)

    ctx.register_hook("post_api_request", on_api_request)

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
            print(json.dumps(status_payload(rnd, targets, watch.usage_summary()), indent=2))
        else:
            print(spoken_summary(rnd, targets))
        return 0

    ctx.register_cli_command("homelab", "Homelab Watch: check your home network and devices",
                             _cli_setup, run_cli)

    def slash_alerts(words: list[str]) -> str:
        action = words[0] if words else "status"
        if action == "on":
            return alerts.enable(ctx.dispatch_tool, get_watch(), scripts_dir(), words[1] if len(words) > 1 else "")
        if action == "off":
            return alerts.disable(ctx.dispatch_tool, scripts_dir())
        return alerts.status(ctx.dispatch_tool)

    def slash(raw_args: str = "", **_) -> str:
        words = raw_args.split()
        try:
            if words[:1] == ["alerts"]:
                return slash_alerts(words[1:])
            rnd, targets = get_watch().check()
        except TargetsError as exc:
            return f"Homelab Watch: {exc}"
        return " ".join(filter(None, [spoken_summary(rnd, targets), usage_sentence(get_watch().usage_summary())]))

    ctx.register_command("homelab", slash, description="Check the homelab now, or manage alerts",
                         args_hint="[alerts on [deliver] | alerts off | alerts]")
