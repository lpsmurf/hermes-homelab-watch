import ipaddress

import pytest

from homelab_watch import scan
from homelab_watch.targets import TargetsError, parse_targets


def test_suggest_prefers_a_web_page_then_ssh_then_ping():
    assert scan.suggest("10.0.0.5", [22, 8123])["url"] == "http://10.0.0.5:8123/"
    assert scan.suggest("10.0.0.5", [443])["url"] == "https://10.0.0.5/"
    assert scan.suggest("10.0.0.5", [22]) == {"check": "tcp", "port": 22, "label": "SSH"}
    assert scan.suggest("10.0.0.5", [])["check"] == "ping"


def test_picks_become_valid_targets_under_the_gateway(tmp_path):
    f = tmp_path / "targets.yaml"
    f.write_text("targets:\n  - {id: web, name: Web, check: http, url: \"https://example.com\"}\n")
    picks = [{"ip": "192.168.1.20", "name": "NAS", **scan.suggest("192.168.1.20", [5000])},
             {"ip": "192.168.1.1", "name": "Router", "gateway": True, "check": "ping"},
             {"ip": "192.168.1.30", "name": "", "check": "ping"}]
    assert scan.add_to_file(f, picks, "") == 3
    t = parse_targets(f.read_text())
    assert t["router"].parent == "" and t["nas"].parent == "router" and t["192-168-1-30"].parent == "router"
    assert (tmp_path / "targets.yaml.bak").exists()


def test_ids_stay_unique_and_a_bad_result_is_never_written(tmp_path):
    f = tmp_path / "targets.yaml"
    f.write_text("targets:\n  - {id: nas, name: NAS, check: ping, host: 10.0.0.2}\n")
    scan.add_to_file(f, [{"ip": "10.0.0.9", "name": "NAS", "check": "ping"}], "")
    assert set(parse_targets(f.read_text())) == {"nas", "nas-2"}
    before = f.read_text()
    with pytest.raises(TargetsError):
        scan.add_to_file(f, [{"ip": "10.0.0.8", "name": "X", "check": "tcp", "port": 99999}], "")
    assert f.read_text() == before


def test_names_with_quotes_cannot_break_the_file(tmp_path):
    f = tmp_path / "targets.yaml"
    f.write_text("targets: []\n")
    scan.add_to_file(f, [{"ip": "10.0.0.4", "name": 'Bob\'s "NAS": {x}', "check": "ping"}], "")
    assert parse_targets(f.read_text())["bob-s-nas-x"].name == 'Bob\'s "NAS": {x}'


def test_only_one_private_slash_24_is_scanned():
    with pytest.raises(TargetsError):
        scan.scan(set(), ipaddress.ip_network("10.0.0.0/16"))
    with pytest.raises(TargetsError):
        scan.scan(set(), ipaddress.ip_network("8.8.8.0/24"))


@pytest.mark.parametrize("empty", ["targets: []\n", "targets:\n", "defaults: {timeout: 5}\ntargets: [ ]\n"])
def test_a_brand_new_empty_file_can_take_the_first_device(tmp_path, empty):
    f = tmp_path / "targets.yaml"
    f.write_text(empty)
    scan.add_to_file(f, [{"ip": "10.0.0.7", "name": "Printer", "check": "ping"}], "")
    assert list(parse_targets(f.read_text())) == ["printer"]


def test_interfaces_are_read_from_macos_and_linux_output():
    mac = "lo0: flags=8049<UP>\n\tinet 127.0.0.1 netmask 0xff000000\nen1: flags=8863<UP>\n\tinet 192.168.1.5 netmask 0xffffff00 broadcast 192.168.1.255\nutun4: flags=8051<UP>\n\tinet 10.5.0.2 --> 10.5.0.1 netmask 0xffffffff\n"
    assert scan._interfaces(mac) == [("lo0", "127.0.0.1"), ("en1", "192.168.1.5"), ("utun4", "10.5.0.2")]
    assert scan._interfaces("2: eth0    inet 10.0.0.9/24 brd 10.0.0.255 scope global eth0") == [("eth0", "10.0.0.9")]


def test_vpn_tunnels_and_virtual_adapters_are_never_offered(monkeypatch):
    out = "en1: flags=1<UP>\n\tinet 192.168.1.5 netmask 0xffffff00\nutun4: flags=1<UP>\n\tinet 10.5.0.2 netmask 0xffffffff\nbridge100: flags=1<UP>\n\tinet 192.168.64.1 netmask 0xffffff00\n"
    class R:
        stdout = out
    monkeypatch.setattr(scan.subprocess, "run", lambda *a, **k: R())
    assert [n["range"] for n in scan.local_networks()] == ["192.168.1.0/24"]
