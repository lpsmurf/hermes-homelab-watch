---
name: add-targets
description: "Add machines, services and whole networks to Homelab Watch: find what is reachable, write targets.yaml with the right parents, and verify."
version: 1.0.0
author: lpsmurf (HFSP Labs)
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [homelab, monitoring, network, setup, targets]
    related_skills: []
---

# Add things for Homelab Watch to watch

Use this when someone wants Homelab Watch to cover more of their network: a new server, a NAS, a
printer, a VPS, a website, a smart plug, or everything on their LAN at once.

The whole job is one file. `targets.yaml` is the only thing that decides what gets checked, so this
skill is about filling it in correctly and proving each new line works.

## Before you touch anything

1. **Find the file.** `hermes homelab init` creates it if it does not exist and prints the path. It
   lives in the plugin's data directory, or wherever `targets_file` points in plugin settings.
2. **Read what is already there** before adding, so you match the existing ids and indentation and
   never duplicate a target.
3. **Keep a copy.** Copy the file to `targets.yaml.bak` first. A malformed file stops every check.

## Rules that keep this safe

- **Only the user's own machines.** Never add, probe or scan an address the user has not said is
  theirs. If they ask you to watch a third party's host, add it as an `http` check of a public URL
  only, which is no more than a browser does.
- **Every check is read-only.** `http` is a GET, `tcp` is a connect-and-close, `ping` is one echo,
  `dns` is a lookup, `bitaxe` is a GET of AxeOS's info endpoint. Never add anything that writes,
  restarts or logs in.
- **Ask before scanning a subnet.** A sweep of 254 addresses is noisy and some networks treat it as
  hostile. Offer it, name the range you would scan, and wait for a yes.
- **Credentials never go in this file.** It holds hostnames and ports. A target that needs a login
  is out of scope; say so rather than inventing a way around it.

## The shape of an entry

```yaml
defaults: {timeout: 10, fail_after: 3}   # seconds per check; failures in a row before "down"

targets:
  - {id: router, name: Router, check: ping, host: 192.168.1.1}
  - {id: nas, name: Synology NAS, check: http, url: "http://192.168.1.20:5000/", parent: router}
  - {id: vps, name: Hetzner VPS, check: tcp, host: 203.0.113.10, port: 22, parent: internet}
```

| field | meaning |
|---|---|
| `id` | short, unique, lowercase; other entries refer to it by this |
| `name` | what the user calls it; this is what alerts and the page say |
| `check` | `http`, `tcp`, `ping`, `dns`, or `bitaxe` |
| `host` / `url` / `port` | `url` for `http`; `host` for the rest; `port` as well for `tcp` |
| `expect_status` | optional, for `http`: an exact status code instead of any 2xx/3xx |
| `parent` | the id of the thing it depends on — this is the important one |
| `timeout`, `fail_after` | override the defaults for a slow or flappy target |
| `thresholds` | `bitaxe` only: `temp_max`, `vr_temp_max`, `hashrate_min_ghs`, `efficiency_max_jth` |

## Common things people watch, and how

| What | Check | Typical entry |
|---|---|---|
| SSH on any machine | `tcp` port 22 | `{id: vps, name: VPS, check: tcp, host: 203.0.113.10, port: 22}` |
| A Tailscale machine | `ping` or `tcp` on its tailnet name | `{id: ts-nas, name: NAS over Tailscale, check: ping, host: nas.tail1234.ts.net}` |
| Proxmox | `http` port 8006 | `{id: pve, name: Proxmox, check: http, url: "https://192.168.1.5:8006/"}` |
| Home Assistant | `http` port 8123 | `{id: hass, name: Home Assistant, check: http, url: "http://192.168.1.6:8123/"}` |
| Synology / QNAP NAS | `http` port 5000 or 5001 | `{id: nas, name: NAS, check: http, url: "http://192.168.1.20:5000/"}` |
| Plex | `http` `/identity` on 32400 | `{id: plex, name: Plex, check: http, url: "http://192.168.1.20:32400/identity", parent: nas}` |
| Jellyfin | `http` port 8096 | `{id: jellyfin, name: Jellyfin, check: http, url: "http://192.168.1.20:8096/", parent: nas}` |
| Pi-hole or AdGuard | `dns` plus `http` for the admin page | `{id: pihole, name: Pi-hole, check: dns, host: example.com}` |
| Docker app behind a port | `http` or `tcp` on that port | `{id: portainer, name: Portainer, check: http, url: "https://192.168.1.20:9443/", parent: nas}` |
| Grafana | `http` port 3000 | `{id: grafana, name: Grafana, check: http, url: "http://192.168.1.20:3000/", parent: nas}` |
| UniFi controller | `http` port 8443 | `{id: unifi, name: UniFi, check: http, url: "https://192.168.1.2:8443/", parent: router}` |
| A database | `tcp` 5432, 3306, 6379 | `{id: pg, name: Postgres, check: tcp, host: 192.168.1.20, port: 5432, parent: nas}` |
| A game or Minecraft server | `tcp` on its port | `{id: mc, name: Minecraft, check: tcp, host: 192.168.1.20, port: 25565, parent: nas}` |
| A website | `http` on the public URL | `{id: site, name: My site, check: http, url: "https://example.com", parent: internet}` |
| A printer or camera | `ping`, or `http` if it has a web page | `{id: printer, name: Printer, check: ping, host: 192.168.1.30, parent: router}` |
| A Bitaxe miner | `bitaxe` | `{id: bitaxe, name: Bitaxe, check: bitaxe, host: 192.168.1.80, parent: router}` |

Two notes on these:

- **A self-signed certificate is fine.** Proxmox, UniFi and most NAS boxes serve HTTPS with their own
  certificate. The check follows what the server returns, so it reports `up` as long as the page answers.
- **Tailscale names work anywhere the machine is signed in.** A tailnet name like `nas.tail1234.ts.net`
  reaches the box from any network, so it keeps working when the user is away from home. Use a plain LAN
  address instead when they only care about it from home.

## Getting `parent` right

This is what makes the plugin worth using. When a target goes down, everything beneath it is folded
into one incident instead of alerting separately.

Ask: *if this thing broke, what else would stop answering?* Then make it the parent of those.

- Everything on the LAN hangs off the **router**.
- A service hangs off the **machine it runs on** (Plex under the NAS, not under the router).
- Public websites and remote servers hang off an **internet check**, so a dropped line reads as one
  outage rather than every site failing at once.
- A target with no `parent` stands alone and is reported on its own.

A parent that does not exist, or a loop, is rejected with the target named, so a mistake here is
loud rather than silent.

## Working through it

1. **Ask what they want watched**, in their words: "the NAS", "my sites", "the office printer".
2. **Turn each into an address.** Ask for it, or offer to look:
   - the default gateway: `route -n get default` on macOS, `ip route` on Linux
   - names the machine already knows: `arp -a`
   - whether a port answers before you add it: `nc -z -G 3 <host> <port>`
   - whether a URL answers: `curl -s -o /dev/null -m 10 -w '%{http_code}' <url>`
3. **Choose the check.** A web interface is `http`. SSH, a database or a game server is `tcp`. A
   device with no open port is `ping`. A domain you want resolved is `dns`. A Bitaxe miner is
   `bitaxe`, which also reports hashrate, temperature and J/TH.
4. **Write the entries**, grouped under a comment, with parents set.
5. **Verify** with `hermes homelab check`. Every new target should read `up`. A target that is
   `down` on the first run is usually the wrong port or a device that does not answer ping.
6. **Tune what flaps.** A site that is slow from here needs a bigger `timeout`; a device that drops
   the odd packet needs a bigger `fail_after`. Do not solve flapping by deleting the target.
7. **Show the result**: `hermes homelab check`, and tell them which targets are now watched.

## Adding a whole LAN at once

Only with an explicit yes, and only on their own network.

1. Get the range from the default route, for example `192.168.1.0/24`.
2. Find what is alive. `arp -a` costs nothing and lists what the machine has already talked to.
   A full sweep is `for i in $(seq 1 254); do ping -c1 -W 300 192.168.1.$i >/dev/null 2>&1 && echo
   192.168.1.$i; done` — say it will take about a minute.
3. For each address found, see whether it serves a web interface on 80, 443, 8080 or 8006 before
   defaulting to `ping`.
4. **Propose the list and let them name things.** "192.168.1.42" is a bad target name; "Office
   printer" is a good one. Drop anything they do not recognise rather than guessing.
5. Set `parent: <router id>` on all of them and verify.

## Afterwards

- Alerts: `/homelab alerts on telegram` posts only when an incident opens or resolves.
- Heartbeats: a cron job or agent can check in by name with the `homelab_heartbeat` tool, and two
  missed check-ins open an incident.
- The Desktop chip and the `/homelab` page pick new targets up on their next refresh.
