# Homelab Watch

**Your homelab, your agents and your agent's bill, in one status chip.**

A Hermes Agent plugin that watches your homelab (router, home server, websites, a Bitaxe miner, your own
cron jobs), counts what Hermes spends on models and what it saved, and routes simple subagent work to a
cheaper model. It tells you what is wrong in one sentence. Failures roll up to the root cause: when the router
drops you get one alert ("Router is down, taking Plex and the miner with it"), not ten.

Every check is read-only (HTTP GET, TCP connect, ping, DNS lookup, the AxeOS info API). It never restarts,
reconfigures or updates a device.

## Install

```bash
hermes plugins install lpsmurf/hermes-homelab-watch
hermes plugins enable homelab-watch
hermes homelab init      # writes targets.yaml into the plugin's data folder
hermes homelab check
```

Then ask Hermes: *"Is everything OK at home?"*, *"Is Plex up?"*, *"How is the miner doing?"*

## Adding things to watch

Ask Hermes to load the bundled skill and it will walk you through it, find the addresses, set the
parents and verify each new target:

```
Use the homelab-watch:add-targets skill to add my NAS and the office printer.
```

## Targets

`targets.yaml` lists what to check. See [targets.example.yaml](targets.example.yaml).

| check | needs | ok when |
|---|---|---|
| `http` | `url`, optional `expect_status` | 2xx/3xx, or exactly `expect_status` |
| `tcp` | `host`, `port` | the port accepts a connection |
| `ping` | `host` | one echo reply |
| `dns` | `host` | the name resolves |
| `bitaxe` | `host`, optional `thresholds` | AxeOS answers and temp, VR temp, hashrate and J/TH are inside limits |

`parent` names what a target depends on. `fail_after` (default 2) is how many failures in a row count as
down, so one dropped packet does not page you.

## Tools

- `homelab_status`: checks now and returns a spoken-style summary, the root-cause incidents and, with
  `detail`, every target's status and metrics.
- `homelab_heartbeat`: a job checks in by name; missing two check-ins raises an incident.

Also: `/homelab` in any chat, and `hermes homelab check|tick|json|init`.

## Hermes Desktop

A status-bar chip, `● Home: All good · 78k tok · saved $0.22`, is green, amber or red. Click it for the
**Homelab** page (also in the sidebar): incidents first, then every target under its parent, with Bitaxe
metrics, latency and age, plus a **Check now** button and the Hermes card below. The chip polls every 30 s and
reuses the last check round, so polling never probes your devices.

The desktop half ships switched off, like every Hermes desktop plugin: Capabilities → Plugins → Rescan, then
switch Homelab Watch on. Restart the gateway after installing (`hermes gateway restart`) so the backend and the
token hook load.

## Tokens and savings

A `post_api_request` hook counts every model request's tokens per day (counts only, never prompt text) and
prices them with [`prices.yaml`](prices.yaml) (from [ax-route](https://github.com/lpsmurf/ax-route)). Savings
are **API-equivalent dollars**: what the same tokens cost at published list prices.

| Counter | Meaning |
|---|---|
| saved by subscription | a flat-plan provider (`openai-codex`, `copilot`, Claude/Cursor subscription plugins, or your own list) absorbed this list price |
| saved by cheaper models | the difference to your baseline model (default: your main model) for work done on a cheaper one |
| saved by free models | local models (Ollama, llama.cpp, LM Studio) and `:free` ids, at baseline price |
| spent | metered list price |
| unpriced | tokens on models with no published price, never estimated |

## Cost router

`jev_route` is a delegation backend: it decides which model each `delegate_task` subagent runs on. Your main
chat is never switched, since that would break Hermes' per-conversation prompt cache. Each subagent task gets
one question: *can a small, fast model do this as well as a frontier model?*

- **Judge:** Jev, if you add your own TypeSafe key in plugin settings; otherwise Hermes' own LLM through the
  **Homelab Watch route judge** auxiliary task (Settings → Models → Auxiliary; pick a cheap model); otherwise
  local rules. The judge's own cost is subtracted from the savings.
- **Shadow by default:** it logs "could run cheaper" and changes nothing. `/homelab route live` moves the tasks
  the judge clears (p ≥ `router_threshold`, default 0.85) to `router_cheap_provider`/`router_cheap_model`.
  Any judge failure keeps the normal route; it never refuses a task.

```bash
hermes config set delegation.backend jev_route
hermes config set plugins.entries.homelab-watch.settings.router_cheap_provider openai-codex
hermes config set plugins.entries.homelab-watch.settings.router_cheap_model gpt-5.6-luna
```

Tested live: a "list the three primary colours" subagent was judged p=0.99 and ran on `gpt-5.6-luna` instead
of `gpt-5.6-sol`.

## What it touches

- **Reads:** the URLs, hosts and ports in your `targets.yaml`; the token counts and model names Hermes passes to
  `post_api_request`.
- **Writes:** its state in the plugin data folder; with alerts on, one script in `scripts/` and one cron job.
- **Sends:** nothing by default. With a TypeSafe key and `delegation.backend: jev_route`, each subagent task's
  goal and context (up to 4,000 characters) go to `api.typesafe.ai` for one yes/no judgment. TypeSafe's
  policy says it does not train on customer data. Without a key, the judge is your own Hermes model.
- **Never:** prompt text in its ledger, telemetry, or changes to your devices.

## Alerts

```
/homelab alerts on telegram     # or discord, slack, local, platform:chat_id … (default: this chat)
/homelab alerts                 # is it on?
/homelab alerts off
```

`alerts on` writes `homelab_watch_tick.py` into your profile's `scripts/` folder and creates a cron job
named `homelab-watch alerts` through Hermes' own `cronjob_manage` tool (so it goes through your normal
approvals and shows in `hermes cron list`). It is a `no_agent` job: every minute it runs one check round
and posts only incidents that opened or resolved. A quiet minute sends nothing and no model is called.
If `targets.yaml` breaks, the job fails and Hermes delivers the failure instead of going silent.

The job runs the script with Hermes' Python outside the plugin loader, so it also works when plugins run
in the isolated plugin host. Cron jobs need the gateway running (`hermes gateway install`).

`hermes homelab tick` does the same from a shell.

## Development

```bash
uv venv .venv && uv pip install --python .venv/bin/python pytest ruamel.yaml
./test.sh
hermes plugins doctor . --ci
hermes plugins validate .
```

## Roadmap

- Home Assistant bridge: targets as HA sensors, for dashboards, automations and Assist voice
- Works with [hermes-voice](https://github.com/majorminorlabs/hermes-voice): its `safe` tool set can use
  `homelab_status` as-is

MIT licensed. Built by HFSP Labs (info@hfsp.xyz).
