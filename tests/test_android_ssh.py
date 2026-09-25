from __future__ import annotations

import os
import socket
from types import SimpleNamespace

import pytest

from awtui.android_ssh import (
    authorized_key_record,
    configured_alias,
    host_key_fingerprint,
    rendezvous_metadata,
)


PUBLIC_KEY = (
    "ecdsa-sha2-nistp256 "
    "AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzdHAyNTYAAABBBCbvzr0O6eNKZpGH4Ys6kSKy9zOUW2Scyfn5Ien52tgSkCOL3pzHuzMNFQxncE3SWucFUgV0S28xv0BwdFhy0OY="
)


def test_authorized_key_record_is_restricted_and_attributable():
    line = authorized_key_record(PUBLIC_KEY, "android-abcdefghijkl", 43127, expires_at="2026-09-26T00:00:00Z")
    assert "command=\"/usr/bin/false\"" in line
    assert 'permitopen="127.0.0.1:43127"' in line
    assert "expiry-time=\"20260926000000Z\"" in line
    assert "awui:android-abcdefghijkl" in line
    assert "PRIVATE" not in line


def test_alias_is_explicit_and_fail_closed(monkeypatch):
    monkeypatch.setenv("AWUI_SSH_HOST", "node26")
    assert configured_alias() == "node26"
    with pytest.raises(ValueError):
        configured_alias("bad alias")
    with pytest.raises(ValueError):
        configured_alias("-oProxyCommand=bad")


def test_host_key_fingerprint_uses_known_hosts_only(monkeypatch, tmp_path):
    known_hosts = tmp_path / "known_hosts"
    known_hosts.write_text("", encoding="utf-8")

    def fake_run(argv, **kwargs):
        if argv[:2] == ["ssh", "-G"]:
            return SimpleNamespace(returncode=0, stdout="hostname relay.example\nport 22\nuser relay\nuserknownhostsfile " + str(known_hosts) + "\n")
        if argv[:2] == ["ssh-keygen", "-F"]:
            return SimpleNamespace(returncode=0, stdout="relay.example ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGZpeHR1cmU=\n")
        raise AssertionError(argv)

    monkeypatch.setattr("awtui.android_ssh.subprocess.run", fake_run)
    value = host_key_fingerprint("relay")
    assert value.startswith("SHA256:")


@pytest.mark.skipif(not os.environ.get("AWUI_TEST_RENDEZVOUS_HOST"), reason="opt-in external rendezvous reachability test")
def test_configured_rendezvous_is_reachable_from_this_host():
    import subprocess

    alias = os.environ["AWUI_TEST_RENDEZVOUS_HOST"]
    config = subprocess.run(["ssh", "-G", alias], check=True, capture_output=True, text=True).stdout
    values = dict(line.split(None, 1) for line in config.splitlines() if " " in line)
    with socket.create_connection((values["hostname"], int(values.get("port", "22"))), timeout=5):
        pass


def test_metadata_uses_explicit_phone_candidate(monkeypatch):
    def fake_run(argv, **kwargs):
        if argv[:2] == ["ssh", "-G"]:
            return SimpleNamespace(returncode=0, stdout="hostname internal\nport 22\nuser relay\n")
        if argv[:2] == ["ssh-keygen", "-F"]:
            return SimpleNamespace(returncode=0, stdout="relay ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGZpeHR1cmU=\n")
        raise AssertionError(argv)

    monkeypatch.setattr("awtui.android_ssh.subprocess.run", fake_run)
    result = rendezvous_metadata("relay", 40123, phone_host="198.51.100.20")
    assert result["host"] == "198.51.100.20"
    assert result["forward_port"] == 40123
