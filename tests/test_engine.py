import json

import pytest

from homelab_watch.engine import DOWN, PENDING, UP, check_round
from homelab_watch.probes import ProbeResult, bitaxe_metrics, evaluate_bitaxe
from homelab_watch.report import alert_text, spoken_summary
from homelab_watch.service import Watch
from homelab_watch.targets import TargetsError, parse_targets
from homelab_watch.tools import make_handlers

TARGETS = """
defaults: {fail_after: 2}
targets:
  - {id: router, name: Router, check: ping, host: 10.0.0.1}
  - {id: nas, name: Umbrel, check: http, url: "http://10.0.0.2/", parent: router}
  - {id: plex, name: Plex, check: tcp, host: 10.0.0.2, port: 32400, parent: nas}
  - {id: site, name: Website, check: http, url: "https://example.com/"}
"""


def probe_with(down: set[str]):
    return lambda t: ProbeResult(t.id not in down, "down" if t.id in down else "ok")


def run(targets, state, down, now):
    return check_round(targets, state, probe=probe_with(down), now=now)


def test_one_failure_is_pending_two_are_down():
    targets, state = parse_targets(TARGETS), {}
    first = run(targets, state, {"site"}, 0)
    assert first.statuses["site"]["status"] == PENDING and not first.incidents
    second = run(targets, state, {"site"}, 60)
    assert second.statuses["site"]["status"] == DOWN
    assert [i.root for i in second.opened] == ["site"]


def test_router_outage_is_one_incident_with_children_affected():
    targets, state = parse_targets(TARGETS), {}
    run(targets, state, {"router", "nas", "plex"}, 0)
    rnd = run(targets, state, {"router", "nas", "plex"}, 60)
    assert [i.root for i in rnd.incidents] == ["router"]
    assert rnd.incidents[0].affected == ["nas", "plex"]
    text = alert_text(rnd, targets, now=120)
    assert text.count("🔴") == 1 and "Umbrel, Plex" in text


def test_alert_only_on_change_and_recovery():
    targets, state = parse_targets(TARGETS), {}
    for now in (0, 60):
        run(targets, state, {"site"}, now)
    assert alert_text(run(targets, state, {"site"}, 120), targets) == ""  # still down: silent
    back = run(targets, state, set(), 180)
    assert back.resolved == ["site"] and "🟢 Website is back up" in alert_text(back, targets)
    assert back.statuses["site"]["status"] == UP


def test_spoken_summary_all_good():
    targets = parse_targets(TARGETS)
    rnd = run(targets, {}, set(), 0)
    assert spoken_summary(rnd, targets) == "All good. 4 of 4 things are up."


@pytest.mark.parametrize("bad, message", [
    ("targets: [{id: a, check: nope, host: x}]", "check must be one of"),
    ("targets: [{id: a, check: http}]", "'url' is required"),
    ("targets: [{id: a, check: ping, host: x, parent: b}]", "parent 'b' is not a target"),
    ("targets: [{id: a, check: ping, host: x, parent: b}, {id: b, check: ping, host: y, parent: a}]", "loops"),
    ("targets: [{id: a, check: tcp, host: x}]", "'port' must be"),
])
def test_invalid_targets_name_the_problem(bad, message):
    with pytest.raises(TargetsError, match=message):
        parse_targets(bad)


def test_bitaxe_metrics_and_thresholds():
    m = bitaxe_metrics({"hashRate": 500.0, "temp": 70.5, "vrTemp": 55, "power": 12.0})
    assert m["efficiency_jth"] == 24.0
    assert evaluate_bitaxe(m, {"temp_max": 68, "hashrate_min_ghs": 400}) == ["chip 70.5°C over 68°C"]


def test_missed_heartbeat_raises_incident(tmp_path):
    (tmp_path / "targets.yaml").write_text("targets: []")
    watch = Watch(tmp_path / "targets.yaml", tmp_path / "state.json")
    watch.heartbeat("nightly-backup", every_minutes=10, now=0)
    rnd, _ = watch.check(now=5 * 60)
    assert not rnd.incidents
    rnd, targets = watch.check(now=25 * 60)
    assert [i.root for i in rnd.incidents] == ["heartbeat:nightly-backup"]


def test_status_tool_reports_missing_targets_file(tmp_path):
    handlers = make_handlers(lambda: Watch(tmp_path / "nope.yaml", tmp_path / "state.json"))
    assert "no targets file" in json.loads(handlers["homelab_status"]({}))["error"]
