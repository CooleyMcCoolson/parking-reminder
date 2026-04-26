"""ntfy transport service for the future rewrite."""

from __future__ import annotations

import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Callable, Protocol

from .models import NtfyMessage, NtfyRequest, NtfyResponse

NORMAL_REMINDER_RETRIES = 3
NORMAL_REMINDER_TIMEOUT_SECONDS = 10.0
NORMAL_REMINDER_RETRY_SLEEP_SECONDS = 2.0
FAILSAFE_SERVER = "https://ntfy.sh"


class TransportError(Exception):
    """Raised when a transport cannot complete the request."""


class NtfyTransport(Protocol):
    def post(self, request: NtfyRequest) -> NtfyResponse:
        """Send one ntfy request."""

    def get(self, url: str, timeout_seconds: float) -> NtfyResponse:
        """Call an integration URL."""


@dataclass(frozen=True)
class NtfyConfig:
    """Configuration needed to address ntfy and optional integrations."""

    server: str
    topic: str
    auth_user: str | None = None
    auth_pass: str | None = None
    failsafe_topic: str | None = None
    uptime_kuma_push_url: str | None = None

    def __post_init__(self) -> None:
        if not self.server:
            raise ValueError("NTFY_SERVER is required")
        if not self.topic:
            raise ValueError("NTFY_TOPIC is required")

    @property
    def auth(self) -> tuple[str, str] | None:
        if self.auth_user and self.auth_pass:
            return (self.auth_user, self.auth_pass)
        return None

    @property
    def topic_url(self) -> str:
        return _join_url(self.server, self.topic)

    @property
    def failsafe_url(self) -> str | None:
        if not self.failsafe_topic:
            return None
        return _join_url(FAILSAFE_SERVER, self.failsafe_topic)


class UrllibNtfyTransport:
    """Standard-library HTTP transport for ntfy posts."""

    def post(self, request: NtfyRequest) -> NtfyResponse:
        headers = dict(request.headers)

        if request.auth is not None:
            password_manager = urllib.request.HTTPPasswordMgrWithDefaultRealm()
            password_manager.add_password(
                None,
                request.url,
                request.auth[0],
                request.auth[1],
            )
            auth_handler = urllib.request.HTTPBasicAuthHandler(password_manager)
            opener = urllib.request.build_opener(auth_handler)
        else:
            opener = urllib.request.build_opener()

        http_request = urllib.request.Request(
            request.url,
            data=request.body.encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            with opener.open(http_request, timeout=request.timeout_seconds) as response:
                body = response.read().decode("utf-8", errors="replace")
                status_code = response.getcode()
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            return NtfyResponse(ok=False, status_code=exc.code, body=body)
        except urllib.error.URLError as exc:
            raise TransportError(str(exc)) from exc

        return NtfyResponse(ok=200 <= status_code < 300, status_code=status_code, body=body)

    def get(self, url: str, timeout_seconds: float) -> NtfyResponse:
        try:
            with urllib.request.urlopen(url, timeout=timeout_seconds) as response:
                body = response.read().decode("utf-8", errors="replace")
                status_code = response.getcode()
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            return NtfyResponse(ok=False, status_code=exc.code, body=body)
        except urllib.error.URLError as exc:
            raise TransportError(str(exc)) from exc

        return NtfyResponse(ok=200 <= status_code < 300, status_code=status_code, body=body)


class NtfyClient:
    """Send ntfy messages with current reminder retry/failsafe semantics."""

    def __init__(
        self,
        config: NtfyConfig,
        transport: NtfyTransport | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self.config = config
        self.transport = transport or UrllibNtfyTransport()
        self.sleep = sleep or time.sleep

    def send_once(
        self,
        message: NtfyMessage,
        *,
        timeout_seconds: float = NORMAL_REMINDER_TIMEOUT_SECONDS,
    ) -> NtfyResponse:
        """Send a message once to the configured ntfy topic."""

        return self.transport.post(
            self._request(
                url=self.config.topic_url,
                message=message,
                timeout_seconds=timeout_seconds,
                auth=self.config.auth,
            )
        )

    def send_normal_reminder(
        self,
        message: NtfyMessage,
        *,
        reminder_type: str,
    ) -> NtfyResponse:
        """Send a normal reminder with retries, failsafe, and uptime push."""

        last_response: NtfyResponse | None = None
        last_error: TransportError | None = None

        for attempt in range(1, NORMAL_REMINDER_RETRIES + 1):
            try:
                response = self.send_once(
                    message,
                    timeout_seconds=NORMAL_REMINDER_TIMEOUT_SECONDS,
                )
            except TransportError as exc:
                last_error = exc
                response = None
            else:
                last_response = response
                if response.ok:
                    self._push_uptime(reminder_type)
                    return response

            if attempt < NORMAL_REMINDER_RETRIES:
                self.sleep(NORMAL_REMINDER_RETRY_SLEEP_SECONDS)

        self._send_failsafe(message)

        if last_response is not None:
            return last_response
        if last_error is not None:
            raise last_error

        return NtfyResponse(ok=False, status_code=0, body="notification failed")

    def _send_failsafe(self, original_message: NtfyMessage) -> None:
        failsafe_url = self.config.failsafe_url
        if failsafe_url is None:
            return

        failsafe_message = NtfyMessage(
            title="Parking System FAILURE",
            priority="urgent",
            tags="",
            body=f"Self-hosted ntfy failed! Original message: {original_message.body}",
        )
        try:
            self.transport.post(
                self._request(
                    url=failsafe_url,
                    message=failsafe_message,
                    timeout_seconds=5.0,
                    auth=None,
                )
            )
        except TransportError:
            return

    def _push_uptime(self, reminder_type: str) -> None:
        if not self.config.uptime_kuma_push_url:
            return

        url = _add_query_params(
            self.config.uptime_kuma_push_url,
            {"status": "up", "msg": reminder_type},
        )
        try:
            self.transport.get(url, timeout_seconds=5.0)
        except TransportError:
            return

    def _request(
        self,
        *,
        url: str,
        message: NtfyMessage,
        timeout_seconds: float,
        auth: tuple[str, str] | None,
    ) -> NtfyRequest:
        return NtfyRequest(
            url=url,
            body=message.body,
            headers=message.headers(),
            timeout_seconds=timeout_seconds,
            auth=auth,
        )


def _join_url(server: str, topic: str) -> str:
    return f"{server.rstrip('/')}/{topic.lstrip('/')}"


def _add_query_params(url: str, params: dict[str, str]) -> str:
    parsed = urllib.parse.urlsplit(url)
    query_items = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query_items.extend(params.items())
    new_query = urllib.parse.urlencode(query_items)
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, new_query, parsed.fragment)
    )
