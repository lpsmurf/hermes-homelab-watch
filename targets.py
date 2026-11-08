"""Load and validate targets.yaml — the single source of what Homelab Watch checks."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CHECK_KINDS = ("http", "tcp", "ping", "dns", "bitaxe")

DEFAULTS = {"timeout": 5.0, "fail_after": 2}


class TargetsError(ValueError):
    """targets.yaml is missing, malformed or inconsistent; the message names the target and field."""


@dataclass(frozen=True)
class Target:
    id: str
    name: str
    check: str
    host: str = ""
    port: int = 0
    url: str = ""
    expect_status: int = 0  # 0 = any 2xx/3xx
    parent: str = ""
    tags: tuple[str, ...] = ()
    timeout: float = DEFAULTS["timeout"]
    fail_after: int = DEFAULTS["fail_after"]
    thresholds: dict[str, float] = field(default_factory=dict)


def _load_yaml(text: str) -> Any:
    from ruamel.yaml import YAML  # ships with Hermes; the plugin guide's documented YAML reader
    return YAML(typ="safe").load(text)


def _require(raw: dict, key: str, tid: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise TargetsError(f"target {tid!r}: '{key}' is required for check '{raw.get('check')}'")
    return value.strip()


def _build(raw: Any, defaults: dict, index: int) -> Target:
    if not isinstance(raw, dict):
        raise TargetsError(f"targets[{index}] must be a mapping")
    tid = str(raw.get("id") or "").strip()
    if not tid:
        raise TargetsError(f"targets[{index}]: 'id' is required")
    check = str(raw.get("check") or "").strip()
    if check not in CHECK_KINDS:
        raise TargetsError(f"target {tid!r}: check must be one of {', '.join(CHECK_KINDS)}")
    fields: dict[str, Any] = {}
    if check == "http":
        fields["url"] = _require(raw, "url", tid)
        fields["expect_status"] = int(raw.get("expect_status") or 0)
    elif check == "tcp":
        fields["host"] = _require(raw, "host", tid)
        fields["port"] = int(raw.get("port") or 0)
        if not 0 < fields["port"] < 65536:
            raise TargetsError(f"target {tid!r}: 'port' must be 1-65535 for check 'tcp'")
    else:  # ping, dns, bitaxe take a host (dns: the name to resolve)
        fields["host"] = _require(raw, "host", tid)
    thresholds = raw.get("thresholds") or {}
    if not isinstance(thresholds, dict):
        raise TargetsError(f"target {tid!r}: 'thresholds' must be a mapping")
    return Target(
        id=tid,
        name=str(raw.get("name") or tid),
        check=check,
        parent=str(raw.get("parent") or "").strip(),
        tags=tuple(str(t) for t in raw.get("tags") or ()),
        timeout=float(raw.get("timeout", defaults["timeout"])),
        fail_after=max(1, int(raw.get("fail_after", defaults["fail_after"]))),
        thresholds={str(k): float(v) for k, v in thresholds.items()},
        **fields,
    )


def _check_parents(targets: dict[str, Target]) -> None:
    for t in targets.values():
        if t.parent and t.parent not in targets:
            raise TargetsError(f"target {t.id!r}: parent {t.parent!r} is not a target")
    for t in targets.values():
        seen, cur = {t.id}, t
        while cur.parent:
            if cur.parent in seen:
                raise TargetsError(f"target {t.id!r}: parent chain loops back to {cur.parent!r}")
            seen.add(cur.parent)
            cur = targets[cur.parent]


def parse_targets(text: str) -> dict[str, Target]:
    """Parse targets.yaml text into targets keyed by id, in file order."""
    try:
        doc = _load_yaml(text) or {}
    except Exception as exc:
        raise TargetsError(f"targets.yaml is not valid YAML: {exc}") from exc
    if not isinstance(doc, dict):
        raise TargetsError("targets.yaml must be a mapping with a 'targets' list")
    defaults = {**DEFAULTS, **(doc.get("defaults") or {})}
    raw_targets = doc.get("targets") or []
    if not isinstance(raw_targets, list):
        raise TargetsError("'targets' must be a list")
    targets: dict[str, Target] = {}
    for i, raw in enumerate(raw_targets):
        t = _build(raw, defaults, i)
        if t.id in targets:
            raise TargetsError(f"target id {t.id!r} appears twice")
        targets[t.id] = t
    _check_parents(targets)
    return targets


def load_targets(path: Path) -> dict[str, Target]:
    if not path.is_file():
        raise TargetsError(f"no targets file at {path} — copy targets.example.yaml there to start")
    return parse_targets(path.read_text(encoding="utf-8"))
