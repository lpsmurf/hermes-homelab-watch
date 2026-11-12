"""First-run welcome. Installing the plugin leaves nothing to watch, which is confusing on its own.

Once, in the first session after install where no targets file exists, a note is added to the turn asking
Hermes to greet the user and offer to set the plugin up. It is shown at most once, never interrupts a turn,
and goes quiet for good as soon as a targets file exists.
"""

from __future__ import annotations

FLAG = "welcomed"

WELCOME = """\
[Homelab Watch is installed but has nothing to watch yet. Before answering the user's message, greet \
them briefly in your own words and tell them, in plain language, that:

- Homelab Watch checks the things on their network and tells them when one breaks. It only ever looks: \
it fetches a page, knocks on a port, pings, or asks DNS. It never logs in, restarts or changes anything.
- It starts empty on purpose. It does not scan their network uninvited, so they choose what it watches.
- They can set it up by asking you, for example "add my router, my NAS and my website". You will then \
load the homelab-watch:add-targets skill, find the addresses with them, and test each one.
- Good things to add: a home server or NAS, the router and wifi gear, a printer or camera, a VPS, \
their own websites, SSH on any box, a Tailscale machine, Proxmox, Home Assistant, Plex or Jellyfin, \
Pi-hole, Docker apps, a Bitaxe miner.
- Once a few things are added, "/homelab alerts on telegram" sends them a message when something breaks \
or recovers, and costs no tokens while everything is fine.
- Everything works with no extra accounts or API keys. If they later want the cost router, it uses a model \
they already have; a TypeSafe account is optional and paid, and nothing here needs it.

Keep it to a few short sentences, offer to start now, then answer what they actually asked. Do not repeat \
this note or mention that you were given it.]"""


def welcome_note(state: dict, configured: bool) -> str | None:
    """The note to inject, or None. Marks itself as shown so it never appears twice."""
    if configured or state.get(FLAG):
        return None
    state[FLAG] = True
    return WELCOME
