"""Pure ntfy message construction for parking reminders."""

from __future__ import annotations

from urllib.parse import urljoin

from app_core.models import ParkingDecision, ReminderStage, Side, StatusVariant

from .models import NtfyAction, NtfyMessage

NORMAL_REMINDER_TITLE = "Parking Reminder"
STATUS_TITLE = "Parking Status"


def build_normal_reminder_message(
    stage: ReminderStage,
    parking: ParkingDecision,
    webhook_base_url: str,
) -> NtfyMessage:
    """Build one of the three normal reminder messages."""

    current, destination = _require_sides(parking)

    if stage == ReminderStage.WARNING_545:
        return NtfyMessage(
            title=NORMAL_REMINDER_TITLE,
            priority="high",
            tags="warning,car",
            body=f"15 minutes: Move car from {current.value} to {destination.value} side",
            actions=(
                _action("Got it!", webhook_base_url, "/ack/gotit"),
                _action("Not home", webhook_base_url, "/ack/nothome"),
            ),
        )

    if stage == ReminderStage.URGENT_600:
        return NtfyMessage(
            title=NORMAL_REMINDER_TITLE,
            priority="urgent",
            tags="rotating_light,car",
            body=f"MOVE NOW: {current.value} -> {destination.value} side (window closes at 7pm)",
            actions=(
                _action("I moved it", webhook_base_url, "/ack/moved"),
                _action("Not home", webhook_base_url, "/ack/nothome"),
            ),
        )

    if stage == ReminderStage.LASTCALL_645:
        return NtfyMessage(
            title=NORMAL_REMINDER_TITLE,
            priority="urgent",
            tags="rotating_light,sos",
            body=f"15 MIN LEFT: Move from {current.value} to {destination.value} side!",
            actions=(
                _action("Done!", webhook_base_url, "/ack/done"),
                _action("Not home", webhook_base_url, "/ack/nothome"),
            ),
        )

    raise ValueError(f"Unsupported normal reminder stage: {stage}")


def build_status_message(
    variant: StatusVariant,
    parking: ParkingDecision,
) -> NtfyMessage:
    """Build the on-demand status notification message."""

    if variant == StatusVariant.SUNDAY_NO_MOVE:
        body = "It's Sunday! No parking moves needed today."
    else:
        _, destination = _require_sides(parking)
        current = parking.current_side
        if current is None:
            raise ValueError("Status message requires current side outside Sunday")

        if variant == StatusVariant.UPCOMING_MOVE:
            body = (
                f"Currently parked on: {current.value} side\n"
                f"Move to: {destination.value} side (6-7pm window)"
            )
        elif variant == StatusVariant.ACTIVE_WINDOW:
            body = f"Park on {destination.value} side (window closes at 7pm)"
        elif variant == StatusVariant.CONFIRMATION:
            body = f"You should now be parked on {destination.value} side"
        else:
            raise ValueError(f"Unsupported status variant: {variant}")

    return NtfyMessage(
        title=STATUS_TITLE,
        priority="high",
        tags="information_source,car",
        body=body,
    )


def build_escalation_message(
    stage: ReminderStage,
    parking: ParkingDecision,
    webhook_base_url: str,
) -> NtfyMessage:
    """Build a single escalation notification message."""

    current, destination = _require_sides(parking)

    if stage == ReminderStage.ESCALATION_URGENT_655:
        return NtfyMessage(
            title="PARKING EMERGENCY - 5 MIN LEFT",
            priority="5",
            tags="rotating_light,alarm,warning",
            body=(
                "NO ACKNOWLEDGMENT RECEIVED\n"
                "Window closes at 7:00pm\n\n"
                "Move car NOW:\n"
                f"{current.value} side -> {destination.value} side\n\n"
                "You have 5 minutes remaining!"
            ),
            actions=_escalation_actions(webhook_base_url, moving_label="I'M MOVING IT NOW"),
        )

    if stage == ReminderStage.ESCALATION_NUCLEAR_700:
        return NtfyMessage(
            title="FINAL WARNING - WINDOW CLOSING",
            priority="5",
            tags="rotating_light,fire,sos,warning",
            body=(
                "STILL NO ACKNOWLEDGMENT\n\n"
                "Move car IMMEDIATELY:\n"
                f"{current.value} side -> {destination.value} side\n\n"
                "Parking window closes NOW!\n"
                "Ticket risk is HIGH!"
            ),
            actions=_escalation_actions(webhook_base_url, moving_label="I MOVED IT"),
        )

    raise ValueError(f"Unsupported escalation stage: {stage}")


def _action(label: str, webhook_base_url: str, path: str) -> NtfyAction:
    return NtfyAction(label=label, url=_join_webhook_url(webhook_base_url, path))


def _escalation_actions(
    webhook_base_url: str,
    moving_label: str,
) -> tuple[NtfyAction, ...]:
    return (
        _action(moving_label, webhook_base_url, "/ack/done"),
        _action("Not home", webhook_base_url, "/ack/nothome"),
    )


def _join_webhook_url(webhook_base_url: str, path: str) -> str:
    return urljoin(f"{webhook_base_url.rstrip('/')}/", path.lstrip("/"))


def _require_sides(parking: ParkingDecision) -> tuple[Side, Side]:
    if parking.current_side is None or parking.destination_side is None:
        raise ValueError("Notification message requires current and destination sides")
    return parking.current_side, parking.destination_side
