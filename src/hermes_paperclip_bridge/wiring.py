import os

import httpx

from .config import checked_url, uuid_value
from .models import BridgeError, mapping


def wire(store, paperclip, hermes, binding_id, *, execution_url, secret_id, key_env, apply=False):
    base = checked_url(execution_url)
    secret_id = uuid_value(secret_id)
    with store.exclusive():
        binding = store.get(binding_id)
        pc, hm = paperclip.get(binding.paperclip_id), hermes.get(binding.profile)
        if pc is None or hm is None:
            raise BridgeError("Both bound records must exist before execution wiring.")
        if pc.metadata.get("adapterType") != "hermes_gateway":
            raise BridgeError("Select the native hermes_gateway adapter in Paperclip first.")
        adapter = paperclip.request("GET", "/api/adapters/hermes_gateway")
        if (
            not isinstance(adapter, dict)
            or adapter.get("type") != "hermes_gateway"
            or adapter.get("loaded") is not True
            or adapter.get("disabled") is not False
        ):
            raise BridgeError("The native Paperclip Hermes gateway adapter is unavailable.")
        secrets = paperclip.request("GET", f"/api/companies/{paperclip.company_id}/secrets")
        if not isinstance(secrets, list) or not any(
            isinstance(item, dict) and item.get("id") == secret_id for item in secrets
        ):
            raise BridgeError("The selected Paperclip secret is not in this company.")
        profile_url = base + "/p/" + binding.profile
        if not apply:
            return {
                "status": "planned",
                "binding": binding_id,
                "apiBaseUrl": profile_url,
                "sessionKeyStrategy": "issue",
            }
        key = os.environ.get(key_env)
        if not key or len(key.strip()) < 16:
            raise BridgeError(
                "The execution-key environment variable must contain at least 16 characters."
            )
        hermes.profiles()
        response = hermes.rpc.request(
            "PUT",
            "/api/env",
            json={
                "profile": binding.profile,
                "key": "API_SERVER_KEY",
                "value": key,
            },
        )
        if mapping(response).get("ok") is not True or response.get("key") != "API_SERVER_KEY":
            raise BridgeError("Hermes did not confirm the profile execution key.")
        try:
            with httpx.Client(trust_env=False, follow_redirects=False, timeout=20) as client:
                reply = client.get(
                    profile_url + "/v1/capabilities", headers={"Authorization": f"Bearer {key}"}
                )
                if reply.status_code != 200:
                    raise BridgeError(
                        "The profile execution listener is not ready. The key may "
                        "already be set; inspect the native listener before retrying."
                    )
                capabilities = reply.json()
        except (httpx.HTTPError, ValueError):
            raise BridgeError(
                "Cannot verify the profile execution listener. The key may already "
                "be set; inspect the native listener before retrying."
            ) from None
        if (
            not isinstance(capabilities, dict)
            or capabilities.get("object") != "hermes.api_server.capabilities"
            or capabilities.get("platform") != "hermes-agent"
            or mapping(capabilities.get("features", {})).get("run_submission") is not True
        ):
            raise BridgeError("The execution listener does not advertise native Hermes runs.")
        current = paperclip.get(binding.paperclip_id)
        if current != pc:
            raise BridgeError("Paperclip changed during wiring; inspect it before retrying.")
        config = {
            "apiBaseUrl": profile_url,
            "apiKey": {"type": "secret_ref", "secretId": secret_id, "version": "latest"},
            "sessionKeyStrategy": "issue",
        }
        paperclip.request(
            "PATCH", f"/api/agents/{binding.paperclip_id}", json={"adapterConfig": config}
        )
        after = paperclip.get(binding.paperclip_id)
        actual = mapping(after.metadata.get("adapterConfig", {})) if after else {}
        if (
            actual.get("apiBaseUrl") != profile_url
            or actual.get("sessionKeyStrategy") != "issue"
            or actual.get("apiKey") != config["apiKey"]
        ):
            raise BridgeError("Paperclip did not confirm gateway configuration.")
        return {
            "status": "wired",
            "binding": binding_id,
            "apiBaseUrl": profile_url,
            "sessionKeyStrategy": "issue",
            "run_verified": False,
        }
