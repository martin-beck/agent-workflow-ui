import json

from awtui.android_register import main


def test_register_command_prints_one_time_payload(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["awui-android-register", "--state", str(tmp_path / "state.json"),
                                      "--project-id", "demo", "--endpoint", "https://host.example"])
    main()
    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "android-registration-qr"
    assert payload["project_id"] == "demo"
    assert not (tmp_path / "state.json").read_text().endswith("credential")
