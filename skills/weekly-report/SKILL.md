---
name: weekly-report
description: "Write a plain-language weekly summary of the homelab: what broke, how long it took to recover, what the agents cost, what is quietly flaky."
version: 1.0.0
author: lpsmurf (HFSP Labs)
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [homelab, monitoring]
    related_skills: [add-targets]
---

# The weekly homelab report

A short, honest summary the user can read in a minute. Offer to schedule it for Monday morning with a
cron job once they like it.

## Where the facts come from

- **Incidents:** every alert Homelab Watch sent is saved by the alerts cron job under the Hermes cron
  output folder (`~/.hermes/cron/output/<job id>/`), one dated file per run, red messages for something
  that broke and green ones for recovery. Match each 🔴 to the next 🟢 for the same name to get a duration.
- **Right now:** `hermes homelab json` for current status and latency.
- **The bill:** the `usage` block in that same output: tokens, saved by subscription, saved by cheaper
  models and free models, spent, with month totals.

## What to write

1. **One sentence of headline.** "A quiet week" or "Plex was down twice, once for four hours."
2. **What broke**, newest first: the name, when, how long, and the root cause if it is known. Group
   repeats ("clawdrop.cloud failed 5 times, always a slow TLS handshake").
3. **What is quietly flaky:** targets that failed and recovered within minutes, more than twice. Suggest
   `homelab-watch:tune-thresholds` for those.
4. **The bill:** tokens used, and what the subscription and cheaper models absorbed, in API-equivalent
   dollars. Say it is API-equivalent. Never present an unpriced model's tokens as a dollar figure.
5. **One thing to do**, if there is one.

## Rules

- Quote only what the files say. If the alert history is empty, say there were no incidents rather than
  inventing a calm week, and say how far back the records go.
- Keep it short and in plain words.
