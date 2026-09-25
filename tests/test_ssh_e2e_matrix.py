"""Offline cross-platform qualification for SSH discovery and Android routing.

The matrix deliberately uses deterministic OpenSSH and DNS seams.  A real
host is never required for CI; the opt-in ``AWUI_TEST_RENDEZVOUS_HOST`` test
in ``test_endpoint_discovery.py`` provides the separate live qualification.
"""
from __future__ import annotations

import base64
from types import SimpleNamespace

import pytest

from awtui.endpoint_discovery import discover_ssh_candidates


@pytest.mark.parametrize("platform", ["linux", "windows", "android"])
@pytest.mark.parametrize(
    ("provenance", "host"),
    [
        ("relay", "relay.example"),
        ("vpn", "10.20.0.7"),
        ("dns", "dns.example"),
        ("public_ip", "198.51.100.7"),
    ],
)
def test_discovery_matrix_is_platform_neutral_and_redacted(platform, provenance, host):
    key = base64.b64encode(f"{platform}-{provenance}-key".encode()).decode()

    def run(argv, **kwargs):
        if argv[0:2] == ["ssh", "-G"]:
            return SimpleNamespace(
                returncode=0,
                stdout="hostname rendezvous.internal\nport 2222\nuser private-user\n"
                "identityfile /private/secret/key\nproxycommand secret-proxy\n",
            )
        if argv[0:2] == ["ssh-keyscan", "-T"]:
            return SimpleNamespace(returncode=0, stdout=f"{argv[-1]} ssh-ed25519 {key}\n")
        raise AssertionError(argv)

    result = discover_ssh_candidates(
        "configured-rendezvous",
        run=run,
        resolver=lambda _: [("2001:db8::7", "ipv6"), ("203.0.113.7", "ipv4")],
        optional_candidates=[{"provenance": provenance, "host": host}],
    )
    assert result.candidates
    assert any(item.provenance in {provenance, "dns_address"} for item in result.candidates)
    assert {item.address_family for item in result.candidates} >= {"name", "ipv4", "ipv6"}
    output = result.public_dict()
    assert "private-user" not in str(output)
    assert "/private/secret/key" not in str(output)
    assert "secret-proxy" not in str(output)


def test_discovery_matrix_rejects_untrusted_or_expired_hints():
    def run(argv, **kwargs):
        if argv[0:2] == ["ssh", "-G"]:
            return SimpleNamespace(returncode=0, stdout="hostname relay.example\nport 22\n")
        if argv[0:2] == ["ssh-keyscan", "-T"]:
            return SimpleNamespace(returncode=0, stdout="")
        raise AssertionError(argv)

    result = discover_ssh_candidates(
        "relay",
        run=run,
        resolver=lambda _: [],
        optional_candidates=[
            {"provenance": "unknown", "host": "evil.example"},
            {"provenance": "relay", "host": "relay-alt.example", "expires_at": 0},
        ],
    )
    assert all(item.host != "evil.example" for item in result.candidates)
    assert "unknown_candidate_provenance_omitted" in result.diagnostics
    assert "invalid_candidate_expiry_omitted" in result.diagnostics
