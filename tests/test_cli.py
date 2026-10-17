import json
from uuid import UUID

from hermes_paperclip_bridge.cli import main


def config(tmp_path):
    path = tmp_path / "bridge.toml"
    path.write_text(f'''
state = "state.sqlite"
[paperclip]
url = "http://127.0.0.1:3100"
company_id = "{UUID(int=1)}"
token_env = "BRIDGE_FIXTURE_PC"
[hermes]
url = "http://127.0.0.1:9119"
install_id = "fixture"
token_env = "BRIDGE_FIXTURE_HM"
''')
    return path


def test_status_needs_no_credentials_and_outputs_json(tmp_path, capsys):
    assert main(["--config", str(config(tmp_path)), "status"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output == {"bindings": [], "operations": []}


def test_missing_credentials_is_a_safe_json_error(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("BRIDGE_FIXTURE_PC", raising=False)
    assert main(["--config", str(config(tmp_path)), "reconcile"]) == 3
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "error"
    assert "Traceback" not in output["message"]


def test_bad_configuration_has_no_traceback_or_file_contents(tmp_path, capsys):
    path = tmp_path / "bridge.toml"
    path.write_text('secret="fixture-must-not-appear"')
    assert main(["--config", str(path), "status"]) == 3
    output = capsys.readouterr().out
    assert "fixture-must-not-appear" not in output
    assert json.loads(output)["status"] == "error"


def test_watch_reports_malformed_native_metadata_and_remains_interruptible(
    tmp_path, capsys, monkeypatch
):
    from hermes_paperclip_bridge import cli
    from hermes_paperclip_bridge.config import Settings
    from hermes_paperclip_bridge.models import View
    from hermes_paperclip_bridge.state import Store

    path = config(tmp_path)
    settings = Settings.load(path)
    store = Store(settings.state, scope=settings.scope)
    store.bind("agent", "maya", baseline="Maya")
    store.close()

    class PC:
        def __init__(self, *_args):
            pass

        def get(self, _identity):
            return View("Maya", "1")

        def close(self):
            pass

    class BadRPC:
        def __init__(self, *_args):
            pass

        def call(self, method, params):
            return {"install_id": "fixture", "profiles": [{"name": "maya", "ui_meta": None}]}

    def interrupt(_seconds):
        raise KeyboardInterrupt

    monkeypatch.setenv("BRIDGE_FIXTURE_PC", "fixture-token")
    monkeypatch.setenv("BRIDGE_FIXTURE_HM", "fixture-token")
    monkeypatch.setattr(cli, "Paperclip", PC)
    monkeypatch.setattr(cli, "RPC", BadRPC)
    monkeypatch.setattr(cli.time, "sleep", interrupt)
    assert main(["--config", str(path), "watch", "--apply"]) == 130
    result = json.loads(capsys.readouterr().out)
    assert result[0]["status"] == "error"
    assert "unsupported" in result[0]["message"]
