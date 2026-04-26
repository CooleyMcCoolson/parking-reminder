from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pytest

from app_api import AppSettings, create_app
from app_core import NEW_YORK_TZ
from app_core.notifications.models import NtfyMessage


def ny_datetime(year: int, month: int, day: int, hour: int, minute: int) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=NEW_YORK_TZ)


@dataclass
class FakeNotifier:
    messages: list[NtfyMessage] = field(default_factory=list)

    def send_status(self, message: NtfyMessage) -> None:
        self.messages.append(message)


@dataclass
class FakeClock:
    value: float = 1000.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


@dataclass(frozen=True)
class AsgiResponse:
    status_code: int
    headers: dict[str, str]
    content: bytes

    @property
    def text(self) -> str:
        return self.content.decode("utf-8")

    def json(self) -> object:
        return json.loads(self.text)


class AsgiTestClient:
    def __init__(self, app) -> None:
        self.app = app

    def get(self, path: str) -> AsgiResponse:
        return asyncio.run(self._request("GET", path))

    def post(self, path: str, *, follow_redirects: bool | None = None) -> AsgiResponse:
        return asyncio.run(self._request("POST", path))

    async def _request(self, method: str, path: str) -> AsgiResponse:
        body_messages = []
        status_code = 500
        headers: dict[str, str] = {}
        received = False

        async def receive():
            nonlocal received
            if not received:
                received = True
                return {"type": "http.request", "body": b"", "more_body": False}
            await asyncio.sleep(0)
            return {"type": "http.disconnect"}

        async def send(message):
            nonlocal status_code, headers
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = {
                    key.decode("latin-1").lower(): value.decode("latin-1")
                    for key, value in message.get("headers", [])
                }
            elif message["type"] == "http.response.body":
                body_messages.append(message.get("body", b""))

        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode("ascii"),
            "query_string": b"",
            "headers": [(b"host", b"testserver")],
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
        }

        await self.app(scope, receive, send)
        return AsgiResponse(
            status_code=status_code,
            headers=headers,
            content=b"".join(body_messages),
        )


def write_static_tree(root: Path) -> None:
    (root / "icons").mkdir(parents=True)
    (root / "manifest.json").write_text('{"name":"Parking"}')
    (root / "service-worker.js").write_text("self.addEventListener('fetch', () => {})")
    (root / "icons" / "icon.svg").write_text("<svg></svg>")
    (root / "icons" / "icon-192.png").write_bytes(b"192")
    (root / "icons" / "icon-512.png").write_bytes(b"512")


def make_settings(tmp_path: Path) -> AppSettings:
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    write_static_tree(static_dir)
    status_html = tmp_path / "status.html"
    status_html.write_text("<!doctype html><title>Parking Reminder</title>")

    return AppSettings(
        state_dir=tmp_path / "state",
        log_dir=tmp_path / "logs",
        static_dir=static_dir,
        status_html_path=status_html,
        webhook_base_url="https://parking.example",
        ntfy_server="https://ntfy.example",
        ntfy_topic="parking",
    )


def make_client(
    tmp_path: Path,
    *,
    notifier: FakeNotifier | None = None,
    clock: FakeClock | None = None,
    now: datetime | None = None,
    settings: AppSettings | None = None,
) -> AsgiTestClient:
    app = create_app(
        settings=settings or make_settings(tmp_path),
        notifier=notifier or FakeNotifier(),
        rate_clock=clock or FakeClock(),
        now_provider=lambda: now or ny_datetime(2026, 4, 20, 17, 59),
    )
    return AsgiTestClient(app)


def test_from_env_reports_absent_ntfy_server(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NTFY_SERVER", raising=False)
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    monkeypatch.delenv("WEBHOOK_BASE_URL", raising=False)

    settings = AppSettings.from_env()

    assert settings.ntfy_server is None
    assert settings.missing_required_config() == (
        "NTFY_SERVER",
        "NTFY_TOPIC",
        "WEBHOOK_BASE_URL",
    )


def test_from_env_does_not_report_present_ntfy_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NTFY_SERVER", "https://ntfy.example")
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    monkeypatch.delenv("WEBHOOK_BASE_URL", raising=False)

    settings = AppSettings.from_env()

    assert settings.ntfy_server == "https://ntfy.example"
    assert "NTFY_SERVER" not in settings.missing_required_config()


def test_get_home_serves_status_html(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.get("/")

    assert response.status_code == 200
    assert "Parking Reminder" in response.text
    assert response.headers["content-type"].startswith("text/html")


def test_health_healthy(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.text.startswith("HEALTHY")
    assert "OK state directory writable" in response.text
    assert "PENDING scheduler/cron ownership" in response.text


def test_health_unhealthy_for_missing_required_config(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    settings = AppSettings(
        state_dir=settings.state_dir,
        log_dir=settings.log_dir,
        static_dir=settings.static_dir,
        status_html_path=settings.status_html_path,
        webhook_base_url=None,
        ntfy_server="https://ntfy.example",
        ntfy_topic=None,
    )
    client = make_client(tmp_path, settings=settings)

    response = client.get("/health")

    assert response.status_code == 503
    assert response.text.startswith("UNHEALTHY")
    assert "WEBHOOK_BASE_URL" in response.text
    assert "NTFY_TOPIC" in response.text


def test_health_unhealthy_when_ntfy_server_absent(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    settings = AppSettings(
        state_dir=settings.state_dir,
        log_dir=settings.log_dir,
        static_dir=settings.static_dir,
        status_html_path=settings.status_html_path,
        webhook_base_url=settings.webhook_base_url,
        ntfy_server=None,
        ntfy_topic=settings.ntfy_topic,
    )
    client = make_client(tmp_path, settings=settings)

    response = client.get("/health")

    assert response.status_code == 503
    assert response.text.startswith("UNHEALTHY")
    assert "FAIL missing config: NTFY_SERVER" in response.text


def test_health_unhealthy_for_unwritable_path_shape(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    bad_log_dir = tmp_path / "not-a-directory"
    bad_log_dir.write_text("file blocks mkdir")
    settings = AppSettings(
        state_dir=settings.state_dir,
        log_dir=bad_log_dir,
        static_dir=settings.static_dir,
        status_html_path=settings.status_html_path,
        webhook_base_url=settings.webhook_base_url,
        ntfy_server=settings.ntfy_server,
        ntfy_topic=settings.ntfy_topic,
    )
    client = make_client(tmp_path, settings=settings)

    response = client.get("/health")

    assert response.status_code == 503
    assert "FAIL log directory not writable" in response.text


@pytest.mark.parametrize("method", ["get", "post"])
def test_ack_get_and_post_create_files(tmp_path: Path, method: str) -> None:
    now = ny_datetime(2026, 4, 20, 18, 0)
    client = make_client(tmp_path, now=now)

    response = getattr(client, method)("/ack/gotit")

    assert response.status_code == 200
    assert response.text == "Acknowledged: gotit"
    files = list((tmp_path / "state").glob("ack-gotit.*"))
    assert len(files) == 1
    assert files[0].read_text() == ""


def test_invalid_ack_returns_404(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.get("/ack/unknown")

    assert response.status_code == 404
    assert not (tmp_path / "state").exists()


@pytest.mark.parametrize("path", ["/vacation/status", "/api/vacation/status"])
def test_vacation_status(tmp_path: Path, path: str) -> None:
    client = make_client(tmp_path)

    assert client.get(path).json() == {"enabled": False}


@pytest.mark.parametrize("path", ["/vacation/toggle", "/api/vacation/toggle"])
def test_vacation_toggle_enables_and_disables(tmp_path: Path, path: str) -> None:
    client = make_client(tmp_path)

    assert client.post(path).json() == {"enabled": True}
    vacation_file = tmp_path / "state" / "vacation-mode"
    assert vacation_file.exists()
    assert vacation_file.read_text() == ""
    assert client.get("/vacation/status").json() == {"enabled": True}

    assert client.post(path).json() == {"enabled": False}
    assert not vacation_file.exists()


def test_post_status_redirects_and_invokes_fake_notifier(tmp_path: Path) -> None:
    notifier = FakeNotifier()
    client = make_client(
        tmp_path,
        notifier=notifier,
        now=ny_datetime(2026, 4, 20, 18, 30),
    )

    response = client.post("/status", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/"
    assert len(notifier.messages) == 1
    assert notifier.messages[0].title == "Parking Status"
    assert notifier.messages[0].body == "Park on HOUSE side (window closes at 7pm)"


def test_status_rate_limit(tmp_path: Path) -> None:
    clock = FakeClock()
    client = make_client(tmp_path, clock=clock)

    first = client.post("/status", follow_redirects=False)
    second = client.post("/status", follow_redirects=False)
    clock.advance(5.1)
    third = client.post("/status", follow_redirects=False)

    assert first.status_code == 303
    assert second.status_code == 429
    assert third.status_code == 303


def test_general_rate_limit(tmp_path: Path) -> None:
    clock = FakeClock()
    client = make_client(tmp_path, clock=clock)

    responses = [client.get("/manifest.json") for _ in range(11)]

    assert [response.status_code for response in responses[:10]] == [200] * 10
    assert responses[10].status_code == 429


def test_general_rate_limit_window_expires(tmp_path: Path) -> None:
    clock = FakeClock()
    client = make_client(tmp_path, clock=clock)

    for _ in range(10):
        assert client.get("/manifest.json").status_code == 200
    assert client.get("/manifest.json").status_code == 429

    clock.advance(60.1)
    assert client.get("/manifest.json").status_code == 200


@pytest.mark.parametrize(
    ("path", "content_type", "cache_control"),
    [
        ("/manifest.json", "application/manifest+json", "public, max-age=86400"),
        ("/service-worker.js", "application/javascript", "no-cache"),
        ("/icons/icon.svg", "image/svg+xml", "public, max-age=86400"),
        ("/icons/icon-192.png", "image/png", "public, max-age=86400"),
        ("/icons/icon-512.png", "image/png", "public, max-age=86400"),
    ],
)
def test_static_routes_and_cache_headers(
    tmp_path: Path,
    path: str,
    content_type: str,
    cache_control: str,
) -> None:
    client = make_client(tmp_path)

    response = client.get(path)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(content_type)
    assert response.headers["cache-control"] == cache_control


def test_missing_static_file_returns_404(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    (settings.static_dir / "icons" / "icon-192.png").unlink()
    client = make_client(tmp_path, settings=settings)

    response = client.get("/icons/icon-192.png")

    assert response.status_code == 404
