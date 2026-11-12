---
name: tune-thresholds
description: "Stop false alarms: find targets that flap or answer slowly and propose better timeout and fail_after values."
version: 1.0.0
author: lpsmurf (HFSP Labs)
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [homelab, monitoring]
    related_skills: [add-targets]
---

# Quieter alerts without missing real ones

A target that fails and recovers in minutes is usually slow, not down. The fix is a longer `timeout` or a
higher `fail_after`, not deleting it.

## Steps

1. **Find the noisy ones.** Read the alert history under `~/.hermes/cron/output/<job id>/`. A target with
   several 🔴/🟢 pairs only minutes apart is flapping.
2. **Measure its real speed.** Take about ten readings, ten seconds apart, with
   `hermes homelab json` (the `latency_ms` of that target), or
   `curl -s -o /dev/null -m 20 -w '%{time_total}' <url>` in a loop.
3. **Choose values:**
   - `timeout`: the slowest normal reading, doubled, with a floor of 5 seconds.
   - `fail_after`: 2 for a target that should never blip, 3 for most, 4 for one on a bad link.
     Remember a check runs every minute, so `fail_after: 3` means about three minutes of real failure
     before an alert.
4. **Show the change** (old and new values, the reason) and apply it to that one target in
   `targets.yaml`. Keep a `.bak` copy first.
5. **Run `hermes homelab check`** to confirm the file still loads.

## Do not

- Raise `fail_after` on something critical just to stop noise: that delays real alerts.
- Tune a target that is genuinely down. Use `homelab-watch:diagnose` for that.
- Change more than one target without saying so.
