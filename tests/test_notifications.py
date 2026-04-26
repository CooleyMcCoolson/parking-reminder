from __future__ import annotations

import json
from dataclasses import dataclass, field

import pytest

from app_core.models import ParkingDecision, ReminderStage, Side, StatusVariant
from app_core.notifications import (
    NtfyClient,
    NtfyConfig,
    NtfyRequest,
    NtfyResponse,
    TransportError,
    build_escalation_message,
    build_normal_reminder_message,
    build_status_message,
)


PARKING = ParkingDecision(current_side=Side.AWAY, destination_side=Side.HOUSE)
SUNDAY = ParkingDecision(current_side=None, destination_side=None, no_move_required=True)


@dataclass
class FakeTransport:
    post_results: list[NtfyResponse | Exception] = field(default_factory=list)
    get_results: list[NtfyResponse | Exception] = field(default_factory=list)
    post_requests: list[NtfyRequest] = field(default_factory=list)
    get_requests: list[tuple[str, float]] = field(default_factory=list)

    def post(self, request: NtfyRequest) -> NtfyResponse:
        self.post_requests.append(request)
        result = self.post_results.pop(0) if self.post_results else NtfyResponse(ok=True)
        if isinstance(result, Exception):
            raise result
        return result

    def get(self, url: str, timeout_seconds: float) -> NtfyResponse:
        self.get_requests.append((url, timeout_seconds))
        result = self.get_results.pop(0) if self.get_results else NtfyResponse(ok=True)
        if isinstance(result, Exception):
            raise result
        return result


def action_payload(message) -> list[dict[str, object]]:
    return json.loads(message.headers()["Actions"])


@pytest.mark.parametrize(
    ("stage", "priority", "tags", "labels_and_paths"),
    [
        (
            ReminderStage.WARNING_545,
            "high",
            "warning,car",
            [("Got it!", "/ack/gotit"), ("Not home", "/ack/nothome")],
        ),
        (
            ReminderStage.URGENT_600,
            "urgent",
            "rotating_light,car",
            [("I moved it", "/ack/moved"), ("Not home", "/ack/nothome")],
        ),
        (
            ReminderStage.LASTCALL_645,
            "urgent",
            "rotating_light,sos",
            [("Done!", "/ack/done"), ("Not home", "/ack/nothome")],
        ),
    ],
)
def test_normal_reminder_message_construction(
    stage: ReminderStage,
    priority: str,
    tags: str,
    labels_and_paths: list[tuple[str, str]],
) -> None:
    message = build_normal_reminder_message(stage, PARKING, "https://parking.example")

    assert message.title == "Parking Reminder"
    assert message.priority == priority
    assert message.tags == tags
    assert "AWAY" in message.body
    assert "HOUSE" in message.body

    actions = action_payload(message)
    assert [(item["label"], item["url"]) for item in actions] == [
        (label, f"https://parking.example{path}") for label, path in labels_and_paths
    ]
    assert all(item["clear"] is True for item in actions)


@pytest.mark.parametrize(
    ("variant", "parking", "expected_body"),
    [
        (
            StatusVariant.SUNDAY_NO_MOVE,
            SUNDAY,
            "It's Sunday! No parking moves needed today.",
        ),
        (
            StatusVariant.UPCOMING_MOVE,
            PARKING,
            "Currently parked on: AWAY side\nMove to: HOUSE side (6-7pm window)",
        ),
        (
            StatusVariant.ACTIVE_WINDOW,
            PARKING,
            "Park on HOUSE side (window closes at 7pm)",
        ),
        (
            StatusVariant.CONFIRMATION,
            PARKING,
            "You should now be parked on HOUSE side",
        ),
    ],
)
def test_status_message_construction(
    variant: StatusVariant,
    parking: ParkingDecision,
    expected_body: str,
) -> None:
    message = build_status_message(variant, parking)

    assert message.title == "Parking Status"
    assert message.priority == "high"
    assert message.tags == "information_source,car"
    assert message.body == expected_body
    assert message.actions == ()


@pytest.mark.parametrize(
    ("stage", "title", "tags", "moving_label"),
    [
        (
            ReminderStage.ESCALATION_URGENT_655,
            "PARKING EMERGENCY - 5 MIN LEFT",
            "rotating_light,alarm,warning",
            "I'M MOVING IT NOW",
        ),
        (
            ReminderStage.ESCALATION_NUCLEAR_700,
            "FINAL WARNING - WINDOW CLOSING",
            "rotating_light,fire,sos,warning",
            "I MOVED IT",
        ),
    ],
)
def test_escalation_message_construction(
    stage: ReminderStage,
    title: str,
    tags: str,
    moving_label: str,
) -> None:
    message = build_escalation_message(stage, PARKING, "https://parking.example")

    assert message.title == title
    assert message.priority == "5"
    assert message.tags == tags
    assert "AWAY" in message.body
    assert "HOUSE" in message.body

    actions = action_payload(message)
    assert [(item["label"], item["url"]) for item in actions] == [
        (moving_label, "https://parking.example/ack/done"),
        ("Not home", "https://parking.example/ack/nothome"),
    ]


@pytest.mark.parametrize(
    "base_url",
    ["https://parking.example", "https://parking.example/"],
)
def test_action_urls_do_not_duplicate_slashes(base_url: str) -> None:
    message = build_normal_reminder_message(
        ReminderStage.WARNING_545,
        PARKING,
        base_url,
    )

    actions = action_payload(message)
    assert actions[0]["url"] == "https://parking.example/ack/gotit"
    assert actions[1]["url"] == "https://parking.example/ack/nothome"


def test_auth_absent() -> None:
    transport = FakeTransport()
    client = NtfyClient(
        NtfyConfig(server="https://ntfy.example", topic="parking"),
        transport=transport,
        sleep=lambda _: None,
    )

    client.send_once(build_status_message(StatusVariant.CONFIRMATION, PARKING))

    assert transport.post_requests[0].auth is None


@pytest.mark.parametrize(
    ("user", "password"),
    [("user", None), (None, "pass")],
)
def test_partial_auth_is_absent(user: str | None, password: str | None) -> None:
    transport = FakeTransport()
    client = NtfyClient(
        NtfyConfig(
            server="https://ntfy.example",
            topic="parking",
            auth_user=user,
            auth_pass=password,
        ),
        transport=transport,
        sleep=lambda _: None,
    )

    client.send_once(build_status_message(StatusVariant.CONFIRMATION, PARKING))

    assert transport.post_requests[0].auth is None


def test_full_auth_is_present() -> None:
    transport = FakeTransport()
    client = NtfyClient(
        NtfyConfig(
            server="https://ntfy.example",
            topic="parking",
            auth_user="user",
            auth_pass="pass",
        ),
        transport=transport,
        sleep=lambda _: None,
    )

    client.send_once(build_status_message(StatusVariant.CONFIRMATION, PARKING))

    assert transport.post_requests[0].auth == ("user", "pass")


def test_normal_reminder_retries_until_success() -> None:
    sleeps: list[float] = []
    transport = FakeTransport(
        post_results=[
            NtfyResponse(ok=False, status_code=500),
            NtfyResponse(ok=False, status_code=502),
            NtfyResponse(ok=True, status_code=200),
        ]
    )
    client = NtfyClient(
        NtfyConfig(server="https://ntfy.example/", topic="/parking"),
        transport=transport,
        sleep=sleeps.append,
    )
    message = build_normal_reminder_message(
        ReminderStage.WARNING_545,
        PARKING,
        "https://parking.example",
    )

    response = client.send_normal_reminder(message, reminder_type="545pm-warning")

    assert response.ok is True
    assert len(transport.post_requests) == 3
    assert [request.url for request in transport.post_requests] == [
        "https://ntfy.example/parking",
        "https://ntfy.example/parking",
        "https://ntfy.example/parking",
    ]
    assert [request.timeout_seconds for request in transport.post_requests] == [
        10.0,
        10.0,
        10.0,
    ]
    assert sleeps == [2.0, 2.0]


def test_transport_errors_are_retried() -> None:
    sleeps: list[float] = []
    transport = FakeTransport(
        post_results=[
            TransportError("temporary"),
            NtfyResponse(ok=True, status_code=200),
        ]
    )
    client = NtfyClient(
        NtfyConfig(server="https://ntfy.example", topic="parking"),
        transport=transport,
        sleep=sleeps.append,
    )

    response = client.send_normal_reminder(
        build_normal_reminder_message(
            ReminderStage.URGENT_600,
            PARKING,
            "https://parking.example",
        ),
        reminder_type="6pm-urgent",
    )

    assert response.ok is True
    assert len(transport.post_requests) == 2
    assert sleeps == [2.0]


def test_normal_failure_triggers_failsafe_when_configured() -> None:
    transport = FakeTransport(
        post_results=[
            NtfyResponse(ok=False, status_code=500),
            NtfyResponse(ok=False, status_code=500),
            NtfyResponse(ok=False, status_code=500),
            NtfyResponse(ok=True, status_code=200),
        ]
    )
    client = NtfyClient(
        NtfyConfig(
            server="https://ntfy.example",
            topic="parking",
            failsafe_topic="parking_backup",
        ),
        transport=transport,
        sleep=lambda _: None,
    )
    message = build_normal_reminder_message(
        ReminderStage.LASTCALL_645,
        PARKING,
        "https://parking.example",
    )

    response = client.send_normal_reminder(message, reminder_type="645pm-lastcall")

    assert response.ok is False
    assert len(transport.post_requests) == 4
    failsafe_request = transport.post_requests[-1]
    assert failsafe_request.url == "https://ntfy.sh/parking_backup"
    assert failsafe_request.auth is None
    assert failsafe_request.timeout_seconds == 5.0
    assert failsafe_request.headers["Title"] == "Parking System FAILURE"
    assert "Self-hosted ntfy failed!" in failsafe_request.body


def test_normal_success_triggers_uptime_kuma_when_configured() -> None:
    transport = FakeTransport(post_results=[NtfyResponse(ok=True, status_code=200)])
    client = NtfyClient(
        NtfyConfig(
            server="https://ntfy.example",
            topic="parking",
            uptime_kuma_push_url="https://uptime.example/api/push/token?existing=1",
        ),
        transport=transport,
        sleep=lambda _: None,
    )
    message = build_normal_reminder_message(
        ReminderStage.WARNING_545,
        PARKING,
        "https://parking.example",
    )

    response = client.send_normal_reminder(message, reminder_type="545pm-warning")

    assert response.ok is True
    assert len(transport.post_requests) == 1
    assert len(transport.get_requests) == 1
    url, timeout = transport.get_requests[0]
    assert timeout == 5.0
    assert url == (
        "https://uptime.example/api/push/token?"
        "existing=1&status=up&msg=545pm-warning"
    )


def test_normal_success_without_uptime_does_not_call_get() -> None:
    transport = FakeTransport(post_results=[NtfyResponse(ok=True, status_code=200)])
    client = NtfyClient(
        NtfyConfig(server="https://ntfy.example", topic="parking"),
        transport=transport,
        sleep=lambda _: None,
    )

    client.send_normal_reminder(
        build_normal_reminder_message(
            ReminderStage.WARNING_545,
            PARKING,
            "https://parking.example",
        ),
        reminder_type="545pm-warning",
    )

    assert transport.get_requests == []
