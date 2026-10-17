import json
from threading import Thread

import pytest
from websockets.sync.server import serve

from hermes_paperclip_bridge.models import BridgeError
from hermes_paperclip_bridge.rpc import RPC


def test_real_websocket_transport_ignores_events_and_matches_reply():
    seen = []

    def handler(ws):
        seen.append(ws.request.path)
        ws.send(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "method": "event",
                    "params": {"type": "gateway.ready", "payload": {}},
                }
            )
        )
        request = json.loads(ws.recv(timeout=2))
        seen.append(request)
        ws.send(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": request["id"],
                    "result": {"install_id": "fixture", "profiles": []},
                }
            )
        )

    with serve(handler, "127.0.0.1", 0) as server:
        thread = Thread(target=server.serve_forever)
        thread.start()
        try:
            port = server.socket.getsockname()[1]
            rpc = RPC(f"http://127.0.0.1:{port}", "fixture-token", "loopback")
            assert rpc.call("profiles.list", {})["install_id"] == "fixture"
        finally:
            server.shutdown()
            thread.join(timeout=5)
            assert not thread.is_alive()
    assert seen[0] == "/api/ws?token=fixture-token"
    assert seen[1]["method"] == "profiles.list"


def test_remote_session_token_is_rejected():
    with pytest.raises(BridgeError, match="loopback"):
        RPC("https://example.com", "fixture-token", "loopback")


def test_bearer_ticket_uses_native_subprotocol_without_token_in_url(monkeypatch):
    from hermes_paperclip_bridge import rpc as module

    captured = {}

    class WS:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def send(self, text):
            self.request = json.loads(text)

        def recv(self, **kwargs):
            return json.dumps({"id": self.request["id"], "result": {"profiles": []}})

    def connect(url, **kwargs):
        captured.update(url=url, **kwargs)
        return WS()

    rpc = RPC("https://hermes.example", "fixture-bearer-secret")
    monkeypatch.setattr(rpc, "request", lambda method, path: {"ticket": "fixture-ticket"})
    monkeypatch.setattr(module, "connect", connect)
    assert rpc.call("profiles.list", {}) == {"profiles": []}
    assert captured["url"] == "wss://hermes.example/api/ws"
    assert captured["subprotocols"] == ["hermes-gateway-v1", "hermes-gateway-ticket.fixture-ticket"]
    assert captured["proxy"] is None


def test_malformed_ticket_is_safe_error(monkeypatch):
    rpc = RPC("https://hermes.example", "fixture-secret")
    monkeypatch.setattr(rpc, "request", lambda *_args: None)
    with pytest.raises(BridgeError, match="unsupported"):
        rpc.call("profiles.list", {})
