import httpx

from .config import checked_url, uuid_value
from .models import BridgeError, View, display_name


class Paperclip:
    def __init__(self, url, company_id, token, *, transport=None):
        self.company_id = uuid_value(company_id)
        self.http = httpx.Client(
            base_url=checked_url(url),
            headers={"Authorization": f"Bearer {token}"},
            timeout=20,
            follow_redirects=False,
            trust_env=False,
            transport=transport,
        )

    def close(self):
        self.http.close()

    def request(self, method, path, **kwargs):
        try:
            response = self.http.request(method, path, **kwargs)
            if response.status_code == 404 and method == "GET":
                return None
            if not 200 <= response.status_code < 300:
                raise BridgeError(f"Paperclip returned HTTP {response.status_code}.")
            return response.json()
        except (httpx.HTTPError, ValueError):
            raise BridgeError("Paperclip request failed; inspect the service connection.") from None

    def get(self, identity):
        identity = uuid_value(identity)
        row = self.request("GET", f"/api/agents/{identity}")
        if row is None:
            return None
        if not isinstance(row, dict) or row.get("companyId") != self.company_id:
            raise BridgeError("Paperclip agent belongs to another company.")
        if row.get("id") != identity:
            raise BridgeError("Paperclip returned a different agent identifier.")
        return View(row.get("name"), str(row.get("updatedAt", "")), row)

    def rename(self, identity, expected, name):
        name = display_name(name)
        current = self.get(identity)
        if current is None or current != expected:
            raise BridgeError("Paperclip changed since the plan; reconcile again.")
        self.request("PATCH", f"/api/agents/{uuid_value(identity)}", json={"name": name})
        result = self.get(identity)
        if result is None or result.name != name:
            raise BridgeError("Paperclip name readback did not match.")

    def create(self, name, manager=None):
        if manager is not None and self.get(manager) is None:
            raise BridgeError("The selected manager does not exist in this company.")
        payload = {
            "name": display_name(name),
            "role": "general",
            "adapterType": "hermes_gateway",
            "adapterConfig": {},
            "runtimeConfig": {"heartbeat": {"enabled": False, "wakeOnDemand": False}},
        }
        if manager is not None:
            payload["reportsTo"] = uuid_value(manager)
        row = self.request("POST", f"/api/companies/{self.company_id}/agents", json=payload)
        if not isinstance(row, dict) or row.get("companyId") != self.company_id:
            raise BridgeError("Paperclip did not confirm creation in this company.")
        return uuid_value(row.get("id"))

    def pause(self, identity):
        if self.get(identity) is None:
            raise BridgeError("The imported Paperclip agent is missing.")
        self.request("PATCH", f"/api/agents/{uuid_value(identity)}", json={"status": "paused"})
        result = self.get(identity)
        if result is None or result.metadata.get("status") != "paused":
            raise BridgeError("Paperclip did not confirm paused status.")
