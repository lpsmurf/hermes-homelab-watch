from datetime import datetime

import pytest

from homelab_watch import usage
from homelab_watch.report import usage_sentence

PRICES = {
    "big-model": {"input": 10, "output": 50},
    "small-model": {"input": 1, "output": 5},
}
ONE_M_EACH = {"input_tokens": 1_000_000, "output_tokens": 1_000_000}  # big = $60, small = $6
NOON = datetime(2026, 11, 11, 12).timestamp()


def rec(state, model, provider="openrouter", base_url="", now=NOON, use=ONE_M_EACH, baseline="big-model"):
    usage.record(state, model=model, provider=provider, base_url=base_url, usage=use, prices=PRICES,
                 baseline_model=baseline, now=now)


def today(state, now=NOON):
    return usage.summary(state, now)["today"]


def test_subscription_saves_what_the_plan_absorbed():
    state = {}
    rec(state, "big-model", provider="openai-codex")
    t = today(state)
    assert t["saved_by_subscription"] == 60 and t["spent"] == 0 and t["saved_total"] == 60


def test_cheaper_metered_model_saves_the_difference_to_the_baseline():
    state = {}
    rec(state, "small-model")
    t = today(state)
    assert t["spent"] == 6 and t["saved_by_cheaper_model"] == 54


def test_free_local_model_saves_the_baseline_price():
    state = {}
    rec(state, "llama3", base_url="http://localhost:11434/v1")
    rec(state, "small-model:free")
    t = today(state)
    assert t["saved_by_free_model"] == 120 and t["spent"] == 0 and t["unpriced_tokens"] == 0


def test_unpriced_model_counts_tokens_but_no_dollars():
    state = {}
    rec(state, "mystery-model")
    t = today(state)
    assert t["tokens"] == 2_000_000 and t["unpriced_tokens"] == 2_000_000 and t["spent"] == 0 and t["saved_total"] == 0


def test_judge_cost_is_netted_out_of_savings():
    state = {}
    rec(state, "small-model")
    usage.add_judge_cost(state, 4, now=NOON)
    assert today(state)["saved_total"] == 50


def test_days_roll_over_and_the_month_adds_them_up():
    state = {}
    rec(state, "small-model", now=NOON)
    tomorrow = NOON + 86_400
    rec(state, "small-model", now=tomorrow)
    assert today(state, tomorrow)["requests"] == 1
    assert usage.summary(state, tomorrow)["month"]["requests"] == 2


@pytest.mark.parametrize("bad", [None, "x", {}, {"input_tokens": 0}])
def test_bad_usage_payloads_are_ignored(bad):
    state = {}
    rec(state, "small-model", use=bad)
    assert today(state)["requests"] == 0


def test_provider_prefixed_ids_find_their_price_and_shipped_table_loads():
    assert usage.cost(PRICES, "vendor/small-model", ONE_M_EACH) == 6
    prices = usage.load_prices()
    assert usage.cost(prices, "claude-opus-5", ONE_M_EACH) == 30


def test_usage_sentence():
    state = {}
    rec(state, "big-model", provider="openai-codex")
    assert usage_sentence(usage.summary(state, NOON)) == "Hermes used 2.0M tokens today and saved about $60.00 at API prices."
