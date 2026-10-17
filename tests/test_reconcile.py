from dataclasses import replace

import pytest

from hermes_paperclip_bridge.models import BridgeError, View
from hermes_paperclip_bridge.reconcile import reconcile
from hermes_paperclip_bridge.state import Store


class Endpoint:
    def __init__(self, name):
        self.view = View(name=name, version="1") if name is not None else None
        self.writes = []
        self.fail_after_write = False

    def get(self, _identity):
        return self.view

    def rename(self, _identity, expected, name):
        if self.view != expected:
            raise BridgeError("Teammate changed during reconciliation.")
        self.writes.append(name)
        self.view = replace(self.view, name=name, version=str(int(self.view.version) + 1))
        if self.fail_after_write:
            raise BridgeError("Connection lost after write.")


@pytest.fixture
def setup(tmp_path):
    store = Store(tmp_path / "state.sqlite", scope="test")
    binding = store.bind("pc-1", "maya", baseline="Maya")
    yield store, binding
    store.close()


@pytest.mark.parametrize("apply", [False, True])
def test_paperclip_rename_reaches_hermes_only_on_apply(setup, apply):
    store, binding = setup
    pc, hermes = Endpoint("Maya Marketing"), Endpoint("Maya")
    result = reconcile(store, pc, hermes, apply=apply)
    assert result[0]["status"] == ("synced" if apply else "planned")
    assert hermes.writes == (["Maya Marketing"] if apply else [])
    assert store.get(binding.id).baseline == ("Maya Marketing" if apply else "Maya")


def test_hermes_rename_reaches_paperclip(setup):
    store, _ = setup
    pc, hermes = Endpoint("Maya"), Endpoint("Maya Research")
    reconcile(store, pc, hermes, apply=True)
    assert pc.writes == ["Maya Research"]


def test_concurrent_edits_conflict_without_writes(setup):
    store, _ = setup
    pc, hermes = Endpoint("PC change"), Endpoint("Hermes change")
    assert reconcile(store, pc, hermes, apply=True)[0]["status"] == "conflict"
    assert pc.writes == hermes.writes == []


def test_identical_concurrent_changes_advance_baseline(setup):
    store, binding = setup
    pc, hermes = Endpoint("New Maya"), Endpoint("New Maya")
    reconcile(store, pc, hermes, apply=True)
    assert store.get(binding.id).baseline == "New Maya"
    assert pc.writes == hermes.writes == []


def test_missing_record_never_propagates_deletion(setup):
    store, _ = setup
    pc, hermes = Endpoint(None), Endpoint("Maya")
    assert reconcile(store, pc, hermes, apply=True)[0]["status"] == "missing"
    assert hermes.writes == []


def test_lost_write_reply_recovers_from_readback_on_next_run(setup):
    store, binding = setup
    pc, hermes = Endpoint("New Maya"), Endpoint("Maya")
    hermes.fail_after_write = True
    assert reconcile(store, pc, hermes, apply=True)[0]["status"] == "error"
    assert store.get(binding.id).pending is not None
    hermes.fail_after_write = False
    assert reconcile(store, pc, hermes, apply=True)[0]["status"] == "synced"
    assert hermes.writes == ["New Maya"]
    assert store.get(binding.id).pending is None


def test_edit_after_interrupted_write_stays_conflicted(setup):
    store, binding = setup
    store.pending(binding.id, "New Maya", "New Maya", "Maya")
    pc, hermes = Endpoint("New Maya"), Endpoint("Unrelated edit")
    assert reconcile(store, pc, hermes, apply=True)[0]["status"] == "conflict"
    assert pc.writes == hermes.writes == []


def test_explicit_resolution_selects_a_side(setup):
    store, binding = setup
    pc, hermes = Endpoint("PC change"), Endpoint("Hermes change")
    reconcile(store, pc, hermes, apply=True, prefer={binding.id: "hermes"})
    assert pc.writes == ["Hermes change"]


def test_state_rejects_endpoint_scope_change(tmp_path):
    path = tmp_path / "state.sqlite"
    Store(path, scope="company-a").close()
    with pytest.raises(BridgeError, match="scope"):
        Store(path, scope="company-b")


def test_state_rejects_duplicate_identity_binding(setup):
    store, _ = setup
    with pytest.raises(BridgeError, match="already"):
        store.bind("pc-1", "another-profile")


def test_resolution_only_touches_selected_binding(setup):
    store, binding = setup
    other = store.bind("pc-2", "another-profile", baseline="Maya")
    pc, hm = Endpoint("New Maya"), Endpoint("Maya")
    results = reconcile(
        store, pc, hm, apply=True, prefer={binding.id: "paperclip"}, only={binding.id}
    )
    assert [r["binding"] for r in results] == [binding.id]
    assert store.get(other.id).baseline == "Maya"


def test_second_process_cannot_open_locked_state(tmp_path):
    path = tmp_path / "state.sqlite"
    store = Store(path, scope="test")
    try:
        with store.exclusive(), pytest.raises(BridgeError, match="process"):
            Store(path, scope="test")
    finally:
        store.close()
