"""Turn a check round into words: a spoken-style summary, alert text, and a structured status."""

from __future__ import annotations

import time

from .engine import DOWN, PENDING, Incident, Round
from .targets import Target
from .usage import short_tokens


def _ago(since: float, now: float) -> str:
    mins = int((now - since) // 60)
    if mins < 1:
        return "just now"
    if mins < 60:
        return f"{mins} minute{'s' * (mins != 1)} ago"
    hours = mins // 60
    return f"{hours} hour{'s' * (hours != 1)} ago"


def _incident_line(i: Incident, targets: dict[str, Target], now: float) -> str:
    line = f"{i.name} is down since {_ago(i.since, now)} ({i.detail})"
    if i.affected:
        names = ", ".join(targets[a].name for a in i.affected)
        line += f", taking {len(i.affected)} more with it: {names}"
    return line


def spoken_summary(rnd: Round, targets: dict[str, Target], now: float | None = None) -> str:
    """One or two short sentences, written to be read aloud (Home Assistant Assist, hermes-voice)."""
    now = time.time() if now is None else now
    if not rnd.incidents:
        pending = [targets[t].name for t, s in rnd.statuses.items() if s["status"] == PENDING]
        if pending:
            return f"Everything is up, but {', '.join(pending)} just failed a check. Watching it."
        return f"All good. {len(targets)} of {len(targets)} things are up."
    lines = [_incident_line(i, targets, now) for i in rnd.incidents]
    up = sum(1 for s in rnd.statuses.values() if s["status"] not in (DOWN, PENDING))
    return ". ".join(lines) + f". The other {up} are fine."


def alert_text(rnd: Round, targets: dict[str, Target], now: float | None = None) -> str:
    """Message for a delivery channel; empty when nothing opened or resolved (cron stays silent)."""
    now = time.time() if now is None else now
    parts = [f"🔴 {_incident_line(i, targets, now)}" for i in rnd.opened]
    parts += [f"🟢 {targets[r].name} is back up" for r in rnd.resolved if r in targets]
    return "\n".join(parts)


def usage_sentence(usage_summary: dict | None) -> str:
    today = (usage_summary or {}).get("today") or {}
    if not today.get("tokens"):
        return ""
    line = f"Hermes used {short_tokens(today['tokens'])} tokens today"
    if today.get("saved_total"):
        line += f" and saved about ${today['saved_total']:.2f} at API prices"
    return line + "."


def status_payload(rnd: Round, targets: dict[str, Target], usage_summary: dict | None = None) -> dict:
    return {
        "usage": usage_summary or {},
        "overall": rnd.overall,
        "incidents": [
            {"root": i.root, "name": i.name, "detail": i.detail, "since": i.since, "affected": i.affected}
            for i in rnd.incidents
        ],
        "targets": [
            {"id": tid, "name": t.name, "check": t.check, "parent": t.parent or None, **rnd.statuses[tid]}
            for tid, t in targets.items()
        ],
    }
