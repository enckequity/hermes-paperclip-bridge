import copy

import pytest

from hermes_paperclip_bridge.hermes import Hermes
from hermes_paperclip_bridge.models import BridgeError
from hermes_paperclip_bridge.state import Store


@pytest.fixture
def journal(tmp_path):
    store = Store(tmp_path / "state.sqlite", scope="test")
    yield store
    store.close()


class RPCFixture:
    def __init__(self):
        self.rows = []
        self.sessions = []
        self.calls = []
        self.list_failure = False

    def call(self, method, params):
        self.calls.append((method, copy.deepcopy(params)))
        if method == "profiles.list":
            return {"install_id": "fixture", "profiles": copy.deepcopy(self.rows)}
        if method == "profiles.create":
            self.rows.append({"name": params["name"], "ui_meta": {}, "ui_meta_revisions": {}})
            return {"ok": True, "name": params["name"]}
        if method == "profiles.configure":
            self.rows[0]["ui_meta"].update(params["ui_meta"])
            self.rows[0]["ui_meta_revisions"]["hermes-bots"] = 1
            return {"applied": {"ui_meta": True}}
        if method == "session.list":
            if self.list_failure:
                raise BridgeError("Unavailable.")
            return {"sessions": copy.deepcopy(self.sessions)}
        if method == "session.create":
            self.sessions.append({"id": "stored", "title": "Bot Chat"})
            return {"session_id": "runtime", "stored_session_id": "stored"}
        if method == "session.title":
            self.rows[0]["canonical_session"] = {
                "id": "stored",
                "resolved_id": "stored",
                "root_title": "Bot Chat",
            }
            return {"pending": False, "title": "Bot Chat"}
        raise AssertionError(method)


def test_full_native_bot_creation_never_copies_credentials_or_calls_model(journal):
    rpc = RPCFixture()
    hermes = Hermes(rpc, "fixture")
    hermes.create_profile("pc-fixture", "Maya")
    assert hermes.finish_bot("pc-fixture", "Maya", "operation", journal=journal).name == "Maya"
    assert hermes.finish_bot("pc-fixture", "Maya", "operation", journal=journal).name == "Maya"
    create = next(p for method, p in rpc.calls if method == "profiles.create")
    assert create["mirror_credentials"] is False and create["share_auth"] is False
    assert "clone_from" not in create
    assert sum(method == "session.create" for method, _ in rpc.calls) == 1
    assert not any("prompt" in p or method.startswith("chat.") for method, p in rpc.calls)


def test_unavailable_session_list_does_not_create_another_chat(journal):
    rpc = RPCFixture()
    hm = Hermes(rpc, "fixture")
    hm.create_profile("pc-fixture", "Maya")
    rpc.list_failure = True
    with pytest.raises(BridgeError):
        hm.finish_bot("pc-fixture", "Maya", "operation", journal=journal)
    assert not any(method == "session.create" for method, _ in rpc.calls)


def test_wrong_canonical_readback_is_rejected(journal):
    rpc = RPCFixture()
    hm = Hermes(rpc, "fixture")
    hm.create_profile("pc-fixture", "Maya")
    hm.finish_bot("pc-fixture", "Maya", "operation", journal=journal)
    rpc.rows[0]["canonical_session"]["id"] = "another-session"
    with pytest.raises(BridgeError, match="canonical"):
        hm.finish_bot("pc-fixture", "Maya", "operation", journal=journal)


def test_lost_session_create_reply_never_retries_after_native_cache_loss(journal):
    class LostReply(RPCFixture):
        def call(self, method, params):
            result = super().call(method, params)
            if method == "session.create":
                self.sessions.clear()
                raise BridgeError("Creation reply lost.")
            return result

    rpc = LostReply()
    hm = Hermes(rpc, "fixture")
    hm.create_profile("pc-fixture", "Maya")
    with pytest.raises(BridgeError, match="lost"):
        hm.finish_bot("pc-fixture", "Maya", "operation", journal=journal)
    with pytest.raises(BridgeError, match="uncertain"):
        hm.finish_bot("pc-fixture", "Maya", "operation", journal=journal)
    assert sum(method == "session.create" for method, _ in rpc.calls) == 1


def test_known_session_receipt_resumes_title_without_another_create(journal):
    class LostTitle(RPCFixture):
        fail = True

        def call(self, method, params):
            if method == "session.title" and self.fail:
                self.sessions.clear()
                raise BridgeError("Title not sent.")
            return super().call(method, params)

    rpc = LostTitle()
    hm = Hermes(rpc, "fixture")
    hm.create_profile("pc-fixture", "Maya")
    with pytest.raises(BridgeError):
        hm.finish_bot("pc-fixture", "Maya", "operation", journal=journal)
    rpc.fail = False
    assert hm.finish_bot("pc-fixture", "Maya", "operation", journal=journal).name == "Maya"
    assert sum(method == "session.create" for method, _ in rpc.calls) == 1
