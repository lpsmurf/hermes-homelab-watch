import json

from homelab_watch import router
from homelab_watch.router import RouterSettings, Verdict, decide

DEFAULT = {"provider": "openai-codex", "model": "gpt-5.6-sol"}
TASK = {"goal": "Summarize the README into three bullet points", "context": "secret project notes"}
LIVE = RouterSettings(mode="live", cheap_provider="openrouter", cheap_model="small-model", threshold=0.85)


def fixed(p):
    return lambda _text: Verdict(p, "jev")


def test_live_moves_a_task_the_judge_clears():
    route, entry = decide(TASK, DEFAULT, LIVE, fixed(0.92))
    assert route["model"] == "small-model" and route["provider"] == "openrouter"
    assert entry["moved"] and entry["would_move"]


def test_live_keeps_a_task_below_threshold_on_the_default_route():
    route, entry = decide(TASK, DEFAULT, LIVE, fixed(0.6))
    assert route == DEFAULT and not entry["would_move"]


def test_shadow_never_changes_the_route_but_logs_what_would_move():
    shadow = RouterSettings(**{**LIVE.__dict__, "mode": "shadow"})
    route, entry = decide(TASK, DEFAULT, shadow, fixed(0.99))
    assert route == DEFAULT and entry["would_move"] and not entry["moved"]


def test_no_cheap_model_means_nothing_moves():
    route, entry = decide(TASK, DEFAULT, RouterSettings(mode="live"), fixed(0.99))
    assert route == DEFAULT and not entry["would_move"]


def test_off_skips_the_judge():
    calls = []
    route, entry = decide(TASK, DEFAULT, RouterSettings(mode="off"), lambda t: calls.append(t))
    assert route == DEFAULT and entry == {} and calls == []


def test_ledger_keeps_scores_not_task_text():
    state = {}
    _, entry = decide(TASK, DEFAULT, LIVE, fixed(0.9))
    router.add_decision(state, entry)
    blob = json.dumps(state)
    assert "README" not in blob and "secret" not in blob
    assert state["route"]["decisions"] == 1 and state["route"]["moved"] == 1


class BrokenLlm:
    def complete_structured(self, **_):
        raise RuntimeError("provider down")


def test_judge_falls_through_to_rules_when_jev_and_llm_fail(monkeypatch):
    def boom(*_a, **_k):
        raise OSError("no network")
    monkeypatch.setattr(router, "jev_judge", boom)
    v = router.judge("Summarize and list the files", jev_key="k", llm=BrokenLlm())
    assert v.judge == "rules" and 0 <= v.p <= 1


def test_rules_judge_leans_cheap_for_lookups_and_expensive_for_design():
    assert router.rules_judge("List and summarize the changed files").p > router.rules_judge(
        "Design the architecture and debug why the security review failed").p


class FakeResult:
    content_type, parsed, model = "json", {"cheap_ok": 0.9}, "small-model"

    class usage:
        cost_usd = 0.0004


class FakeLlm:
    def complete_structured(self, **kwargs):
        assert kwargs["task"] == router.AUX_TASK
        return FakeResult()


def test_hermes_judge_reports_its_own_cost():
    v = router.judge("Summarize this", llm=FakeLlm())
    assert v.judge == "hermes" and v.p == 0.9 and v.cost_usd == 0.0004
