import json
import sqlite3
from pathlib import Path
from uuid import uuid4

from filelock import FileLock, Timeout

from .models import Binding, BridgeError


class Store:
    def __init__(self, path: Path, *, scope: str):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = FileLock(str(self.path) + ".lock", timeout=0)
        self.db = sqlite3.connect(self.path, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        try:
            with self.exclusive():
                version = self.db.execute("PRAGMA user_version").fetchone()[0]
                if version not in (0, 1):
                    raise BridgeError("This state file requires a different bridge version.")
                self.db.executescript("""
                    CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                    CREATE TABLE IF NOT EXISTS bindings (
                        id TEXT PRIMARY KEY, paperclip_id TEXT UNIQUE NOT NULL,
                        profile TEXT UNIQUE NOT NULL, baseline TEXT, pending TEXT
                    );
                    CREATE TABLE IF NOT EXISTS operations (
                        id TEXT PRIMARY KEY, kind TEXT NOT NULL, source TEXT NOT NULL,
                        target TEXT NOT NULL, phase TEXT NOT NULL, UNIQUE(kind, source)
                    );
                """)
                row = self.db.execute("SELECT value FROM settings WHERE key='scope'").fetchone()
                if row is not None and row[0] != scope:
                    raise BridgeError("State scope differs from the configured company or runtime.")
                self.db.execute("INSERT OR IGNORE INTO settings VALUES ('scope', ?)", (scope,))
                self.db.execute("PRAGMA user_version=1")
        except Exception:
            self.db.close()
            raise

    def exclusive(self):
        try:
            return self.lock.acquire()
        except Timeout:
            raise BridgeError("Another bridge process holds this state file.") from None

    def close(self):
        self.db.close()

    @staticmethod
    def _binding(row):
        return Binding(
            row["id"],
            row["paperclip_id"],
            row["profile"],
            row["baseline"],
            json.loads(row["pending"]) if row["pending"] else None,
        )

    def bindings(self):
        return [self._binding(row) for row in self.db.execute("SELECT * FROM bindings ORDER BY id")]

    def get(self, binding_id):
        row = self.db.execute("SELECT * FROM bindings WHERE id=?", (binding_id,)).fetchone()
        if row is None:
            raise BridgeError("Binding does not exist.")
        return self._binding(row)

    def bind(self, paperclip_id, profile, *, baseline=None):
        binding_id = str(uuid4())
        try:
            self.db.execute(
                "INSERT INTO bindings VALUES (?, ?, ?, ?, NULL)",
                (binding_id, paperclip_id, profile, baseline),
            )
        except sqlite3.IntegrityError:
            raise BridgeError(
                "A teammate is already bound. Inspect the existing binding."
            ) from None
        return self.get(binding_id)

    def pending(self, binding_id, name, paperclip_before, hermes_before):
        payload = {"name": name, "paperclip": paperclip_before, "hermes": hermes_before}
        self.db.execute(
            "UPDATE bindings SET pending=? WHERE id=?", (json.dumps(payload), binding_id)
        )

    def finish(self, binding_id, name):
        self.db.execute(
            "UPDATE bindings SET baseline=?, pending=NULL WHERE id=?", (name, binding_id)
        )

    def operation(self, kind, source):
        row = self.db.execute(
            "SELECT * FROM operations WHERE kind=? AND source=?", (kind, source)
        ).fetchone()
        return dict(row) if row else None

    def start(self, kind, source, target):
        self.db.execute(
            "INSERT INTO operations VALUES (?, ?, ?, ?, 'prepared')",
            (str(uuid4()), kind, source, target),
        )
        return self.operation(kind, source)

    def phase(self, operation_id, phase, *, target=None):
        if target is None:
            self.db.execute("UPDATE operations SET phase=? WHERE id=?", (phase, operation_id))
        else:
            self.db.execute(
                "UPDATE operations SET phase=?,target=? WHERE id=?", (phase, target, operation_id)
            )

    def operations(self):
        return [dict(row) for row in self.db.execute("SELECT * FROM operations ORDER BY id")]
