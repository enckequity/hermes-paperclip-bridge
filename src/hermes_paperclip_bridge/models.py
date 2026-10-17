from dataclasses import dataclass, field
from typing import Any


class BridgeError(Exception):
    """A safe, operator-facing failure without remote response or credential material."""


def display_name(value: Any) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > 160
        or any(ord(char) < 32 for char in value)
    ):
        raise BridgeError("Teammate name must contain 1–160 characters without control characters.")
    return value.strip()


@dataclass(frozen=True)
class View:
    name: str
    version: str
    metadata: dict = field(default_factory=dict, compare=False, repr=False)

    def __post_init__(self):
        object.__setattr__(self, "name", display_name(self.name))


@dataclass(frozen=True)
class Binding:
    id: str
    paperclip_id: str
    profile: str
    baseline: str | None
    pending: dict | None
