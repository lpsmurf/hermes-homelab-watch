"""Tool handlers. Each returns a JSON string and never raises."""

from __future__ import annotations

import json
from typing import Callable

from .report import spoken_summary, status_payload
from .service import Watch
from .targets import TargetsError


def make_handlers(get_watch: Callable[[], Watch]) -> dict[str, Callable[..., str]]:
    def homelab_status(args: dict, **_) -> str:
        try:
            rnd, targets = get_watch().check()
        except TargetsError as exc:
            return json.dumps({"error": str(exc)})
        except Exception as exc:
            return json.dumps({"error": f"check failed: {type(exc).__name__}: {exc}"})
        wanted = str(args.get("target") or "").strip().lower()
        if wanted:
            match = next((t for t in targets.values() if wanted in (t.id.lower(), t.name.lower())), None)
            if match is None:
                return json.dumps({"error": f"no target named {wanted!r}", "targets": list(targets)})
            return json.dumps({"target": match.id, "name": match.name, **rnd.statuses[match.id]})
        out = {"summary": spoken_summary(rnd, targets), "overall": rnd.overall}
        payload = status_payload(rnd, targets)
        out["incidents"] = payload["incidents"]
        if args.get("detail"):
            out["targets"] = payload["targets"]
        return json.dumps(out)

    def homelab_heartbeat(args: dict, **_) -> str:
        name = str(args.get("name") or "").strip()
        if not name:
            return json.dumps({"error": "name is required"})
        try:
            entry = get_watch().heartbeat(name, int(args.get("every_minutes") or 60))
        except Exception as exc:
            return json.dumps({"error": f"heartbeat failed: {type(exc).__name__}: {exc}"})
        return json.dumps({"ok": True, "name": name, **entry})

    return {"homelab_status": homelab_status, "homelab_heartbeat": homelab_heartbeat}
