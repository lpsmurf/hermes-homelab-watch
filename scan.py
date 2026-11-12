"""Find devices on the user's own network and turn the ones they pick into targets.

Only ever looks: a ping, a TCP connect to a few common ports, a reverse-DNS lookup, and the ARP table the
machine already holds. It refuses anything outside a private (home or office) address range, and never
scans more than one /24. Writing to targets.yaml happens only for entries the user chose, after the
result list is shown.
"""

from __future__ import annotations

import ipaddress
import platform
import re
import socket
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .targets import TargetsError, parse_targets

# port → (what it usually is, check to suggest)
PORTS: dict[int, tuple[str, str]] = {
    80: ("web page", "http"), 443: ("secure web page", "http"), 8080: ("web page", "http"),
    5000: ("NAS web page", "http"), 8006: ("Proxmox", "http"), 8123: ("Home Assistant", "http"),
    32400: ("Plex", "http"), 8096: ("Jellyfin", "http"), 3000: ("Grafana or app", "http"),
    22: ("SSH", "tcp"),
}
HTTPS_PORTS = {443, 8006, 9443, 8443}
MAX_HOSTS = 254


TUNNELS = ("utun", "tun", "tap", "wg", "tailscale", "ppp", "ipsec", "vpn", "docker", "veth", "br-", "vmnet", "bridge", "lo")


def _interfaces(text: str) -> list[tuple[str, str]]:
    """(interface, ipv4) pairs from `ifconfig` (macOS) or `ip -4 -o addr` (Linux) output."""
    pairs = [(m[1], m[2]) for m in re.finditer(r"^\d+:\s+(\S+)\s+inet\s+(\d+\.\d+\.\d+\.\d+)", text, re.M)]
    if pairs:
        return pairs
    cur, out = "", []
    for ln in text.splitlines():
        head = re.match(r"^(\S+?):\s+flags=", ln)
        if head:
            cur = head[1]
        m = re.match(r"^\s+inet (\d+\.\d+\.\d+\.\d+)\b", ln)
        if m and cur:
            out.append((cur, m[1]))
    return out


def local_networks() -> list[dict]:
    """Every private /24 this machine is directly on, skipping VPN tunnels and virtual adapters.

    A VPN usually becomes the default route, so asking "which interface reaches the internet" would
    scan the tunnel and miss the home network. Listing real interfaces avoids that.
    """
    gateway = default_gateway()
    out = []
    for cmd in (["ifconfig"], ["ip", "-4", "-o", "addr"]):
        try:
            text = subprocess.run(cmd, capture_output=True, text=True, timeout=5).stdout
        except (OSError, subprocess.SubprocessError):
            continue
        for iface, ip in _interfaces(text):
            addr = ipaddress.ip_address(ip)
            if not addr.is_private or addr.is_loopback or addr.is_link_local or iface.startswith(TUNNELS):
                continue
            net = ipaddress.ip_network(f"{ip}/24", strict=False)
            if all(n["range"] != str(net) for n in out):
                gw = gateway if gateway and ipaddress.ip_address(gateway) in net else ""
                out.append({"range": str(net), "iface": iface, "gateway": gw, "addresses": net.num_addresses - 2})
        if out:
            break
    if not out:
        raise TargetsError("No home or office network found to scan. Are you connected to wifi or ethernet?")
    return out


def default_gateway() -> str:
    cmds = (["route", "-n", "get", "default"], ["ip", "route", "show", "default"])
    for cmd in cmds:
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=5).stdout
        except (OSError, subprocess.SubprocessError):
            continue
        m = re.search(r"gateway:\s*(\S+)", out) or re.search(r"default via (\S+)", out)
        if m:
            return m.group(1)
    return ""


def _ping(ip: str) -> bool:
    wait = ["-W", "1000"] if platform.system() == "Darwin" else ["-W", "1"]
    try:
        return subprocess.run(["ping", "-c", "1", *wait, ip], capture_output=True, timeout=4).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _arp(net: ipaddress.IPv4Network) -> set[str]:
    """Addresses the machine already knows about. Catches devices that ignore ping."""
    try:
        out = subprocess.run(["arp", "-an"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return set()
    found = set()
    for ip, mac in re.findall(r"\((\d+\.\d+\.\d+\.\d+)\) at ([0-9a-f:]+)", out):
        if len(mac) > 11 and ipaddress.ip_address(ip) in net and not ip.endswith(".255"):
            found.add(ip)
    return found


def _open_ports(ip: str) -> list[int]:
    found = []
    for port in PORTS:
        try:
            with socket.create_connection((ip, port), timeout=0.6):
                found.append(port)
        except OSError:
            pass
    return found


def _name(ip: str) -> str:
    try:
        return socket.gethostbyaddr(ip)[0].split(".")[0]
    except OSError:
        return ""


def suggest(ip: str, ports: list[int]) -> dict:
    """The sensible check for a device given what answered."""
    web = next((p for p in (443, 8006, 8123, 32400, 8096, 5000, 3000, 8080, 80) if p in ports), None)
    label = ", ".join(PORTS[p][0] for p in ports) or "answers ping"
    if web is not None:
        scheme = "https" if web in HTTPS_PORTS else "http"
        url = f"{scheme}://{ip}/" if web in (80, 443) else f"{scheme}://{ip}:{web}/"
        return {"check": "http", "url": url, "label": label}
    if 22 in ports:
        return {"check": "tcp", "port": 22, "label": label}
    return {"check": "ping", "label": label}


def scan(known_hosts: set[str], net: ipaddress.IPv4Network | None = None, gateway: str = "") -> dict:
    """Sweep one private /24. `known_hosts` are addresses already in targets.yaml (marked, not hidden)."""
    if net is None:
        net = ipaddress.ip_network(local_networks()[0]["range"])
    if not net.is_private or net.num_addresses - 2 > MAX_HOSTS:
        raise TargetsError("Only one private /24 can be scanned at a time.")
    hosts = [str(h) for h in net.hosts()]
    with ThreadPoolExecutor(max_workers=64) as pool:
        alive = {ip for ip, ok in zip(hosts, pool.map(_ping, hosts)) if ok}
    alive |= _arp(net)
    ordered = sorted(alive, key=lambda i: tuple(map(int, i.split("."))))
    with ThreadPoolExecutor(max_workers=24) as pool:
        ports = dict(zip(ordered, pool.map(_open_ports, ordered)))
        names = dict(zip(ordered, pool.map(_name, ordered)))
    devices = [{"ip": ip, "name": names[ip], "ports": ports[ip], "known": ip in known_hosts,
                "gateway": ip == gateway, **suggest(ip, ports[ip])} for ip in ordered]
    return {"range": str(net), "gateway": gateway, "devices": devices, "scanned": len(hosts)}


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "device"


def render_entries(picks: list[dict], existing_ids: set[str], gateway_id: str = "") -> str:
    """YAML lines for the chosen devices. Ids stay unique; everything else sits under the gateway."""
    picks = sorted(picks, key=lambda p: not p.get("gateway"))  # the gateway first, so its id exists to point at
    lines, used = ["", "  # --- added from a network scan ---"], set(existing_ids)
    for p in picks:
        base = _slug(p.get("name") or p["ip"])
        tid, n = base, 2
        while tid in used:
            tid, n = f"{base}-{n}", n + 1
        used.add(tid)
        if p.get("gateway") and not gateway_id:
            gateway_id = tid
        check = p["check"]
        fields = [f"id: {tid}", f"name: {_quote(p.get('name') or p['ip'])}", f"check: {check}"]
        if check == "http":
            fields.append(f"url: {_quote(p['url'])}")
        else:
            fields.append(f"host: {p['ip']}")
            if check == "tcp":
                fields.append(f"port: {int(p.get('port', 22))}")
        if gateway_id and not p.get("gateway") and tid != gateway_id:
            fields.append(f"parent: {gateway_id}")
        lines.append("  - {" + ", ".join(fields) + "}")
    return "\n".join(lines) + "\n"


def _quote(s: str) -> str:
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def add_to_file(path: Path, picks: list[dict], gateway: str) -> int:
    """Append the picks to targets.yaml after proving the result still loads. Keeps a .bak copy."""
    text = path.read_text(encoding="utf-8") if path.exists() else "targets:\n"
    # A new user's file is `targets: []`, which cannot take list items underneath it.
    text = re.sub(r"(?m)^targets:[ \t]*\[[ \t]*\][ \t]*$", "targets:", text)
    current = parse_targets(text)
    gateway_id = next((t.id for t in current.values() if gateway and t.host == gateway), "")
    new = text.rstrip("\n") + "\n" + render_entries(picks, set(current), gateway_id)
    parse_targets(new)  # raises TargetsError naming the problem, before anything is written
    path.with_suffix(".yaml.bak").write_text(text, encoding="utf-8")
    path.write_text(new, encoding="utf-8")
    return len(picks)
