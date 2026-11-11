---
name: watch-my-agents
description: "Wire the user's cron jobs and agents into Homelab Watch heartbeats, so a job that silently stops is noticed."
version: 1.0.0
author: lpsmurf (HFSP Labs)
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [homelab, monitoring]
    related_skills: [add-targets]
---

# Notice when a job quietly stops

A cron job that dies rarely complains. This skill makes Homelab Watch notice: the job checks in by name
when it finishes, and two missed check-ins open an incident, alerted on Telegram like any other.

## Steps

1. List what exists: `hermes cron list`. Note each job's name, schedule and what it does.
2. Ask which ones matter. A nightly backup does; a reminder that fires once does not.
3. For each, work out the expected interval in minutes from its schedule (`every 1h` is 60, a daily job
   is 1440).
4. Add the check-in as the **last step of the job**, so it only fires when the work actually finished.
   The `homelab_heartbeat` tool takes `name` and `every_minutes`:
   - For an agent-run job, add a final line to its prompt: "When finished, call homelab_heartbeat with
     name '<job name>' and every_minutes <n>."
   - For a script job, end the script with `hermes -z "call homelab_heartbeat name=<job name>
     every_minutes=<n>"`, or keep it simple and let an agent job do the check-in.
5. A heartbeat target only appears after its **first** check-in. Run each job once by hand with
   `hermes cron run <job id>` so it exists, then confirm with `hermes homelab check`.
6. Missing two check-ins in a row raises the incident, so pick `every_minutes` as the real interval,
   not a generous one.

## Notes

- Never edit a job the user has not agreed to change. Show the change first.
- A job that runs only on demand has no sensible interval; leave it out.
