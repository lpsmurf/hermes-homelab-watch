---
name: bitaxe-advice
description: "Read a Bitaxe miner's live numbers from Homelab Watch and suggest safe changes. It advises; it never changes the miner by itself."
version: 1.0.0
author: lpsmurf (HFSP Labs)
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [homelab, monitoring]
    related_skills: [add-targets]
---

# Bitaxe: read the numbers, advise carefully

Homelab Watch reads a Bitaxe's AxeOS info endpoint: hashrate, chip temperature, power, and the derived
efficiency in joules per terahash. This skill turns those readings into advice.

## Read

`hermes homelab json`, then the miner's `metrics`: `hashrate_ghs`, `temp_c`, `vr_temp_c` (0 means the
board has no sensor), `power_w`, `efficiency_jth`.

## What the numbers mean

- **Temperature:** under about 65 °C is comfortable; above 70 °C is a reason to act now.
- **Efficiency:** lower J/TH is better. Compare with the user's own earlier readings, not with someone
  else's miner, because boards differ.
- **Hashrate far below normal with normal power** usually points to heat throttling or unstable settings.
- **Hashrate zero** means the pool connection or the network, not the chip: check the target's parent
  first with `homelab-watch:diagnose`.

## Advising

Suggest one change at a time, say what it should do, and say what to watch afterwards. Typical ones:
improve airflow, lower the frequency a step if it is hot, or check the pool address.

Changing voltage or frequency writes to the device. **Do not do it yourself without an explicit yes**, and
never push a setting the user has not seen. If the user already has a `bitaxe-tune` skill installed, hand
the change to it. Afterwards, wait several minutes and read the numbers again before calling it good.

Thresholds (`temp_max`, `hashrate_min_ghs`, `efficiency_max_jth`) live on the miner's entry in
`targets.yaml`; update them to match the new settings so alerts stay meaningful.
