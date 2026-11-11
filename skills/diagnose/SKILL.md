---
name: diagnose
description: "Something is red in Homelab Watch: find the real cause, then offer a fix that Hermes performs only with the user's approval."
version: 1.0.0
author: lpsmurf (HFSP Labs)
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [homelab, monitoring]
    related_skills: [add-targets]
---

# Diagnose, then fix with permission

Homelab Watch only looks. It never repairs anything, by design. This skill is the other half: when
something is down, work out why, then offer a fix that **Hermes itself** carries out through its own
tools, each step approved by the user. The plugin is not involved in the fixing.

## 1. Find the real cause

1. Run `hermes homelab json`. Start from `incidents`, not from the long list of red targets: the root
   incident is already the highest thing that is down, and `affected` lists what it took with it.
2. Test it from the bottom up, stopping at the first failure:
   - **Can this machine reach the network at all?** `ping -c1 <router>`; `dig +short example.com`.
   - **Does the name resolve?** `dig +short <host>`. No answer with a working ping means DNS, not the host.
   - **Does the address answer?** `ping -c1 <host>`.
   - **Is the port open?** `nc -z -G 3 <host> <port>`. Ping works but the port is closed means the
     service is down, not the machine.
   - **Does the service answer correctly?** `curl -sS -m 10 -o /dev/null -w '%{http_code}' <url>`. A
     timeout is a hang; a 5xx is the app failing; a TLS error is a certificate problem.
3. **Compare with before.** `hermes cron runs` and the alert history in the Hermes cron output folder
   show when it first failed and whether it flaps. A box that fails every night at 03:00 is a backup
   job, not an outage.
4. **Check whether the problem is local.** If only this Mac cannot resolve names, a VPN or the Mac's
   own DNS is the cause. Ask the user to try the same address from a phone on mobile data before
   telling them their server is down.

State the cause in one sentence and say how sure you are.

## 2. Offer a fix, never assume one

Say what you would do and why, in plain words, then **wait for a clear yes** for each action:

| Cause | Fix to offer |
|---|---|
| A service on a machine you can reach by SSH is stopped | restart that one service |
| A container is unhealthy | restart that container |
| Disk full | show what is large and let the user pick what to remove |
| A certificate expired | renew it with the user's own tool |
| The router or modem is unresponsive | tell the user to power-cycle it; you cannot |
| A website is down at the host | check the host's status page and say so |

Rules for acting:

- Use Hermes' normal tools (`terminal` and the like) so every command goes through Hermes' approval
  prompt. **Never** bypass, pre-approve or silently confirm anything.
- Touch only the one thing diagnosed. No broad restarts, no reboots of a machine other things depend on,
  and nothing that could lose data, without an explicit, specific yes.
- Do not guess credentials, and do not read private key or token files. If a fix needs a login Hermes
  does not already have, say so and stop.
- Prefer the undoable action: restart a service rather than reinstall it.

## 3. Prove it worked

Run `hermes homelab check` and read the target back to the user. If it is still red, say so plainly and
go back to step 1 with what you learned. Never report a fix as done without a green check.

## 4. Leave a note

Tell the user in two sentences what broke, what you changed, and what to watch for next time. If the
same target keeps failing, suggest the `homelab-watch:tune-thresholds` skill.
