import pytest

from hermes_paperclip_bridge.lifecycle import import_bot, provision
from hermes_paperclip_bridge.models import BridgeError, View
from hermes_paperclip_bridge.state import Store


class PC:
    def get(self, identity):
        return View("Maya", "1")


class HM:
    def __init__(self):
        self.created = []
        self.fail = False

    def create_profile(self, key, name):
        self.created.append(key)
        if self.fail:
            raise BridgeError("Reply lost.")

    def finish_bot(self, key, name, operation_id, *, journal):
        return View(name, "1")


def test_creation_is_dry_run_and_then_idempotent(tmp_path):
    store = Store(tmp_path / "state.sqlite", scope="test")
    hm = HM()
    assert provision(store, PC(), hm, "agent")["status"] == "planned"
    assert not store.operations() and not hm.created
    first = provision(store, PC(), hm, "agent", apply=True)
    second = provision(store, PC(), hm, "agent", apply=True)
    assert first["binding"] == second["binding"]
    assert len(hm.created) == 1
    store.close()


def test_unknown_creation_outcome_is_not_retried(tmp_path):
    store = Store(tmp_path / "state.sqlite", scope="test")
    hm = HM()
    hm.fail = True
    with pytest.raises(BridgeError):
        provision(store, PC(), hm, "agent", apply=True)
    hm.fail = False
    with pytest.raises(BridgeError, match="uncertain"):
        provision(store, PC(), hm, "agent", apply=True)
    assert len(hm.created) == 1
    assert not store.bindings()
    store.close()


def test_import_disables_execution_then_pauses_and_resumes_after_failure(tmp_path):
    class ImportPC:
        def __init__(self):
            self.creates = 0
            self.fail = True
            self.paused = False

        def create(self, name, manager):
            self.creates += 1
            return "agent"

        def pause(self, agent):
            if self.fail:
                raise BridgeError("Pause reply lost.")
            self.paused = True

        def get(self, identity):
            return View("Maya", "1")

    class ImportHM:
        def get(self, profile):
            return View("Maya", "1")

    store = Store(tmp_path / "state.sqlite", scope="test")
    pc = ImportPC()
    assert import_bot(store, pc, ImportHM(), "maya")["status"] == "planned"
    assert pc.creates == 0
    with pytest.raises(BridgeError):
        import_bot(store, pc, ImportHM(), "maya", apply=True)
    assert not store.bindings()
    pc.fail = False
    assert import_bot(store, pc, ImportHM(), "maya", apply=True)["paused"] is True
    assert pc.creates == 1 and pc.paused
    assert import_bot(store, pc, ImportHM(), "maya", apply=True)["status"] == "bound"
    store.close()
