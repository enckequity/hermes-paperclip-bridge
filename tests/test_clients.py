from uuid import UUID

import httpx
import pytest

from hermes_paperclip_bridge.config import Settings, checked_url
from hermes_paperclip_bridge.hermes import Hermes
from hermes_paperclip_bridge.models import BridgeError
from hermes_paperclip_bridge.paperclip import Paperclip

COMPANY = str(UUID(int=1))
AGENT = str(UUID(int=2))


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "https://u:p@example.com",
        "https://x/?key=a",
        "https://example.com/p/maya",
        "http://127.0.0.1:invalid",
        "https://[bad",
    ],
)
def test_urls_reject_remote_http_embedded_credentials_and_queries(url):
    with pytest.raises(BridgeError):
        checked_url(url)


def test_loopback_http_is_allowed():
    assert checked_url("http://127.0.0.1:3100/") == "http://127.0.0.1:3100"


def test_config_has_environment_references_not_plaintext_tokens(tmp_path, monkeypatch):
    path = tmp_path / "bridge.toml"
    path.write_text(f'''
state = "state.sqlite"
[paperclip]
url = "http://127.0.0.1:3100"
company_id = "{COMPANY}"
token_env = "TEST_PC_TOKEN"
[hermes]
url = "http://127.0.0.1:9119"
install_id = "installation-a"
token_env = "TEST_HERMES_TOKEN"
auth_mode = "bearer"
''')
    settings = Settings.load(path)
    assert settings.state == tmp_path / "state.sqlite"
    assert "TEST_PC_TOKEN" not in settings.scope
    with pytest.raises(BridgeError, match="environment"):
        settings.paperclip.token()
    monkeypatch.setenv("TEST_PC_TOKEN", "test-secret-only")
    assert settings.paperclip.token() == "test-secret-only"
    assert "test-secret-only" not in repr(settings)


def test_paperclip_refuses_foreign_company_and_redirects():
    def handler(request):
        assert request.headers["Authorization"] == "Bearer fixture-token"
        return httpx.Response(200, json={"id": AGENT, "companyId": "foreign", "name": "Maya"})

    pc = Paperclip(
        "http://127.0.0.1:3100", COMPANY, "fixture-token", transport=httpx.MockTransport(handler)
    )
    with pytest.raises(BridgeError, match="company"):
        pc.get(AGENT)
    pc.close()
    pc = Paperclip(
        "http://127.0.0.1:3100",
        COMPANY,
        "fixture-token",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(307, headers={"location": "https://untrusted.example/"})
        ),
    )
    with pytest.raises(BridgeError, match="307"):
        pc.get(AGENT)
    pc.close()


def test_paperclip_rename_preserves_other_fields_and_checks_readback():
    row = {"id": AGENT, "companyId": COMPANY, "name": "Maya", "updatedAt": "1"}
    patches = []

    def handler(request):
        if request.method == "PATCH":
            patches.append(request.content)
            row.update(name="Marketing", updatedAt="2")
        return httpx.Response(200, json=row.copy())

    pc = Paperclip(
        "http://127.0.0.1:3100", COMPANY, "fixture-token", transport=httpx.MockTransport(handler)
    )
    pc.rename(AGENT, pc.get(AGENT), "Marketing")
    assert patches == [b'{"name":"Marketing"}']
    pc.close()


class FakeRPC:
    def __init__(self):
        self.profiles = [
            {
                "name": "maya",
                "ui_meta": {
                    "hermes-bots": {"title": "Maya", "hidden": False, "section": "Team"},
                    "unrelated": {"keep": True},
                },
                "ui_meta_revisions": {"hermes-bots": 1},
                "canonical_session": {"id": "chat-1"},
            }
        ]
        self.calls = []
        self.reject_cas = False
        self.install_id = "installation-a"

    def call(self, method, params):
        self.calls.append((method, params))
        if method == "profiles.list":
            return {"install_id": self.install_id, "profiles": self.profiles}
        if method == "profiles.configure":
            if self.reject_cas:
                return {"applied": {"ui_meta": False, "ui_meta_conflicts": {"hermes-bots": {}}}}
            row = next(p for p in self.profiles if p["name"] == params["name"])
            row["ui_meta"].update(params["ui_meta"])
            row["ui_meta_revisions"]["hermes-bots"] += 1
            return {"applied": {"ui_meta": True}}
        raise AssertionError(method)


def test_hermes_rename_uses_cas_and_preserves_existing_metadata():
    rpc = FakeRPC()
    hm = Hermes(rpc, "installation-a")
    hm.rename("maya", hm.get("maya"), "Marketing")
    assert rpc.profiles[0]["ui_meta"]["hermes-bots"]["section"] == "Team"
    assert rpc.profiles[0]["ui_meta"]["unrelated"] == {"keep": True}
    writes = [p for method, p in rpc.calls if method == "profiles.configure"]
    assert writes[0]["ui_meta_expected_revisions"] == {"hermes-bots": 1}
    assert hm.get("maya").name == "Marketing"


def test_hermes_wrong_installation_and_partial_application_fail_closed():
    rpc = FakeRPC()
    hm = Hermes(rpc, "installation-a")
    expected = hm.get("maya")
    rpc.install_id = "installation-b"
    with pytest.raises(BridgeError, match="installation"):
        hm.rename("maya", expected, "Marketing")
    rpc.install_id = "installation-a"
    rpc.reject_cas = True
    with pytest.raises(BridgeError, match="revision"):
        hm.rename("maya", expected, "Marketing")


def test_plain_profile_is_not_silently_treated_as_bot():
    rpc = FakeRPC()
    rpc.profiles[0]["ui_meta"] = {}
    with pytest.raises(BridgeError, match="Bot Mode"):
        Hermes(rpc, "installation-a").get("maya")


def test_paperclip_import_creation_disables_both_wake_paths():
    import json

    requests = []
    row = {"id": AGENT, "companyId": COMPANY, "name": "Maya", "updatedAt": "1"}

    def handler(request):
        if request.method == "POST":
            requests.append(json.loads(request.content))
        elif request.method == "PATCH":
            row.update(status="paused")
        return httpx.Response(201 if request.method == "POST" else 200, json=row.copy())

    pc = Paperclip(
        "http://127.0.0.1:3100", COMPANY, "fixture-token", transport=httpx.MockTransport(handler)
    )
    try:
        agent = pc.create("Maya")
        pc.pause(agent)
        assert requests[0]["runtimeConfig"]["heartbeat"] == {
            "enabled": False,
            "wakeOnDemand": False,
        }
        assert requests[0]["adapterConfig"] == {}
        assert requests[0]["adapterType"] == "hermes_gateway"
        assert pc.get(agent).metadata["status"] == "paused"
    finally:
        pc.close()


@pytest.mark.parametrize("field", ["ui_meta", "ui_meta_revisions"])
def test_malformed_nested_metadata_is_a_safe_error(field):
    rpc = FakeRPC()
    rpc.profiles[0][field] = None
    with pytest.raises(BridgeError, match="unsupported"):
        Hermes(rpc, "installation-a").get("maya")
