import json
import subprocess
import sys
import threading

from homelab_watch import alerts
from homelab_watch.service import Watch

TARGETS = "targets:\n  - {id: closed, name: Closed port, check: tcp, host: 127.0.0.1, port: 1, timeout: 1, fail_after: 1}\n"


class FakeCron:
    """Stands in for the cronjob_manage tool: keeps jobs in a list, answers like the real tool."""

    def __init__(self):
        self.jobs, self.calls = [], []

    def __call__(self, tool: str, args: dict) -> str:
        assert tool == "cronjob_manage"
        self.calls.append(args)
        if args["action"] == "list":
            return json.dumps({"success": True, "jobs": self.jobs})
        if args["action"] == "create":
            job = {"job_id": f"job{len(self.jobs) + 1}", "name": args["name"], "schedule": args["schedule"]}
            self.jobs.append(job)
            return json.dumps({"success": True, "job_id": job["job_id"], "deliver": args.get("deliver", "origin")})
        if args["action"] == "remove":
            self.jobs = [j for j in self.jobs if j["job_id"] != args["job_id"]]
            return json.dumps({"success": True})
        raise AssertionError(args)


def make_watch(tmp_path) -> Watch:
    (tmp_path / "targets.yaml").write_text(TARGETS)
    return Watch(tmp_path / "targets.yaml", tmp_path / "state.json")


def test_alerts_on_creates_one_no_agent_job_and_off_removes_it(tmp_path):
    cron, scripts = FakeCron(), tmp_path / "scripts"
    watch = make_watch(tmp_path)
    assert "Alerts on" in alerts.enable(cron, watch, scripts, "telegram")
    assert "already on" in alerts.enable(cron, watch, scripts, "telegram")
    created = [c for c in cron.calls if c["action"] == "create"]
    assert len(created) == 1
    assert created[0]["no_agent"] is True and created[0]["deliver"] == "telegram"
    assert (scripts / alerts.SCRIPT_NAME).is_file()
    assert "Alerts off" in alerts.disable(cron, scripts)
    assert not cron.jobs and not (scripts / alerts.SCRIPT_NAME).exists()


def test_generated_script_is_silent_until_something_changes(tmp_path):
    watch = make_watch(tmp_path)
    script = tmp_path / alerts.SCRIPT_NAME
    script.write_text(alerts.render_script(watch))
    run = lambda: subprocess.run([sys.executable, str(script)], capture_output=True, text=True, timeout=30)
    first = run()
    assert first.returncode == 0, first.stderr
    assert "🔴 Closed port is down" in first.stdout
    second = run()
    assert second.returncode == 0 and second.stdout == ""  # still down: nothing to post


def test_generated_script_fails_loudly_on_broken_targets(tmp_path):
    watch = make_watch(tmp_path)
    watch.targets_path.write_text("targets: [{id: x, check: nope}]")
    script = tmp_path / alerts.SCRIPT_NAME
    script.write_text(alerts.render_script(watch))
    proc = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, timeout=30)
    assert proc.returncode == 2 and "check must be one of" in proc.stderr


def test_concurrent_heartbeats_are_not_lost(tmp_path):
    (tmp_path / "targets.yaml").write_text("targets: []")
    watch = Watch(tmp_path / "targets.yaml", tmp_path / "state.json")
    threads = [threading.Thread(target=watch.heartbeat, args=(f"job{i}",)) for i in range(20)]
    threads += [threading.Thread(target=watch.check) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(watch.store.load()["heartbeats"]) == 20
