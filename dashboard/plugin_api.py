"""Backend for the Desktop half: GET /api/plugins/homelab-watch/status (cheap, polled by the status-bar chip)
and POST /api/plugins/homelab-watch/check (a real check round, for the page's "Check now" button).

The gateway imports this file on its own, outside the plugin loader, so it loads the plugin package the same
way the alerts cron script does.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from fastapi import APIRouter

_ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("homelab_watch_cron_tick", _ROOT / "cron_tick.py")
_tick = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_tick)
_tick._load_package(_ROOT)

from homelab_watch.report import spoken_summary, status_payload, usage_sentence  # noqa: E402
from homelab_watch.service import PLUGIN_ID, Watch  # noqa: E402
from homelab_watch import scan as netscan  # noqa: E402
from homelab_watch.targets import TargetsError, load_targets  # noqa: E402

router = APIRouter()


def _watch() -> Watch:
    from hermes_cli.config import load_config_readonly  # documented route for a plugin_api's own settings
    settings = (load_config_readonly().get("plugins", {}).get("entries", {}).get(PLUGIN_ID, {}) or {}).get("settings", {})
    return Watch.from_settings((settings or {}).get("targets_file") or "")


def _respond(run) -> dict:
    try:
        watch = _watch()
        rnd, targets = run(watch)
    except TargetsError as exc:
        return {"overall": "unconfigured", "error": str(exc), "incidents": [], "targets": []}
    used = watch.usage_summary()
    return {**status_payload(rnd, targets, used),
            "summary": " ".join(filter(None, [spoken_summary(rnd, targets), usage_sentence(used)]))}


@router.get("/status")
def status() -> dict:
    return _respond(lambda w: w.latest())


@router.post("/check")
def check() -> dict:
    return _respond(lambda w: w.check())


def _known_hosts(watch: Watch) -> set[str]:
    try:
        return {h for tg in load_targets(watch.targets_path).values() for h in (tg.host,) if h}
    except TargetsError:
        return set()


@router.get("/scan/plan")
def scan_plan() -> dict:
    """The real local networks a scan could cover, so the page can ask first. Sends nothing to the network."""
    try:
        return {"networks": netscan.local_networks()}
    except TargetsError as exc:
        return {"error": str(exc)}


@router.post("/scan")
def scan_network(body: dict) -> dict:
    """Scan one of the networks the plan listed. Anything else is refused."""
    try:
        chosen = next((n for n in netscan.local_networks() if n["range"] == body.get("range")), None)
        if chosen is None:
            return {"error": "That is not one of this computer's networks."}
        import ipaddress
        return netscan.scan(_known_hosts(_watch()), ipaddress.ip_network(chosen["range"]), chosen["gateway"])
    except TargetsError as exc:
        return {"error": str(exc)}


@router.post("/scan/add")
def scan_add(body: dict) -> dict:
    """Append the devices the user ticked to targets.yaml, then check them once."""
    picks = [p for p in body.get("devices", []) if isinstance(p, dict) and p.get("ip") and p.get("check")]
    if not picks:
        return {"error": "Nothing selected."}
    watch = _watch()
    try:
        netscan.add_to_file(watch.targets_path, picks, str(body.get("gateway") or ""))
        rnd, _ = watch.check()
    except TargetsError as exc:
        return {"error": str(exc)}
    return {"added": len(picks), "overall": rnd.overall}
