"""Cost router: a delegation backend that sends a subagent to a cheaper model when a judge says it will do as well.

Main-chat turns are never touched: switching that model per turn breaks Hermes' per-conversation prompt cache.
Subagents (delegate_task) are the supported seam, and the place where cheap-tier work piles up on the
expensive model.

It ships in shadow mode: every task is judged and logged ("would have moved"), but runs on the normal route
until the user turns live mode on. Any judge failure means the normal route; the router never refuses a task.

Judges, in order: Jev with the user's own TypeSafe key; else Hermes' own LLM through a registered auxiliary
task (the user picks a cheap model for it); else local rules. The ledger keeps scores and sizes, never task text.
"""

from __future__ import annotations

import json
import re
import time
import urllib.request
from dataclasses import dataclass
from typing import Callable

BACKEND = "jev_route"
AUX_TASK = "route_judge"
JEV_URL = "https://api.typesafe.ai/v1/systemone"
MAX_TASK_CHARS = 4000
RECENT = 20

QUESTION = (
    "Can a small, fast, inexpensive language model complete this delegated task as well as a frontier model? "
    "Yes for lookups, summaries, extraction, classification, formatting, renaming or a small, well-specified "
    "edit. No for multi-step reasoning, architecture or design, debugging an unknown cause, security review, "
    "or anything where a subtle mistake is costly."
)

_EASY = re.compile(r"\b(summari[sz]e|list|extract|find|look ?up|count|format|rename|classify|translate|grep|read)\b", re.I)
_HARD = re.compile(r"\b(design|architect|debug|refactor|security|review|prove|plan|investigate|optimi[sz]e|why)\b", re.I)


@dataclass
class Verdict:
    p: float          # probability the cheap model is good enough
    judge: str        # jev | hermes | rules
    cost_usd: float = 0.0


def task_text(task: dict) -> str:
    return f"{task.get('goal') or ''}\n\n{task.get('context') or ''}".strip()[:MAX_TASK_CHARS]


def rules_judge(text: str) -> Verdict:
    easy, hard = len(_EASY.findall(text)), len(_HARD.findall(text))
    p = 0.5 + 0.15 * min(easy, 3) - 0.25 * min(hard, 2) - (0.2 if len(text) > 1500 else 0.0)
    return Verdict(round(min(0.95, max(0.0, p)), 2), "rules")


def jev_judge(text: str, api_key: str, timeout: float = 6.0) -> Verdict:
    body = {"model": "jev-latest", "state": text, "questions": {"cheap_ok": {"type": "noul", "instructions": QUESTION}}}
    req = urllib.request.Request(JEV_URL, data=json.dumps(body).encode(), method="POST", headers={
        "Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "User-Agent": "hermes-homelab-watch"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — fixed TypeSafe endpoint
        answer = json.loads(resp.read(65_536))
    return Verdict(float(answer["answers"]["cheap_ok"]["noul"]), "jev")


JUDGE_SCHEMA = {
    "type": "object",
    "properties": {"cheap_ok": {"type": "number", "minimum": 0, "maximum": 1}},
    "required": ["cheap_ok"],
}


def hermes_judge(text: str, llm, price: Callable[[str, dict], float | None]) -> Verdict:
    result = llm.complete_structured(
        instructions=f"{QUESTION} Answer with cheap_ok: the probability from 0 to 1 that the answer is yes.",
        input=[{"type": "text", "text": text}], json_schema=JUDGE_SCHEMA, schema_name="route_judge",
        max_tokens=50, temperature=0, task=AUX_TASK, purpose="homelab-watch cost router")
    if result.content_type != "json":
        raise ValueError("judge returned no JSON")
    use = result.usage
    dollars = getattr(use, "cost_usd", None)
    if dollars is None:
        dollars = price(result.model, {k: getattr(use, k, 0) or 0 for k in
                                       ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens")}) or 0.0
    return Verdict(float(result.parsed["cheap_ok"]), "hermes", float(dollars))


def judge(text: str, *, jev_key: str = "", llm=None, price=None) -> Verdict:
    """The best judge available; each failure falls through to the next, ending at local rules."""
    if jev_key:
        try:
            return jev_judge(text, jev_key)
        except Exception:
            pass
    if llm is not None:
        try:
            return hermes_judge(text, llm, price or (lambda *_: None))
        except Exception:
            pass
    return rules_judge(text)


@dataclass
class RouterSettings:
    mode: str = "shadow"          # shadow | live | off
    cheap_provider: str = ""
    cheap_model: str = ""
    threshold: float = 0.85

    @property
    def cheap_route(self) -> dict | None:
        return {"provider": self.cheap_provider, "model": self.cheap_model} if self.cheap_model else None


def decide(task: dict, default_route: dict, settings: RouterSettings, verdict_for: Callable[[str], Verdict]) -> tuple[dict, dict]:
    """(route to use, ledger entry). Shadow and off always return the default route."""
    if settings.mode == "off":
        return dict(default_route), {}
    text = task_text(task)
    verdict = verdict_for(text)
    would_move = verdict.p >= settings.threshold and settings.cheap_route is not None
    moved = would_move and settings.mode == "live"
    entry = {"t": round(time.time()), "p": round(verdict.p, 3), "judge": verdict.judge, "chars": len(text),
             "would_move": would_move, "moved": moved, "judge_cost": verdict.cost_usd}
    if moved:
        return {**settings.cheap_route, "label": f"cheap p={verdict.p:.2f}"}, entry
    return dict(default_route), entry


def add_decision(state: dict, entry: dict) -> None:
    if not entry:
        return
    led = state.setdefault("route", {"decisions": 0, "would_move": 0, "moved": 0, "recent": []})
    led["decisions"] += 1
    led["would_move"] += int(entry["would_move"])
    led["moved"] += int(entry["moved"])
    led["recent"] = (led["recent"] + [entry])[-RECENT:]


def make_provider(base_cls, *, get_settings: Callable[[], RouterSettings], verdict_for: Callable[[str], Verdict],
                  record: Callable[[dict], None]):
    """Build the DelegationProvider subclass at register time (the base class exists only inside Hermes)."""

    class CostRoute(base_cls):
        display_name = "Homelab Watch cost router"
        summary = "Sends simple subagent tasks to a cheaper model when a judge says it will do as well (shadow by default)."

        @property
        def name(self) -> str:
            return BACKEND

        def description(self, config):
            return "Subagent models are chosen automatically; write a clear goal and the router does the rest."

        def is_available(self) -> bool:
            return True

        def route_task(self, task, config):
            try:
                route, entry = decide(task, dict(config), get_settings(), verdict_for)
            except Exception:
                return dict(config)
            try:
                record(entry)
            except Exception:
                pass
            return route

    return CostRoute()
