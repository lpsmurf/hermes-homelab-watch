"""One check round: probe every target, damp flapping, roll failures up to their root cause.

State is a plain dict so the caller decides where it lives (Hermes plugin state, a JSON file, a test).
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable

from .probes import ProbeResult, run_probe
from .targets import Target

UP, DOWN, PENDING = "up", "down", "pending"


@dataclass
class Incident:
    """A root-cause failure and the targets that are down only because it is."""

    root: str
    name: str
    detail: str
    since: float
    affected: list[str] = field(default_factory=list)


@dataclass
class Round:
    statuses: dict[str, dict]
    incidents: list[Incident]
    opened: list[Incident]
    resolved: list[str]

    @property
    def overall(self) -> str:
        if self.incidents:
            return "down"
        return "degraded" if any(s["status"] == PENDING for s in self.statuses.values()) else "up"


def _advance(prev: dict | None, result: ProbeResult, target: Target, now: float) -> dict:
    """Confirmed DOWN only after fail_after consecutive failures; one success is UP again."""
    fails = 0 if result.ok else (prev or {}).get("fails", 0) + 1
    if result.ok:
        status = UP
    elif fails >= target.fail_after:
        status = DOWN
    else:
        status = PENDING if (prev or {}).get("status") != DOWN else DOWN
    changed = (prev or {}).get("status") != status
    return {
        "status": status,
        "fails": fails,
        "detail": result.detail,
        "latency_ms": result.latency_ms,
        "metrics": result.metrics,
        "since": now if changed or prev is None else prev.get("since", now),
        "checked_at": now,
    }


def _down_ancestor(tid: str, targets: dict[str, Target], statuses: dict[str, dict]) -> str:
    """The highest down ancestor of tid, or '' when every ancestor is up."""
    root, cur = "", targets[tid].parent
    while cur:
        if statuses[cur]["status"] == DOWN:
            root = cur
        cur = targets[cur].parent
    return root


def rollup(targets: dict[str, Target], statuses: dict[str, dict]) -> list[Incident]:
    incidents: dict[str, Incident] = {}
    for tid in targets:
        if statuses[tid]["status"] != DOWN or _down_ancestor(tid, targets, statuses):
            continue
        s = statuses[tid]
        incidents[tid] = Incident(tid, targets[tid].name, s["detail"], s["since"])
    for tid in targets:
        root = _down_ancestor(tid, targets, statuses)
        if root and statuses[tid]["status"] in (DOWN, PENDING):
            incidents[root].affected.append(tid)
    return list(incidents.values())


def check_round(
    targets: dict[str, Target],
    state: dict,
    *,
    probe: Callable[[Target], ProbeResult] = run_probe,
    now: float | None = None,
    commit_alerts: bool = True,
) -> Round:
    """Probe all targets in parallel and update state in place.

    state["targets"] holds per-target status; state["open"] the root ids already alerted on, so a
    round reports only incidents that opened or resolved since the last one.
    """
    now = time.time() if now is None else now
    with ThreadPoolExecutor(max_workers=min(16, max(1, len(targets)))) as pool:
        results = dict(zip(targets, pool.map(probe, targets.values())))
    prev = state.get("targets", {})
    statuses = {tid: _advance(prev.get(tid), results[tid], t, now) for tid, t in targets.items()}
    incidents = rollup(targets, statuses)
    was_open = set(state.get("open", []))
    now_open = {i.root for i in incidents}
    state["targets"] = statuses
    if commit_alerts:  # only the alerting caller may mark incidents as told; a look must not eat an alert
        state["open"] = sorted(now_open)
    return Round(
        statuses=statuses,
        incidents=incidents,
        opened=[i for i in incidents if i.root not in was_open],
        resolved=sorted(was_open - now_open),
    )
