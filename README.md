# Homelab Watch

A Hermes Agent plugin that watches your homelab (router, home server, websites, a Bitaxe miner, your own
cron jobs) and tells you what is wrong in one sentence. Failures roll up to the root cause: when the router
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

## What it touches

Reads only: the URLs, hosts and ports in your `targets.yaml`. Writes only: its state in the plugin data
folder, and, when you turn alerts on, one script in `scripts/` plus one cron job. No telemetry, no
third-party services, no credentials.

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

- Hermes Desktop status-bar pane
- Home Assistant bridge: targets as HA sensors, for dashboards, automations and Assist voice
- Works with [hermes-voice](https://github.com/majorminorlabs/hermes-voice): its `safe` tool set can use
  `homelab_status` as-is

MIT licensed. Built by HFSP Labs (info@hfsp.xyz).
