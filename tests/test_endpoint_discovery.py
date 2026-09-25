import base64
import os
import socket
from types import SimpleNamespace

import pytest

from awtui.endpoint_discovery import discover_ssh_candidates, dumps_public


def fake_run(argv, **kwargs):
    if argv[0] == "ssh":
        return SimpleNamespace(returncode=0, stdout="hostname internal-alias\nuser private-user\nport 2202\nidentityfile /home/private/.ssh/id_ed25519\nproxycommand secret-command\n")
    if argv[0] == "ssh-keyscan":
        key = base64.b64encode(b"fixture-host-public-key").decode()
        return SimpleNamespace(returncode=0, stdout=f"example.test ssh-ed25519 {key}\n")
    raise AssertionError(argv)


def test_enumerates_config_name_and_dual_stack_without_secrets(monkeypatch):
    monkeypatch.setattr("awtui.endpoint_discovery.socket.getaddrinfo", lambda *a, **k: [])
    result = discover_ssh_candidates("ai-ws", run=fake_run,
                                     resolver=lambda host: [("203.0.113.20", "ipv4"), ("2001:db8::4", "ipv6")])
    assert result.candidates[0].port == 2202
    assert {c.address_family for c in result.candidates} == {"name", "ipv4", "ipv6"}
    encoded = dumps_public(result)
    for forbidden in ("private-user", "/home/private", "secret-command", "identityfile"):
        assert forbidden not in encoded
    assert all(c.host_key_fingerprints[0].startswith("SHA256:") for c in result.candidates)


def test_orders_relay_vpn_dns_before_public_address():
    result = discover_ssh_candidates("relay", run=fake_run, resolver=lambda _: [], optional_candidates=[
        {"host": "203.0.113.5", "provenance": "public_ip"},
        {"host": "vpn.example", "provenance": "vpn"},
        {"host": "relay.example", "provenance": "relay"},
    ])
    assert [c.provenance for c in result.candidates] == ["relay", "vpn", "ssh_config", "public_ip"]


@pytest.mark.parametrize("host", ["127.0.0.1", "169.254.4.5", "::1", "fe80::1"])
def test_rejects_loopback_and_link_local_candidates(host):
    result = discover_ssh_candidates("local", run=fake_run, resolver=lambda _: [(host, "ipv4")])
    assert all(c.host != host for c in result.candidates)
    assert "non_phone_routable_address_omitted" in result.diagnostics


def test_bad_alias_and_bad_ssh_config_fail_closed():
    with pytest.raises(ValueError): discover_ssh_candidates("-oProxyCommand=evil")
    failure = lambda *a, **k: SimpleNamespace(returncode=255, stdout="secret error /private/path")
    result = discover_ssh_candidates("missing", run=failure, resolver=lambda _: [])
    assert result.diagnostics == ("ssh_alias_unresolved",)


def test_node26_alias_from_temporary_config_is_a_public_address_fixture(tmp_path):
    config = tmp_path / "config"
    config.write_text("Host node26\n  HostName 203.0.113.26\n  Port 2201\n  User fixture-user\n")
    seen = []
    def fixture_run(argv, **kwargs):
        seen.append(argv)
        if argv[0] == "ssh":
            assert "-F" in argv and str(config) in argv
        return SimpleNamespace(returncode=0, stdout="hostname 203.0.113.26\nport 2201\nuser fixture-user\n")
        return fake_run(argv, **kwargs)
    result = discover_ssh_candidates("node26", config_path=str(config), run=fixture_run, resolver=lambda _: [])
    assert result.candidates[0].host == "203.0.113.26"
    assert result.candidates[0].port == 2201
    assert "fixture-user" not in dumps_public(result)


def test_reflection_provider_is_explicit_https_and_returns_global_ip():
    from awtui.endpoint_discovery import reflected_public_ip

    class Response:
        def __enter__(self): return self
        def __exit__(self, *_): return None
        def read(self, limit):
            assert limit == 129
            return b"8.8.8.8\n"
    assert reflected_public_ip("https://reflect.example/ip", fetch=lambda *a, **k: Response())["host"] == "8.8.8.8"
    for value in ("http://reflect.example", "https://user:pass@reflect.example"):
        with pytest.raises(ValueError): reflected_public_ip(value)


@pytest.mark.skipif(not os.environ.get("AWUI_TEST_RENDEZVOUS_HOST"), reason="opt-in external rendezvous reachability test")
def test_opt_in_configured_rendezvous_tcp_reachability():
    """Real network checks are opt-in and never required by CI."""
    from awtui.endpoint_discovery import discover_ssh_candidates
    host = os.environ["AWUI_TEST_RENDEZVOUS_HOST"]
    result = discover_ssh_candidates(host)
    candidates = [c for c in result.candidates if c.host_key_fingerprints]
    assert candidates, result.diagnostics
    for candidate in candidates:
        with socket.create_connection((candidate.host, candidate.port), timeout=4):
            pass
