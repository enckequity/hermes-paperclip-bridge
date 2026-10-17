import hashlib
import json
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

from .models import BridgeError


def checked_url(value):
    if not isinstance(value, str) or any(ord(char) < 32 for char in value):
        raise BridgeError("Use a valid listener root URL.")
    try:
        parsed = urlsplit(value)
        _ = parsed.port
    except ValueError:
        raise BridgeError("Use a valid listener URL and port.") from None
    if (
        parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or not parsed.hostname
        or parsed.scheme not in ("https", "http")
        or parsed.path not in ("", "/")
    ):
        raise BridgeError("Use an HTTP(S) URL without credentials, query, or fragment.")
    if parsed.scheme == "http" and parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
        raise BridgeError("Remote connections require HTTPS.")
    return value.rstrip("/")


def uuid_value(value):
    try:
        return str(UUID(value))
    except (ValueError, TypeError, AttributeError):
        raise BridgeError("Expected a UUID identifier.") from None


@dataclass(frozen=True)
class Endpoint:
    url: str
    token_env: str

    def token(self):
        value = os.environ.get(self.token_env)
        if not value:
            raise BridgeError("The configured credential environment variable is missing.")
        return value


@dataclass(frozen=True)
class Settings:
    state: Path
    paperclip: Endpoint
    hermes: Endpoint
    company_id: str
    install_id: str
    auth_mode: str
    scope: str

    @classmethod
    def load(cls, path):
        try:
            path = Path(path).resolve()
            data = tomllib.loads(path.read_text(encoding="utf-8"))
            pc, hm = data["paperclip"], data["hermes"]
            pc_url, hm_url = checked_url(pc["url"]), checked_url(hm["url"])
            company = uuid_value(pc["company_id"])
            installation = hm["install_id"]
            if not isinstance(installation, str) or not installation:
                raise BridgeError("Configure the expected Hermes installation ID.")
            mode = hm.get("auth_mode", "bearer")
            if mode not in ("bearer", "loopback"):
                raise BridgeError("Hermes auth_mode must be bearer or loopback.")
            if mode == "loopback" and urlsplit(hm_url).hostname not in (
                "localhost",
                "127.0.0.1",
                "::1",
            ):
                raise BridgeError("Session-token authentication requires loopback.")
            scope = hashlib.sha256(
                json.dumps([pc_url, company, hm_url, installation]).encode()
            ).hexdigest()
            return cls(
                (path.parent / data.get("state", "bridge.sqlite")).resolve(),
                Endpoint(pc_url, pc["token_env"]),
                Endpoint(hm_url, hm["token_env"]),
                company,
                installation,
                mode,
                scope,
            )
        except (OSError, ValueError, KeyError, TypeError):
            raise BridgeError("Cannot read bridge configuration; check the TOML fields.") from None
