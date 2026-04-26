"""Future FastAPI route-compatible app.

This app is intentionally beside the current runtime. It does not replace
``ack-server.py`` or participate in Docker/cron yet.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Protocol

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response

from app_core.models import AckType
from app_core.notifications.messages import build_status_message
from app_core.notifications.ntfy import NtfyClient, NtfyConfig
from app_core.notifications.models import NtfyMessage
from app_core.rules import parking_decision_for_datetime, status_variant_for_datetime
from app_core.state import AcknowledgmentState
from app_core.timezone import NEW_YORK_TZ
from app_core.vacation import VacationState

from .health import check_health
from .rate_limit import RateLimiter
from .settings import AppSettings


class StatusNotifier(Protocol):
    def send_status(self, message: NtfyMessage) -> None:
        """Deliver a status notification."""


class NtfyStatusNotifier:
    """Status notification adapter using the app_core ntfy client."""

    def __init__(self, client: NtfyClient) -> None:
        self.client = client

    def send_status(self, message: NtfyMessage) -> None:
        self.client.send_once(message)


class UnconfiguredStatusNotifier:
    """Notifier used when required ntfy config is absent at import time."""

    def send_status(self, message: NtfyMessage) -> None:
        raise RuntimeError("Status notifier is not configured")


def create_app(
    *,
    settings: AppSettings | None = None,
    notifier: StatusNotifier | None = None,
    now_provider: Callable[[], datetime] | None = None,
    rate_clock: Callable[[], float] | None = None,
) -> FastAPI:
    """Create the future FastAPI app with injectable edges for tests."""

    app_settings = settings or AppSettings.from_env()
    current_time = now_provider or (lambda: datetime.now(NEW_YORK_TZ))
    clock = rate_clock or time.time
    ack_state = AcknowledgmentState(app_settings.state_dir)
    vacation_state = VacationState(app_settings.state_dir)
    status_notifier = notifier or _build_notifier(app_settings)
    general_limiter = RateLimiter(max_requests=10, window_seconds=60, clock=clock)
    status_limiter = RateLimiter(max_requests=1, window_seconds=5, clock=clock)

    app = FastAPI(title="Parking Reminder Future API")

    @app.middleware("http")
    async def general_rate_limit(request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        if not general_limiter.is_allowed(client_ip):
            return PlainTextResponse("Too Many Requests", status_code=429)
        return await call_next(request)

    @app.get("/", response_class=HTMLResponse)
    async def home() -> Response:
        if app_settings.status_html_path.exists():
            return HTMLResponse(app_settings.status_html_path.read_text())
        return HTMLResponse("<!doctype html><title>Parking Reminder</title>")

    @app.get("/health", response_class=PlainTextResponse)
    async def health() -> Response:
        result = check_health(app_settings)
        return PlainTextResponse(result.message, status_code=200 if result.healthy else 503)

    @app.post("/status")
    async def post_status(request: Request) -> Response:
        client_ip = request.client.host if request.client else "unknown"
        if not status_limiter.is_allowed(client_ip):
            return PlainTextResponse("Please wait 5 seconds between status checks", status_code=429)

        moment = current_time()
        parking = parking_decision_for_datetime(moment)
        variant = status_variant_for_datetime(moment)
        message = build_status_message(variant, parking)
        status_notifier.send_status(message)
        return RedirectResponse("/", status_code=303)

    @app.get("/vacation/status")
    @app.get("/api/vacation/status")
    async def vacation_status() -> JSONResponse:
        return JSONResponse({"enabled": vacation_state.is_enabled(current_time())})

    @app.post("/vacation/toggle")
    @app.post("/api/vacation/toggle")
    async def vacation_toggle() -> JSONResponse:
        return JSONResponse({"enabled": vacation_state.toggle_web()})

    @app.get("/ack/{ack_type}", response_class=PlainTextResponse)
    @app.post("/ack/{ack_type}", response_class=PlainTextResponse)
    async def acknowledge(ack_type: str) -> PlainTextResponse:
        try:
            normalized = AckType(ack_type)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Invalid acknowledgment type") from exc

        ack_state.create_ack(normalized, now=current_time())
        return PlainTextResponse(f"Acknowledged: {normalized.value}")

    @app.get("/manifest.json")
    async def manifest() -> Response:
        return _static_response(
            app_settings.static_dir / "manifest.json",
            media_type="application/manifest+json",
            cache_control="public, max-age=86400",
        )

    @app.get("/service-worker.js")
    async def service_worker() -> Response:
        return _static_response(
            app_settings.static_dir / "service-worker.js",
            media_type="application/javascript",
            cache_control="no-cache",
        )

    @app.get("/icons/icon.svg")
    async def icon_svg() -> Response:
        return _static_response(
            app_settings.static_dir / "icons" / "icon.svg",
            media_type="image/svg+xml",
            cache_control="public, max-age=86400",
        )

    @app.get("/icons/icon-192.png")
    async def icon_192() -> Response:
        return _static_response(
            app_settings.static_dir / "icons" / "icon-192.png",
            media_type="image/png",
            cache_control="public, max-age=86400",
        )

    @app.get("/icons/icon-512.png")
    async def icon_512() -> Response:
        return _static_response(
            app_settings.static_dir / "icons" / "icon-512.png",
            media_type="image/png",
            cache_control="public, max-age=86400",
        )

    return app


def _build_notifier(settings: AppSettings) -> StatusNotifier:
    if settings.missing_required_config():
        return UnconfiguredStatusNotifier()

    config = NtfyConfig(
        server=settings.ntfy_server or "",
        topic=settings.ntfy_topic or "",
        auth_user=settings.ntfy_auth_user,
        auth_pass=settings.ntfy_auth_pass,
        failsafe_topic=settings.ntfy_failsafe_topic,
        uptime_kuma_push_url=settings.uptime_kuma_push_url,
    )
    return NtfyStatusNotifier(NtfyClient(config))


def _static_response(path: Path, *, media_type: str, cache_control: str) -> Response:
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    response = Response(content=path.read_bytes(), media_type=media_type)
    response.headers["Cache-Control"] = cache_control
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


app = create_app()
