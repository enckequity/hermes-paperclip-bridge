import json
import time
from urllib.parse import urlencode, urlsplit, urlunsplit
from uuid import uuid4

import httpx
from websockets.exceptions import WebSocketException
from websockets.sync.client import connect

from .config import checked_url
from .models import BridgeError, mapping


class RPC:
    def __init__(self, url, token, mode="bearer", *, timeout=20):
        self.url = checked_url(url)
        self._token = token
        self.mode = mode
        self.timeout = timeout
        if mode not in ("bearer", "loopback"):
            raise BridgeError("Unsupported Hermes authentication mode.")
        if mode == "loopback" and urlsplit(url).hostname not in ("localhost", "127.0.0.1", "::1"):
            raise BridgeError("Session-token authentication requires loopback.")

    def request(self, method, path, **kwargs):
        headers = (
            {"Authorization": f"Bearer {self._token}"}
            if self.mode == "bearer"
            else {"X-Hermes-Session-Token": self._token}
        )
        try:
            with httpx.Client(
                base_url=self.url,
                headers=headers,
                trust_env=False,
                follow_redirects=False,
                timeout=self.timeout,
            ) as client:
                response = client.request(method, path, **kwargs)
                if not 200 <= response.status_code < 300:
                    raise BridgeError(f"Hermes returned HTTP {response.status_code}.")
                return response.json()
        except (httpx.HTTPError, ValueError):
            raise BridgeError("Hermes management request failed.") from None

    def call(self, method, params):
        parsed = urlsplit(self.url)
        path = parsed.path.rstrip("/") + "/api/ws"
        protocols = None
        query = ""
        if self.mode == "bearer":
            ticket = mapping(self.request("POST", "/api/auth/ws-ticket")).get("ticket")
            if not isinstance(ticket, str) or not ticket:
                raise BridgeError("Hermes did not issue a WebSocket ticket.")
            protocols = ["hermes-gateway-v1", "hermes-gateway-ticket." + ticket]
        else:
            query = urlencode({"token": self._token})
        url = urlunsplit(
            ("wss" if parsed.scheme == "https" else "ws", parsed.netloc, path, query, "")
        )
        request_id = str(uuid4())
        deadline = time.monotonic() + self.timeout
        try:
            with connect(
                url,
                subprotocols=protocols,
                proxy=None,
                open_timeout=self.timeout,
                close_timeout=2,
                max_size=2**21,
            ) as ws:
                ws.send(
                    json.dumps(
                        {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
                    )
                )
                for _ in range(1000):
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise BridgeError("Hermes RPC timed out.")
                    reply = json.loads(ws.recv(timeout=remaining))
                    if not isinstance(reply, dict) or reply.get("id") != request_id:
                        continue
                    if "error" in reply:
                        raise BridgeError(f"Hermes rejected RPC method {method}.")
                    result = reply.get("result")
                    if not isinstance(result, dict):
                        raise BridgeError("Hermes RPC returned an unsupported result.")
                    return result
                raise BridgeError("Hermes RPC event limit reached.")
        except (WebSocketException, OSError, TimeoutError, ValueError):
            raise BridgeError(
                "Hermes RPC connection failed; the write outcome may be uncertain."
            ) from None
