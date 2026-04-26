"""Settings for the future FastAPI app."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from app_core.state import DEFAULT_STATE_DIR

REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class AppSettings:
    """Runtime paths and notification config for the FastAPI app."""

    state_dir: Path = DEFAULT_STATE_DIR
    log_dir: Path = Path("/var/log/parking-reminder")
    static_dir: Path = REPO_ROOT
    status_html_path: Path = REPO_ROOT / "status.html"
    timezone: str = "America/New_York"
    webhook_base_url: str | None = None
    ntfy_server: str | None = None
    ntfy_topic: str | None = None
    ntfy_auth_user: str | None = None
    ntfy_auth_pass: str | None = None
    ntfy_failsafe_topic: str | None = None
    uptime_kuma_push_url: str | None = None

    @classmethod
    def from_env(cls) -> "AppSettings":
        return cls(
            state_dir=Path(os.environ.get("PARKING_STATE_DIR", str(DEFAULT_STATE_DIR))),
            log_dir=Path(os.environ.get("PARKING_LOG_DIR", "/var/log/parking-reminder")),
            timezone=os.environ.get("TZ", "America/New_York"),
            webhook_base_url=os.environ.get("WEBHOOK_BASE_URL"),
            ntfy_server=os.environ.get("NTFY_SERVER"),
            ntfy_topic=os.environ.get("NTFY_TOPIC"),
            ntfy_auth_user=os.environ.get("NTFY_AUTH_USER") or None,
            ntfy_auth_pass=os.environ.get("NTFY_AUTH_PASS") or None,
            ntfy_failsafe_topic=os.environ.get("NTFY_FAILSAFE_TOPIC") or None,
            uptime_kuma_push_url=os.environ.get("UPTIME_KUMA_PUSH_URL") or None,
        )

    def missing_required_config(self) -> tuple[str, ...]:
        missing: list[str] = []
        if not self.ntfy_server:
            missing.append("NTFY_SERVER")
        if not self.ntfy_topic:
            missing.append("NTFY_TOPIC")
        if not self.webhook_base_url:
            missing.append("WEBHOOK_BASE_URL")
        return tuple(missing)
