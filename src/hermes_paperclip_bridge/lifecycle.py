from uuid import uuid4

from .models import BridgeError


def bind(store, paperclip, hermes, agent, profile, *, apply=False):
    with store.exclusive():
        pc, hm = paperclip.get(agent), hermes.get(profile)
        if pc is None or hm is None:
            raise BridgeError("Both records must exist before binding.")
        if not apply:
            return {"status": "planned", "agent": agent, "profile": profile}
        baseline = pc.name if pc.name == hm.name else None
        binding = store.bind(agent, profile, baseline=baseline)
        return {"status": "bound", "binding": binding.id, "names_match": baseline is not None}


def provision(store, paperclip, hermes, agent, *, apply=False):
    with store.exclusive():
        existing = next((b for b in store.bindings() if b.paperclip_id == agent), None)
        if existing:
            return {"status": "bound", "binding": existing.id, "profile": existing.profile}
        pc = paperclip.get(agent)
        if pc is None:
            raise BridgeError("Paperclip agent does not exist.")
        if not apply:
            return {"status": "planned", "agent": agent, "execution_wired": False}
        operation = store.operation("provision", agent)
        if operation is None:
            operation = store.start("provision", agent, "pc-" + uuid4().hex)
        if operation["phase"] in ("creating", "uncertain"):
            raise BridgeError(
                "Profile creation outcome is uncertain. Inspect both systems and bind "
                "the confirmed profile explicitly; automatic retry is disabled."
            )
        if operation["phase"] == "prepared":
            store.phase(operation["id"], "creating")
            try:
                hermes.create_profile(operation["target"], pc.name)
            except Exception:
                store.phase(operation["id"], "uncertain")
                raise
            store.phase(operation["id"], "profile_created")
        bot = hermes.finish_bot(operation["target"], pc.name, operation["id"], journal=store)
        binding = store.bind(
            agent, operation["target"], baseline=pc.name if pc.name == bot.name else None
        )
        store.phase(operation["id"], "bound")
        return {
            "status": "bound",
            "binding": binding.id,
            "profile": binding.profile,
            "execution_wired": False,
        }


def import_bot(store, paperclip, hermes, profile, *, manager=None, apply=False):
    with store.exclusive():
        existing = next((b for b in store.bindings() if b.profile == profile), None)
        if existing:
            return {"status": "bound", "binding": existing.id, "agent": existing.paperclip_id}
        bot = hermes.get(profile)
        if bot is None:
            raise BridgeError("The Hermes bot does not exist.")
        if not apply:
            return {"status": "planned", "profile": profile, "execution_wired": False}
        operation = store.operation("import", profile)
        if operation is None:
            operation = store.start("import", profile, "")
        if operation["phase"] in ("creating", "uncertain"):
            raise BridgeError(
                "Agent creation outcome is uncertain. Inspect Paperclip and bind "
                "the confirmed agent explicitly; automatic retry is disabled."
            )
        if operation["phase"] == "prepared":
            store.phase(operation["id"], "creating")
            try:
                agent = paperclip.create(bot.name, manager)
            except Exception:
                store.phase(operation["id"], "uncertain")
                raise
            store.phase(operation["id"], "agent_created", target=agent)
            operation = store.operation("import", profile)
        agent = operation["target"]
        paperclip.pause(agent)
        pc = paperclip.get(agent)
        binding = store.bind(agent, profile, baseline=bot.name if pc.name == bot.name else None)
        store.phase(operation["id"], "bound")
        return {
            "status": "bound",
            "binding": binding.id,
            "agent": agent,
            "execution_wired": False,
            "paused": True,
        }
