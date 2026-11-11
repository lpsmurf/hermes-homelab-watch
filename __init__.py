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

from . import alerts, router, schemas, usage
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

    skills_dir = Path(__file__).parent / "skills"
    for child in sorted(skills_dir.iterdir()) if skills_dir.is_dir() else ():
        if (child / "SKILL.md").is_file():
            ctx.register_skill(child.name, child / "SKILL.md")

    def router_settings() -> router.RouterSettings:
        mode = ctx.get_config("router_mode", default="shadow") or "shadow"
        return router.RouterSettings(
            mode=mode if mode in ("shadow", "live", "off") else "shadow",
            cheap_provider=ctx.get_config("router_cheap_provider", default="") or "",
            cheap_model=ctx.get_config("router_cheap_model", default="") or "",
            threshold=float(ctx.get_config("router_threshold", default=0.85) or 0.85))

    def verdict_for(text: str) -> router.Verdict:
        from agent.secret_scope import get_secret
        return router.judge(text, jev_key=get_secret("TYPESAFE_API_KEY") or "", llm=ctx.llm,
                            price=lambda model, use: usage.cost(prices, model, use))

    try:
        ctx.register_auxiliary_task(router.AUX_TASK, display_name="Homelab Watch route judge",
                                    description="Judges whether a subagent task can run on a cheaper model. "
                                                "Pick a small, cheap model here.")
    except Exception:  # without it the Hermes judge uses the active model, or the router falls back to rules
        logger.warning("homelab-watch: route judge task not registered", exc_info=True)
    try:
        from agent.delegation_provider import DelegationProvider
        ctx.register_delegation_provider(router.make_provider(
            DelegationProvider, get_settings=router_settings, verdict_for=verdict_for,
            record=lambda entry: get_watch().record_route(entry)))
    except Exception:  # an older Hermes without these seams still gets the monitor
        logger.warning("homelab-watch: cost router not registered", exc_info=True)

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
            rnd, targets = watch.check(alerts=cmd == "tick")
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

    def slash_route(words: list[str]) -> str:
        if words and words[0] in ("live", "shadow", "off"):
            ctx.set_config("router_mode", words[0])
        rs = router_settings()
        led = get_watch().usage_summary().get("route", {})
        cheap = rs.cheap_model or "no cheap model set (router_cheap_model)"
        return (f"Cost router: {rs.mode}, cheap model {cheap}, threshold {rs.threshold}. "
                f"{led.get('would_move', 0)} of {led.get('decisions', 0)} subagent tasks could run cheaper; "
                f"{led.get('moved', 0)} did. Select it with /delegation {router.BACKEND}.")

    def slash(raw_args: str = "", **_) -> str:
        words = raw_args.split()
        try:
            if words[:1] == ["alerts"]:
                return slash_alerts(words[1:])
            if words[:1] == ["route"]:
                return slash_route(words[1:])
            rnd, targets = get_watch().check()
        except TargetsError as exc:
            return f"Homelab Watch: {exc}"
        return " ".join(filter(None, [spoken_summary(rnd, targets), usage_sentence(get_watch().usage_summary())]))

    ctx.register_command("homelab", slash, description="Check the homelab now, or manage alerts",
                         args_hint="[alerts on [deliver] | alerts off | route live|shadow|off]")
