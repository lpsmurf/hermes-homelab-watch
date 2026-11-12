"""Hermes' own LLM usage: tokens per day and what they would have cost, split by how they were paid.

"Saved" is always API-equivalent dollars: what the same tokens cost at published list prices. A model with no
published price is counted as unpriced tokens, never estimated (the ax-route rule this table comes from).
"""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Any

PRICES_FILE = Path(__file__).parent / "prices.yaml"
KEEP_DAYS = 62
TOKEN_KEYS = ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens")

# Providers that bill a flat subscription, not per token. A user setting adds more.
SUBSCRIPTION_PROVIDERS = ("openai-codex", "copilot")
SUBSCRIPTION_PREFIXES = ("claude-subscription", "cursor-subscription", "antigravity")
LOCAL_HOSTS = ("localhost", "127.0.0.1", "[::1]", "0.0.0.0", ".local")

COUNTERS = ("saved_by_subscription", "saved_by_cheaper_model", "saved_by_free_model", "spent", "judge_cost")


def load_prices(extra: dict | None = None) -> dict[str, dict[str, float]]:
    from ruamel.yaml import YAML
    doc = YAML(typ="safe").load(PRICES_FILE.read_text(encoding="utf-8")) or {}
    prices = {}
    for section in doc.values():
        for model, row in (section or {}).items():
            prices[_norm(model)] = row
    for model, row in (extra or {}).items():
        prices[_norm(model)] = row
    return prices


def _norm(model: str) -> str:
    """'anthropic/claude-opus-5' and 'claude-opus-5' are the same price row; Nebius ids keep their org."""
    m = str(model or "").strip().lower()
    return m.removesuffix(":free")


def _row(prices: dict, model: str) -> dict | None:
    m = _norm(model)
    return prices.get(m) or prices.get(m.rsplit("/", 1)[-1])


def cost(prices: dict, model: str, usage: dict) -> float | None:
    row = _row(prices, model)
    if row is None or "input" not in row or "output" not in row:
        return None
    rate = {
        "input_tokens": row["input"],
        "output_tokens": row["output"],
        "cache_read_tokens": row.get("cache_read", row["input"]),
        "cache_write_tokens": row.get("cache_write", row["input"]),
    }
    return sum(float(usage.get(k) or 0) * rate[k] for k in TOKEN_KEYS) / 1_000_000


def billing_kind(provider: str, base_url: str, model: str, extra_subscriptions: tuple[str, ...] = ()) -> str:
    p, url, m = (provider or "").lower(), (base_url or "").lower(), (model or "").lower()
    if m.endswith(":free") or any(h in url for h in LOCAL_HOSTS) or p in ("ollama", "lmstudio", "llamacpp", "local"):
        return "free"
    if p in SUBSCRIPTION_PROVIDERS or p in extra_subscriptions or p.startswith(SUBSCRIPTION_PREFIXES):
        return "subscription"
    return "metered"


def _tokens(usage: dict) -> int:
    total = usage.get("total_tokens")
    if isinstance(total, (int, float)) and total > 0:
        return int(total)
    return int(sum(float(usage.get(k) or 0) for k in TOKEN_KEYS) + float(usage.get("reasoning_tokens") or 0))


def _day(now: float) -> str:
    return datetime.fromtimestamp(now).strftime("%Y-%m-%d")


def _empty_day() -> dict:
    return {"tokens": 0, "requests": 0, "unpriced_tokens": 0, "by_model": {}, **{c: 0.0 for c in COUNTERS}}


def record(state: dict, *, model: str, provider: str, base_url: str, usage: Any, prices: dict,
           baseline_model: str, extra_subscriptions: tuple[str, ...] = (), now: float | None = None) -> None:
    """Add one API request to today's counters. Ignores a request without usable token counts."""
    if not isinstance(usage, dict):
        return
    tokens = _tokens(usage)
    if tokens <= 0:
        return
    now = time.time() if now is None else now
    days = state.setdefault("usage", {})
    day = days.setdefault(_day(now), _empty_day())
    day["tokens"] += tokens
    day["requests"] += 1
    per_model = day["by_model"].setdefault(model or "unknown", {"tokens": 0, "requests": 0})
    per_model["tokens"] += tokens
    per_model["requests"] += 1

    kind = billing_kind(provider, base_url, model, extra_subscriptions)
    actual = cost(prices, model, usage)
    baseline = cost(prices, baseline_model, usage) if baseline_model else None
    if kind == "subscription":
        if actual is None:
            day["unpriced_tokens"] += tokens
        else:
            day["saved_by_subscription"] += actual
            if baseline is not None and baseline > actual:  # a cheaper model on the same plan frees plan quota
                day["saved_by_cheaper_model"] += baseline - actual
    elif kind == "free":
        if baseline is None:
            day["unpriced_tokens"] += tokens
        else:
            day["saved_by_free_model"] += baseline
    else:
        if actual is None:
            day["unpriced_tokens"] += tokens
        else:
            day["spent"] += actual
            if baseline is not None and baseline > actual:
                day["saved_by_cheaper_model"] += baseline - actual
    for old in sorted(days)[:-KEEP_DAYS]:
        del days[old]


def add_judge_cost(state: dict, dollars: float, now: float | None = None) -> None:
    """The router's own judge calls are a cost of saving; the summary nets them out."""
    day = state.setdefault("usage", {}).setdefault(_day(time.time() if now is None else now), _empty_day())
    day["judge_cost"] += max(0.0, dollars)


def _sum(days: list[dict]) -> dict:
    out = _empty_day()
    for d in days:
        for k in ("tokens", "requests", "unpriced_tokens", *COUNTERS):
            out[k] += d.get(k, 0)
        for m, v in d.get("by_model", {}).items():
            agg = out["by_model"].setdefault(m, {"tokens": 0, "requests": 0})
            agg["tokens"] += v["tokens"]
            agg["requests"] += v["requests"]
    out["saved_total"] = round(max(0.0, out["saved_by_subscription"] + out["saved_by_cheaper_model"]
                                   + out["saved_by_free_model"] - out["judge_cost"]), 4)
    for k in COUNTERS:
        out[k] = round(out[k], 4)
    return out


def summary(state: dict, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    days = state.get("usage", {})
    today = _day(now)
    month = today[:7]
    return {
        "today": _sum([days[today]] if today in days else []),
        "month": _sum([v for k, v in days.items() if k.startswith(month)]),
    }


def short_tokens(n: float) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}k"
    return str(int(n))
