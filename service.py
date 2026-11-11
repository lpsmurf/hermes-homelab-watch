"""Where targets and state live, plus heartbeats; shared by the tools, the slash command and the CLI."""

from __future__ import annotations

import json
import os
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

try:
    import fcntl
    msvcrt = None
except ImportError:  # Windows
    fcntl = None
    import msvcrt

from . import router, usage
from .engine import Round, check_round, rollup
from .probes import ProbeResult, run_probe
from .targets import Target, load_targets

PLUGIN_ID = "homelab-watch"
HEARTBEAT_PREFIX = "heartbeat:"


def data_dir() -> Path:
    from plugins.plugin_storage import plugin_data_dir
    return Path(plugin_data_dir(PLUGIN_ID))


def scripts_dir() -> Path:
    """<hermes home>/scripts/, where cron script jobs must live; plugin_data_dir is <hermes home>/plugin-data/<id>."""
    return data_dir().parent.parent / "scripts"


class Store:
    """JSON state file, replaced atomically so a cron tick and a tool call never see half a write.

    Read-modify-write callers hold locked(): the alerts cron job and a chat tool call can run a round at the
    same moment, and without the lock one of them would drop the other's heartbeat or failure count.
    """

    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def locked(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path.with_suffix(".lock"), "a+") as fh:
            if fcntl is not None:
                fcntl.flock(fh, fcntl.LOCK_EX)
            elif msvcrt is not None:
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                if fcntl is not None:
                    fcntl.flock(fh, fcntl.LOCK_UN)
                elif msvcrt is not None:
                    fh.seek(0)
                    msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)

    def load(self) -> dict:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except json.JSONDecodeError:
            return {}  # a corrupt file only costs the flap-damping history

    def save(self, state: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".state-")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(state, fh)
        os.replace(tmp, self.path)


def heartbeat_targets(state: dict) -> dict[str, Target]:
    return {
        f"{HEARTBEAT_PREFIX}{name}": Target(id=f"{HEARTBEAT_PREFIX}{name}", name=f"{name} (heartbeat)",
                                            check="heartbeat", fail_after=1)
        for name in state.get("heartbeats", {})
    }


def heartbeat_probe(state: dict, now: float):
    def probe(t: Target) -> ProbeResult:
        if t.check != "heartbeat":
            return run_probe(t)
        hb = state["heartbeats"][t.id.removeprefix(HEARTBEAT_PREFIX)]
        late_after = hb["every_minutes"] * 60 * 2
        age = now - hb["last"]
        if age > late_after:
            return ProbeResult(False, f"no check-in for {int(age // 60)} minutes")
        return ProbeResult(True, f"checked in {int(age // 60)} minutes ago")
    return probe


class Watch:
    def __init__(self, targets_path: Path, state_path: Path):
        self.targets_path = targets_path
        self.store = Store(state_path)

    @classmethod
    def from_settings(cls, targets_file: str = "") -> "Watch":
        base = data_dir()
        return cls(Path(targets_file).expanduser() if targets_file else base / "targets.yaml", base / "state.json")

    def check(self, now: float | None = None) -> tuple[Round, dict[str, Target]]:
        now = time.time() if now is None else now
        configured = load_targets(self.targets_path)
        with self.store.locked():
            state = self.store.load()
            targets = {**configured, **heartbeat_targets(state)}
            rnd = check_round(targets, state, probe=heartbeat_probe(state, now), now=now)
            self.store.save(state)
        return rnd, targets

    def latest(self, max_age_s: float = 120, now: float | None = None) -> tuple[Round, dict[str, Target]]:
        """The last round's result without probing when every target was checked within max_age_s
        (the alerts job keeps it fresh); otherwise a real check. Lets the Desktop chip poll cheaply."""
        now = time.time() if now is None else now
        configured = load_targets(self.targets_path)
        with self.store.locked():
            state = self.store.load()
        targets = {**configured, **heartbeat_targets(state)}
        statuses = state.get("targets", {})
        fresh = all(now - statuses.get(tid, {}).get("checked_at", 0) <= max_age_s for tid in targets)
        if not fresh:
            return self.check(now=now)
        statuses = {tid: statuses[tid] for tid in targets}
        return Round(statuses=statuses, incidents=rollup(targets, statuses), opened=[], resolved=[]), targets

    def record_usage(self, **request) -> None:
        with self.store.locked():
            state = self.store.load()
            usage.record(state, **request)
            self.store.save(state)

    def usage_summary(self, now: float | None = None) -> dict:
        with self.store.locked():
            state = self.store.load()
        return {**usage.summary(state, now), "route": state.get("route", {})}

    def record_route(self, entry: dict) -> None:
        if not entry:
            return
        with self.store.locked():
            state = self.store.load()
            router.add_decision(state, entry)
            usage.add_judge_cost(state, entry.get("judge_cost", 0.0))
            self.store.save(state)

    def heartbeat(self, name: str, every_minutes: int = 60, now: float | None = None) -> dict:
        entry = {"last": time.time() if now is None else now, "every_minutes": max(1, int(every_minutes))}
        with self.store.locked():
            state = self.store.load()
            state.setdefault("heartbeats", {})[name] = entry
            self.store.save(state)
        return entry
