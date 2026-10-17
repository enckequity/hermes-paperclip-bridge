import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from uuid import UUID

import pytest

from hermes_paperclip_bridge.models import View
from hermes_paperclip_bridge.state import Store
from hermes_paperclip_bridge.wiring import wire

SECRET = str(UUID(int=3))
KEY = "fixture-execution-key-only"


@pytest.fixture
def listener():
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append((self.path, self.headers.get("Authorization")))
            payload = json.dumps(
                {
                    "object": "hermes.api_server.capabilities",
                    "platform": "hermes-agent",
                    "features": {"run_submission": True},
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


def test_wiring_uses_native_profile_auth_secret_reference_and_safe_merge(
    tmp_path, monkeypatch, listener
):
    class Paperclip:
        company_id = "company"

        def __init__(self):
            self.config = {"timeoutSec": 600}
            self.patches = []

        def get(self, _identity):
            return View(
                "Maya", "1", {"adapterType": "hermes_gateway", "adapterConfig": self.config.copy()}
            )

        def request(self, method, path, **kwargs):
            if path == "/api/adapters/hermes_gateway":
                return {"type": "hermes_gateway", "loaded": True, "disabled": False}
            if path.endswith("/secrets"):
                return [{"id": SECRET}]
            assert method == "PATCH"
            self.patches.append(kwargs["json"])
            self.config.update(kwargs["json"]["adapterConfig"])

    class RPC:
        writes = []

        def request(self, method, path, **kwargs):
            self.writes.append((method, path, kwargs["json"]))
            return {"ok": True, "key": "API_SERVER_KEY"}

    class Hermes:
        rpc = RPC()

        def get(self, _identity):
            return View("Maya", "1")

        def profiles(self):
            return []

    base, reads = listener
    path = tmp_path / "state.sqlite"
    store = Store(path, scope="test")
    binding = store.bind("agent", "maya", baseline="Maya")
    pc, hm = Paperclip(), Hermes()
    args = {"execution_url": base, "secret_id": SECRET, "key_env": "FIXTURE_EXECUTION_KEY"}
    try:
        assert wire(store, pc, hm, binding.id, **args)["status"] == "planned"
        assert not hm.rpc.writes and not pc.patches and not reads
        monkeypatch.setenv("FIXTURE_EXECUTION_KEY", KEY)
        result = wire(store, pc, hm, binding.id, **args, apply=True)
        assert result["status"] == "wired" and result["run_verified"] is False
        assert reads == [("/p/maya/v1/capabilities", "Bearer " + KEY)]
        assert hm.rpc.writes == [
            ("PUT", "/api/env", {"profile": "maya", "key": "API_SERVER_KEY", "value": KEY})
        ]
        assert pc.config["apiKey"] == {
            "type": "secret_ref",
            "secretId": SECRET,
            "version": "latest",
        }
        assert pc.config["timeoutSec"] == 600
        assert KEY not in json.dumps(result)
        assert KEY.encode() not in path.read_bytes()
    finally:
        store.close()
