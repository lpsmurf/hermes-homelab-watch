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

from homelab_watch.report import spoken_summary, status_payload  # noqa: E402
from homelab_watch.service import PLUGIN_ID, Watch  # noqa: E402
from homelab_watch.targets import TargetsError  # noqa: E402

router = APIRouter()


def _watch() -> Watch:
    from hermes_cli.config import load_config_readonly  # documented route for a plugin_api's own settings
    settings = (load_config_readonly().get("plugins", {}).get("entries", {}).get(PLUGIN_ID, {}) or {}).get("settings", {})
    return Watch.from_settings((settings or {}).get("targets_file") or "")


def _respond(run) -> dict:
    try:
        rnd, targets = run(_watch())
    except TargetsError as exc:
        return {"overall": "unconfigured", "error": str(exc), "incidents": [], "targets": []}
    return {**status_payload(rnd, targets), "summary": spoken_summary(rnd, targets)}


@router.get("/status")
def status() -> dict:
    return _respond(lambda w: w.latest())


@router.post("/check")
def check() -> dict:
    return _respond(lambda w: w.check())
