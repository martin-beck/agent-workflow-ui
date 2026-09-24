import json
import os
import stat
import tarfile
from pathlib import Path

import pytest
from awtui.connect import environment_fingerprint, bootstrap_runtime, runtime_archive_name, runtime_manifest, _validate_remote_path, _validate_ssh_host, _timeout_seconds, _transport
from awtui.connect import connect


def test_environment_fingerprint_has_portable_runtime_facts():
    facts = environment_fingerprint()
    assert set(facts) == {"platform", "architecture", "python", "shell"}
    assert facts["platform"]
    assert facts["architecture"]


def test_runtime_archive_is_platform_specific_and_safely_extracted(tmp_path):
    archive = tmp_path / "runtime.tar.gz"
    payload = tmp_path / "payload"; payload.mkdir(); (payload / "bin").mkdir()
    (payload / "bin" / "awui-live").write_text("#!/bin/sh\n")
    (payload / "runtime-manifest.json").write_text(__import__("json").dumps(runtime_manifest({"platform": "linux", "architecture": "x86_64", "python": "3.12"})))
    with tarfile.open(archive, "w:gz") as bundle:
        bundle.add(payload / "bin" / "awui-live", arcname="bin/awui-live")
        bundle.add(payload / "runtime-manifest.json", arcname="runtime-manifest.json")
    destination = bootstrap_runtime(archive, tmp_path / "out", expected={"schema_version": "1", "platform": "linux", "architecture": "x86_64", "python": "3.12"})
    assert (destination / "bin/awui-live").is_file()
    assert runtime_archive_name({"platform": "windows", "architecture": "amd64"}) == "awui-windows-amd64.tar.gz"
    assert runtime_manifest({"platform": "linux", "architecture": "aarch64", "python": "3.12"})["architecture"] == "aarch64"


@pytest.mark.parametrize("path", ["relative.json", "/tmp/../escape", "/tmp/a\njson"])
def test_remote_paths_fail_closed(path):
    with pytest.raises(ValueError):
        _validate_remote_path(path)


@pytest.mark.parametrize("host", ["bad;host", "bad host", "bad\nhost", "bad'host"])
def test_ssh_aliases_fail_closed(host):
    with pytest.raises(ValueError, match="ssh_host"):
        _validate_ssh_host(host)


def test_ssh_alias_is_preserved_for_open_ssh_config():
    assert _validate_ssh_host("project-prod") == "project-prod"


def test_transport_retries_are_timeout_bounded(monkeypatch):
    import subprocess
    import awtui.connect as connector

    calls = []

    def run(command, **kwargs):
        calls.append(kwargs["timeout"])
        return subprocess.CompletedProcess(command, 1)

    monkeypatch.setattr(connector.subprocess, "run", run)
    assert _transport(["ssh", "offline", "true"], attempts=3) == 1
    assert calls == [30.0, 30.0, 30.0]


def test_transport_converts_user_cancel_to_controlled_exit(monkeypatch):
    import awtui.connect as connector

    def cancel(*_args, **_kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(connector.subprocess, "run", cancel)
    assert _transport(["ssh", "offline", "true"], attempts=3) == 130


def test_timeout_setting_is_fail_closed_and_capped(monkeypatch):
    monkeypatch.setenv("AWUI_CONNECT_TIMEOUT", "999")
    assert _timeout_seconds() == 300.0
    monkeypatch.setenv("AWUI_CONNECT_TIMEOUT", "0")
    with pytest.raises(ValueError):
        _timeout_seconds()


def test_runtime_archive_directory_is_cleaned_after_local_launch(tmp_path, monkeypatch):
    import awtui.connect as connector

    archive = tmp_path / "runtime.tar.gz"
    payload = tmp_path / "payload"; payload.mkdir(); (payload / "bin").mkdir()
    (payload / "bin" / "awtui-live").write_text("#!/bin/sh\n")
    (payload / "runtime-manifest.json").write_text(__import__("json").dumps(runtime_manifest()))
    with tarfile.open(archive, "w:gz") as bundle:
        bundle.add(payload / "bin" / "awtui-live", arcname="bin/awtui-live")
        bundle.add(payload / "runtime-manifest.json", arcname="runtime-manifest.json")

    seen = []
    created = []

    class TrackingDirectory:
        def __init__(self, prefix):
            import tempfile
            self.name = tempfile.mkdtemp(prefix=prefix, dir=tmp_path)
            created.append(self.name)
        def cleanup(self):
            import shutil
            shutil.rmtree(self.name, ignore_errors=True)

    monkeypatch.setenv("AWUI_RUNTIME_ARCHIVE", str(archive))
    monkeypatch.setattr(connector.shutil, "which", lambda name: None)
    monkeypatch.setattr(connector.tempfile, "TemporaryDirectory", TrackingDirectory)
    monkeypatch.setattr(connector, "_run", lambda command, env=None: seen.append(command) or 0)
    assert connector.connect(session_file=str(tmp_path / "request.json"), backend="tui") == 0
    assert created and not Path(created[0]).exists()
    assert seen


def test_remote_result_is_published_by_atomic_rename_and_cleanup(monkeypatch):
    import json
    import subprocess
    import awtui.connect as connector

    commands = []
    request = {"project_id": "p", "session_id": "s", "ar": {"ar_id": "AR-1", "task_revision": 2}}

    def transport(command, **kwargs):
        del kwargs
        commands.append(command)
        if command[0] == "ssh" and command[2] == "cat":
            kwargs = {}  # keep the branch visibly side-effect free
            stdout = transport.stdout
            stdout.write(json.dumps(request).encode())
        return subprocess.CompletedProcess(command, 0)

    transport.stdout = None
    original = connector.subprocess.run

    def run(command, **kwargs):
        if command[0] == "ssh" and command[2] == "cat":
            transport.stdout = kwargs["stdout"]
        result = transport(command, **kwargs)
        transport.stdout = None
        return result

    def ui(command, *, env=None):
        del env
        output = connector.Path(command[command.index("--output-json") + 1])
        output.write_text(json.dumps({"session_id": "s", "sequence": 1}) + "\n", encoding="utf-8")
        return 0

    monkeypatch.setattr(connector.subprocess, "run", run)
    monkeypatch.setattr(connector, "_run", ui)
    try:
        assert connect(session_file="/srv/request.json", ssh_host="project-prod", remote_event_file="/srv/result.json", backend="tui") == 0
    finally:
        monkeypatch.setattr(connector.subprocess, "run", original)
    scp = next(command for command in commands if command[0] == "scp")
    assert ".tmp-" in scp[-1]
    assert any(command[:4] == ["ssh", "project-prod", "mv", "-f"] for command in commands)
    assert any(command[:4] == ["ssh", "project-prod", "rm", "-f"] for command in commands)


@pytest.mark.parametrize(
    ("platform", "architecture"),
    [("linux", "x86_64"), ("windows", "amd64"), ("darwin", "arm64"), ("linux", "aarch64")],
)
def test_runtime_manifest_matrix_is_addressable(platform, architecture):
    facts = {"platform": platform, "architecture": architecture, "python": "3.12"}
    assert runtime_archive_name(facts) == f"awui-{platform}-{architecture}.tar.gz"
    manifest = runtime_manifest(facts)
    assert manifest["platform"] == platform
    assert manifest["architecture"] == architecture


@pytest.mark.parametrize("backend, executable", [("gui", "awui-live"), ("tui", "awtui-live")])
def test_connect_local_invokes_selected_backend_and_writes_result(tmp_path, monkeypatch, backend, executable):
    shim = tmp_path / executable
    shim.write_text(
        "#!/usr/bin/env python3\n"
        "import json, pathlib, sys\n"
        "a=sys.argv; req=pathlib.Path(a[a.index('--session-file')+1]); out=pathlib.Path(a[a.index('--output-json')+1])\n"
        "data=json.loads(req.read_text()); out.write_text(json.dumps({'event_type':'select','session_id':data['session_id']})+'\\n')\n",
        encoding="utf-8",
    )
    shim.chmod(shim.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")
    request = tmp_path / "request.json"
    request.write_text(json.dumps({"session_id": "local-e2e"}), encoding="utf-8")
    result = tmp_path / "events.jsonl"
    assert connect(session_file=str(request), remote_event_file=str(result), backend=backend) == 0
    assert json.loads(result.read_text(encoding="utf-8"))["session_id"] == "local-e2e"
