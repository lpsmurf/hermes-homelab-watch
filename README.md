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

## Alerts

`hermes homelab tick` prints only incidents that opened or resolved since the last run, and nothing
otherwise, so a `no_agent` cron job can run it every minute and deliver alerts without spending tokens.

## Development

```bash
uv venv .venv && uv pip install --python .venv/bin/python pytest ruamel.yaml
./test.sh
hermes plugins doctor . --ci
hermes plugins validate .
```

## Roadmap

- Alerts cron job set up by `hermes homelab alerts on`
- Hermes Desktop status-bar pane
- Home Assistant bridge: targets as HA sensors, for dashboards, automations and Assist voice
- Works with [hermes-voice](https://github.com/majorminorlabs/hermes-voice): its `safe` tool set can use
  `homelab_status` as-is

MIT licensed. Built by HFSP Labs (info@hfsp.xyz).
