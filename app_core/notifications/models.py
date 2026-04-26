"""Value objects for ntfy notifications."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class NtfyAction:
    """A view action attached to an ntfy notification."""

    label: str
    url: str
    clear: bool = True

    def as_ntfy_json(self) -> dict[str, object]:
        return {
            "action": "view",
            "label": self.label,
            "url": self.url,
            "clear": self.clear,
        }


@dataclass(frozen=True)
class NtfyMessage:
    """Complete ntfy message before server/topic addressing is applied."""

    title: str
    priority: str
    tags: str
    body: str
    actions: tuple[NtfyAction, ...] = ()

    def headers(self) -> dict[str, str]:
        headers = {
            "Title": self.title,
            "Priority": self.priority,
            "Tags": self.tags,
        }
        if self.actions:
            headers["Actions"] = json.dumps(
                [action.as_ntfy_json() for action in self.actions],
                separators=(",", ":"),
            )
        return headers


@dataclass(frozen=True)
class NtfyRequest:
    """Transport-level request captured by tests and sent by the client."""

    url: str
    body: str
    headers: Mapping[str, str]
    timeout_seconds: float
    auth: tuple[str, str] | None = None


@dataclass(frozen=True)
class NtfyResponse:
    """Minimal response used by the ntfy client."""

    ok: bool
    status_code: int = 200
    body: str = ""
