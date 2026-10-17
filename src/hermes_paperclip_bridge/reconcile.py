from collections.abc import Callable

from diffsync import Adapter, DiffSyncModel
from diffsync.enum import DiffSyncFlags

from .models import BridgeError


class Teammate(DiffSyncModel):
    _modelname = "teammate"
    _identifiers = ("key",)
    _attributes = ("name",)

    key: str
    name: str

    def update(self, attrs):
        if self.adapter.writer is not None:
            self.adapter.writer(self.key, attrs["name"])
        return super().update(attrs)


class Inventory(Adapter):
    teammate = Teammate
    top_level = ["teammate"]

    def __init__(self, name, *, writer: Callable | None = None):
        super().__init__(name=name)
        self.writer = writer


def _decision(binding, pc, hermes, prefer):
    if prefer is not None:
        return pc.name if prefer == "paperclip" else hermes.name
    if binding.pending:
        pending = binding.pending
        if pc.name not in (pending["paperclip"], pending["name"]):
            return None
        if hermes.name not in (pending["hermes"], pending["name"]):
            return None
        return pending["name"]
    if pc.name == hermes.name:
        return pc.name
    if pc.name == binding.baseline:
        return hermes.name
    if hermes.name == binding.baseline:
        return pc.name
    return None


def reconcile(store, paperclip, hermes, *, apply=False, prefer=None):
    results = []
    prefer = prefer or {}
    if any(side not in ("paperclip", "hermes") for side in prefer.values()):
        raise BridgeError("Resolution must select paperclip or hermes.")
    with store.exclusive():
        for binding in store.bindings():
            result = {"binding": binding.id}
            try:
                pc, hm = paperclip.get(binding.paperclip_id), hermes.get(binding.profile)
                if pc is None or hm is None:
                    results.append({**result, "status": "missing"})
                    continue
                name = _decision(binding, pc, hm, prefer.get(binding.id))
                if name is None:
                    results.append({**result, "status": "conflict", "paperclip": pc.name,
                                    "hermes": hm.name})
                    continue
                desired = Inventory("accepted")
                desired.add(Teammate(key=binding.id, name=name))
                changed = pc.name != name or hm.name != name
                if not apply:
                    results.append({**result, "status": "planned" if changed else "unchanged",
                                    "name": name})
                    continue
                if changed and not binding.pending:
                    store.pending(binding.id, name, pc.name, hm.name)
                elif changed and prefer.get(binding.id):
                    store.pending(binding.id, name, pc.name, hm.name)
                for endpoint, identity, expected in (
                    (paperclip, binding.paperclip_id, pc), (hermes, binding.profile, hm),
                ):
                    def write(_key, target, endpoint=endpoint, identity=identity, expected=expected):
                        endpoint.rename(identity, expected, target)

                    target = Inventory("endpoint", writer=write)
                    target.add(Teammate(key=binding.id, name=expected.name))
                    flags = DiffSyncFlags.SKIP_UNMATCHED_DST
                    diff = target.diff_from(desired, flags=flags)
                    target.sync_from(desired, diff=diff, flags=flags)
                pc_after = paperclip.get(binding.paperclip_id)
                hm_after = hermes.get(binding.profile)
                if pc_after is None or hm_after is None or pc_after.name != name or hm_after.name != name:
                    raise BridgeError("Teammate readback did not match the intended name.")
                store.finish(binding.id, name)
                completed = changed or binding.pending is not None
                results.append({**result, "status": "synced" if completed else "unchanged", "name": name})
            except BridgeError as exc:
                results.append({**result, "status": "error", "message": str(exc)})
    return results
