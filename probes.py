"""Read-only probes. Each returns a ProbeResult and never raises; none of them changes a device."""

from __future__ import annotations

import json
import platform
import socket
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Callable

from .targets import Target


@dataclass(frozen=True)
class ProbeResult:
    ok: bool
    detail: str
    latency_ms: float | None = None
    metrics: dict[str, float] = field(default_factory=dict)


def _elapsed(start: float) -> float:
    return round((time.monotonic() - start) * 1000, 1)


def _http_get(url: str, timeout: float) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": "hermes-homelab-watch"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — user-configured URL
        return resp.status, resp.read(262_144)


def probe_http(t: Target) -> ProbeResult:
    start = time.monotonic()
    try:
        status, _ = _http_get(t.url, t.timeout)
    except urllib.error.HTTPError as exc:
        status = exc.code
    except Exception as exc:
        return ProbeResult(False, f"no response ({_reason(exc)})")
    ok = status == t.expect_status if t.expect_status else 200 <= status < 400
    return ProbeResult(ok, f"HTTP {status}", _elapsed(start))


def probe_tcp(t: Target) -> ProbeResult:
    start = time.monotonic()
    try:
        with socket.create_connection((t.host, t.port), timeout=t.timeout):
            pass
    except Exception as exc:
        return ProbeResult(False, f"port {t.port} closed ({_reason(exc)})")
    return ProbeResult(True, f"port {t.port} open", _elapsed(start))


def probe_ping(t: Target) -> ProbeResult:
    wait = ["-W", str(int(t.timeout * 1000))] if platform.system() == "Darwin" else ["-W", str(max(1, int(t.timeout)))]
    start = time.monotonic()
    try:
        proc = subprocess.run(["ping", "-c", "1", *wait, t.host], capture_output=True, timeout=t.timeout + 2)
    except Exception as exc:
        return ProbeResult(False, f"ping failed ({_reason(exc)})")
    if proc.returncode != 0:
        return ProbeResult(False, "no ping reply")
    return ProbeResult(True, "ping reply", _elapsed(start))


def probe_dns(t: Target) -> ProbeResult:
    start = time.monotonic()
    try:
        addr = socket.gethostbyname(t.host)
    except Exception as exc:
        return ProbeResult(False, f"does not resolve ({_reason(exc)})")
    return ProbeResult(True, f"resolves to {addr}", _elapsed(start))


def bitaxe_metrics(info: dict) -> dict[str, float]:
    """AxeOS /api/system/info → hashrate (GH/s), chip/VR temperature (°C), power (W), efficiency (J/TH)."""
    out: dict[str, float] = {}
    for src, dst in (("hashRate", "hashrate_ghs"), ("temp", "temp_c"), ("vrTemp", "vr_temp_c"), ("power", "power_w")):
        value = info.get(src)
        if isinstance(value, (int, float)):
            out[dst] = round(float(value), 2)
    if out.get("hashrate_ghs") and "power_w" in out:
        out["efficiency_jth"] = round(out["power_w"] / (out["hashrate_ghs"] / 1000), 2)
    return out


# threshold key → (metric, breach test, label)
_BITAXE_LIMITS: dict[str, tuple[str, Callable[[float, float], bool], str]] = {
    "temp_max": ("temp_c", lambda v, lim: v > lim, "chip {v:g}°C over {lim:g}°C"),
    "vr_temp_max": ("vr_temp_c", lambda v, lim: v > lim, "VR {v:g}°C over {lim:g}°C"),
    "hashrate_min_ghs": ("hashrate_ghs", lambda v, lim: v < lim, "hashrate {v:g} GH/s under {lim:g}"),
    "efficiency_max_jth": ("efficiency_jth", lambda v, lim: v > lim, "{v:g} J/TH over {lim:g}"),
}


def evaluate_bitaxe(metrics: dict[str, float], thresholds: dict[str, float]) -> list[str]:
    breaches = []
    for key, limit in thresholds.items():
        rule = _BITAXE_LIMITS.get(key)
        if rule and rule[0] in metrics and rule[1](metrics[rule[0]], limit):
            breaches.append(rule[2].format(v=metrics[rule[0]], lim=limit))
    return breaches


def probe_bitaxe(t: Target) -> ProbeResult:
    start = time.monotonic()
    try:
        _, body = _http_get(f"http://{t.host}/api/system/info", t.timeout)
        info = json.loads(body)
    except Exception as exc:
        return ProbeResult(False, f"AxeOS API unreachable ({_reason(exc)})")
    metrics = bitaxe_metrics(info if isinstance(info, dict) else {})
    breaches = evaluate_bitaxe(metrics, t.thresholds)
    summary = ", ".join(f"{k}={v:g}" for k, v in metrics.items())
    return ProbeResult(not breaches, "; ".join(breaches) or summary, _elapsed(start), metrics)


PROBES: dict[str, Callable[[Target], ProbeResult]] = {
    "http": probe_http, "tcp": probe_tcp, "ping": probe_ping, "dns": probe_dns, "bitaxe": probe_bitaxe,
}


def run_probe(t: Target) -> ProbeResult:
    try:
        return PROBES[t.check](t)
    except Exception as exc:  # a probe bug must not take down the whole check round
        return ProbeResult(False, f"probe error ({_reason(exc)})")


def _reason(exc: BaseException) -> str:
    if isinstance(exc, urllib.error.URLError) and exc.reason:
        exc = exc.reason if isinstance(exc.reason, BaseException) else Exception(str(exc.reason))
    return f"{type(exc).__name__}: {exc}"[:160]
