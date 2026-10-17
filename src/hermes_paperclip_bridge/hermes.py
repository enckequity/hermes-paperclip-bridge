import copy
import json
import re
import time

from .models import BridgeError, View, display_name, mapping


def profile_key(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value):
        raise BridgeError("Invalid Hermes profile key.")
    return value


class Hermes:
    def __init__(self, rpc, install_id):
        self.rpc = rpc
        self.install_id = install_id

    def profiles(self):
        result = self.rpc.call("profiles.list", {})
        if not isinstance(result, dict) or result.get("install_id") != self.install_id:
            raise BridgeError("Hermes installation identity does not match configuration.")
        rows = result.get("profiles")
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise BridgeError("Hermes profile list has an unsupported response.")
        return rows

    def raw(self, key):
        key = profile_key(key)
        rows = [row for row in self.profiles() if row.get("name") == key]
        if len(rows) > 1:
            raise BridgeError("Hermes returned duplicate profile identities.")
        return copy.deepcopy(rows[0]) if rows else None

    def get(self, identity):
        row = self.raw(identity)
        if row is None:
            return None
        meta = mapping(row.get("ui_meta", {})).get("hermes-bots")
        if not isinstance(meta, dict) or not meta.get("title"):
            raise BridgeError("The Hermes profile is not configured for Bot Mode.")
        revision = mapping(row.get("ui_meta_revisions", {})).get("hermes-bots")
        if not isinstance(revision, int):
            raise BridgeError("Hermes did not return the Bot metadata revision.")
        return View(meta["title"], str(revision), row)

    def configure_bot(self, identity, meta, revision):
        self.profiles()
        result = self.rpc.call(
            "profiles.configure",
            {
                "name": profile_key(identity),
                "ui_meta": {"hermes-bots": meta},
                "ui_meta_expected_revisions": {"hermes-bots": revision},
            },
        )
        if mapping(mapping(result).get("applied", {})).get("ui_meta") is not True:
            raise BridgeError("Hermes rejected the Bot metadata revision.")

    def rename(self, identity, expected, name):
        name = display_name(name)
        current = self.get(identity)
        if current is None or current != expected:
            raise BridgeError("Hermes changed since the plan; reconcile again.")
        meta = copy.deepcopy(current.metadata["ui_meta"]["hermes-bots"])
        meta["title"] = name
        self.configure_bot(identity, meta, int(current.version))
        result = self.get(identity)
        if result is None or result.name != name:
            raise BridgeError("Hermes name readback did not match.")

    def create_profile(self, key, name):
        if self.raw(key) is not None:
            raise BridgeError("The target profile already exists; inspect it before binding.")
        result = self.rpc.call(
            "profiles.create",
            {
                "name": profile_key(key),
                "description": display_name(name),
                "mirror_credentials": False,
                "share_auth": False,
                "no_alias": True,
                "no_skills": True,
            },
        )
        if mapping(result).get("ok") is not True or result.get("name") != key:
            raise BridgeError("Hermes did not confirm profile creation.")

    def finish_bot(self, key, name, operation_id, *, journal):
        row = self.raw(key)
        if row is None:
            raise BridgeError("The created Hermes profile is missing.")
        meta = copy.deepcopy(mapping(row.get("ui_meta", {})).get("hermes-bots", {}))
        if not isinstance(meta, dict):
            raise BridgeError("Hermes Bot metadata has an unsupported response.")
        if not meta:
            self.configure_bot(
                key,
                {
                    "title": display_name(name),
                    "description": "",
                    "hidden": False,
                    "created": int(time.time() * 1000),
                },
                mapping(row.get("ui_meta_revisions", {})).get("hermes-bots", 0),
            )
        operation = journal.operation("session", key)
        if operation and operation["phase"] in ("creating", "uncertain"):
            raise BridgeError(
                "Bot Chat creation outcome is uncertain; inspect the native sessions "
                "and bind the verified bot explicitly. Automatic retry is disabled."
            )
        sessions = self.rpc.call(
            "session.list",
            {
                "profile": key,
                "title": "Bot Chat",
                "include_hidden": True,
                "limit": 100,
            },
        )
        rows = mapping(sessions).get("sessions")
        if not isinstance(rows, list) or any(not isinstance(s, dict) for s in rows):
            raise BridgeError("Hermes session list has an unsupported response.")
        chats = [s for s in rows if s.get("title") == "Bot Chat"]
        if len(chats) > 1:
            raise BridgeError("Multiple Bot Chat sessions require operator review.")
        stored_id = chats[0].get("id") if chats else None
        if operation and operation["phase"] in ("created", "ready"):
            receipt = mapping(json.loads(operation["target"]))
            if stored_id and stored_id != receipt["stored_session_id"]:
                raise BridgeError("The canonical chat differs from its creation receipt.")
            stored_id = receipt["stored_session_id"]
        if not chats:
            if operation is None:
                operation = journal.start("session", key, "")
            if operation["phase"] == "prepared":
                journal.phase(operation["id"], "creating")
                try:
                    session = mapping(
                        self.rpc.call(
                            "session.create",
                            {
                                "profile": key,
                                "title": "Bot Chat",
                                "hidden": True,
                                "follow_profile_config": True,
                                "idempotency_key": operation_id,
                            },
                        )
                    )
                    if (
                        not isinstance(session.get("session_id"), str)
                        or not session["session_id"]
                        or not isinstance(session.get("stored_session_id"), str)
                        or not session["stored_session_id"]
                    ):
                        raise BridgeError("Hermes did not confirm session creation.")
                except Exception:
                    journal.phase(operation["id"], "uncertain")
                    raise
                journal.phase(
                    operation["id"],
                    "created",
                    target=json.dumps(
                        {
                            "session_id": session["session_id"],
                            "stored_session_id": session["stored_session_id"],
                        }
                    ),
                )
                receipt = session
                stored_id = session["stored_session_id"]
            title = mapping(
                self.rpc.call(
                    "session.title",
                    {
                        "session_id": receipt["session_id"],
                        "title": "Bot Chat",
                    },
                )
            )
            if title.get("pending") is not False or title.get("title") != "Bot Chat":
                raise BridgeError("Hermes did not persist the canonical chat title.")
        result = self.get(key)
        canonical = result.metadata.get("canonical_session") if result else None
        if (
            not isinstance(canonical, dict)
            or not stored_id
            or canonical.get("id") != stored_id
            or not isinstance(canonical.get("resolved_id"), str)
            or not canonical["resolved_id"]
            or canonical.get("root_title") != "Bot Chat"
        ):
            raise BridgeError("Hermes did not confirm a canonical Bot Chat.")
        if result.name != display_name(name):
            raise BridgeError("The created Bot title changed; inspect it before binding.")
        if operation:
            journal.phase(operation["id"], "ready")
        return result
