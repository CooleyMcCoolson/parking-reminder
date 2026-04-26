"""Health checks for the future FastAPI app."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .settings import AppSettings


@dataclass(frozen=True)
class HealthResult:
    healthy: bool
    message: str


def check_health(settings: AppSettings) -> HealthResult:
    checks: list[str] = []
    healthy = True

    if _directory_writable(settings.state_dir):
        checks.append("OK state directory writable")
    else:
        checks.append(f"FAIL state directory not writable: {settings.state_dir}")
        healthy = False

    if _directory_writable(settings.log_dir):
        checks.append("OK log directory writable")
    else:
        checks.append(f"FAIL log directory not writable: {settings.log_dir}")
        healthy = False

    if settings.timezone == "America/New_York":
        checks.append("OK timezone America/New_York")
    else:
        checks.append(f"WARN timezone {settings.timezone} (expected America/New_York)")

    missing = settings.missing_required_config()
    if missing:
        checks.append(f"FAIL missing config: {', '.join(missing)}")
        healthy = False
    else:
        checks.append("OK required config present")

    checks.append("PENDING scheduler/cron ownership not implemented in FastAPI app")

    status = "HEALTHY" if healthy else "UNHEALTHY"
    return HealthResult(healthy=healthy, message=f"{status}\n" + "\n".join(checks))


def _directory_writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".healthcheck"
        probe.touch()
        probe.unlink()
        return True
    except OSError:
        return False
