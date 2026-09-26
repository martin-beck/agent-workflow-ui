from pathlib import Path
from types import SimpleNamespace

import pytest

from awtui.android_pair import endpoint_for, ensure_service, rendezvous_endpoint


def test_endpoint_for_supports_ipv6_and_rejects_options():
    assert endpoint_for("2001:db8::5", 8765) == "https://[2001:db8::5]:8765"
    with pytest.raises(ValueError):
        endpoint_for("-oProxyCommand=bad", 8765)


def test_ensure_service_reuses_healthy_service(monkeypatch, tmp_path):
    monkeypatch.setattr("awtui.android_pair.service_health", lambda *a, **k: True)
    called = []
    assert ensure_service(endpoint="https://workflow.example", state=tmp_path / "state.json",
                          host="127.0.0.1", port=8765, certfile=None, keyfile=None,
                          popen=lambda *a, **k: called.append((a, k))) is False
    assert called == []


def test_ensure_service_starts_and_waits_for_health(monkeypatch, tmp_path):
    responses = iter([False, True])
    monkeypatch.setattr("awtui.android_pair.service_health", lambda *a, **k: next(responses))
    cert, key = tmp_path / "service.crt", tmp_path / "service.key"
    cert.write_text("certificate")
    key.write_text("key")
    calls = []

    class Process:
        pid = 1234
        def poll(self):
            return None

    def start(command, **kwargs):
        calls.append((command, kwargs))
        return Process()

    pid = tmp_path / "service.pid"
    assert ensure_service(endpoint="https://workflow.example", state=tmp_path / "state.json",
                          host="127.0.0.1", port=8765, certfile=cert, keyfile=key,
                          ssh_host="node26", pid_file=pid, popen=start) is True
    assert calls and "--ssh-host" in calls[0][0]
    assert pid.read_text() == "1234\n"


def test_ensure_service_requires_tls_material_when_absent(monkeypatch, tmp_path):
    monkeypatch.setattr("awtui.android_pair.service_health", lambda *a, **k: False)
    with pytest.raises(RuntimeError, match="--certfile and --keyfile"):
        ensure_service(endpoint="https://workflow.example", state=tmp_path / "state.json",
                       host="127.0.0.1", port=8765, certfile=None, keyfile=None)


def test_rendezvous_endpoint_uses_allocated_https_forward_for_first_bootstrap():
    assert rendezvous_endpoint(
        {"ssh_rendezvous": {"host": "relay.example", "forward_port": 40123}},
        ssh_host="node26", endpoint=None, public_host=None,
        service_host="127.0.0.1", service_port=8765,
    ) == "https://relay.example:40123"


def test_rendezvous_endpoint_requires_metadata_when_ssh_bootstrap_requested():
    with pytest.raises(ValueError, match="rendezvous metadata"):
        rendezvous_endpoint({}, ssh_host="node26", endpoint=None, public_host=None,
                            service_host="127.0.0.1", service_port=8765)
