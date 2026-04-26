from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app_core import (
    AckType,
    NEW_YORK_TZ,
    ReminderStage,
    Side,
    StatusVariant,
    as_new_york,
    escalation_stage_for_datetime,
    parking_decision_for_datetime,
    reminder_stage_for_datetime,
    status_variant_for_datetime,
    suppression_for_stage,
)


def ny_datetime(year: int, month: int, day: int, hour: int, minute: int) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=NEW_YORK_TZ)


@pytest.mark.parametrize(
    ("moment", "current_side", "destination_side", "no_move_required"),
    [
        (ny_datetime(2026, 4, 20, 12, 0), Side.AWAY, Side.HOUSE, False),
        (ny_datetime(2026, 4, 21, 12, 0), Side.HOUSE, Side.AWAY, False),
        (ny_datetime(2026, 4, 22, 12, 0), Side.AWAY, Side.HOUSE, False),
        (ny_datetime(2026, 4, 23, 12, 0), Side.HOUSE, Side.AWAY, False),
        (ny_datetime(2026, 4, 24, 12, 0), Side.AWAY, Side.HOUSE, False),
        (ny_datetime(2026, 4, 25, 12, 0), Side.HOUSE, Side.AWAY, False),
        (ny_datetime(2026, 4, 26, 12, 0), None, None, True),
    ],
)
def test_parking_side_decisions_for_all_weekdays(
    moment: datetime,
    current_side: Side | None,
    destination_side: Side | None,
    no_move_required: bool,
) -> None:
    decision = parking_decision_for_datetime(moment)

    assert decision.current_side == current_side
    assert decision.destination_side == destination_side
    assert decision.no_move_required is no_move_required


def test_sunday_has_no_normal_or_escalation_stage() -> None:
    sunday_545 = ny_datetime(2026, 4, 26, 17, 45)
    sunday_655 = ny_datetime(2026, 4, 26, 18, 55)

    assert reminder_stage_for_datetime(sunday_545) is None
    assert escalation_stage_for_datetime(sunday_655) is None


@pytest.mark.parametrize(
    ("hour", "minute", "stage"),
    [
        (17, 44, None),
        (17, 45, ReminderStage.WARNING_545),
        (17, 47, ReminderStage.WARNING_545),
        (17, 48, None),
        (18, 0, ReminderStage.URGENT_600),
        (18, 2, ReminderStage.URGENT_600),
        (18, 3, None),
        (18, 44, None),
        (18, 45, ReminderStage.LASTCALL_645),
        (18, 47, ReminderStage.LASTCALL_645),
        (18, 48, None),
    ],
)
def test_reminder_window_boundaries(
    hour: int,
    minute: int,
    stage: ReminderStage | None,
) -> None:
    assert reminder_stage_for_datetime(ny_datetime(2026, 4, 20, hour, minute)) == stage


@pytest.mark.parametrize(
    ("hour", "minute"),
    [
        (0, 0),
        (12, 0),
        (17, 0),
        (18, 30),
        (19, 0),
        (23, 59),
    ],
)
def test_non_stage_times_return_no_normal_reminder(hour: int, minute: int) -> None:
    assert reminder_stage_for_datetime(ny_datetime(2026, 4, 20, hour, minute)) is None


@pytest.mark.parametrize(
    ("hour", "minute", "stage"),
    [
        (18, 54, None),
        (18, 55, ReminderStage.ESCALATION_URGENT_655),
        (18, 56, None),
        (18, 59, None),
        (19, 0, ReminderStage.ESCALATION_NUCLEAR_700),
        (19, 1, None),
    ],
)
def test_explicit_escalation_stages(
    hour: int,
    minute: int,
    stage: ReminderStage | None,
) -> None:
    assert escalation_stage_for_datetime(ny_datetime(2026, 4, 20, hour, minute)) == stage


@pytest.mark.parametrize(
    ("stage", "ack_type", "expected_suppressed"),
    [
        (ReminderStage.WARNING_545, AckType.GOTIT, True),
        (ReminderStage.WARNING_545, AckType.NOTHOME, True),
        (ReminderStage.WARNING_545, AckType.MOVED, False),
        (ReminderStage.WARNING_545, AckType.DONE, False),
        (ReminderStage.URGENT_600, AckType.GOTIT, False),
        (ReminderStage.URGENT_600, AckType.NOTHOME, True),
        (ReminderStage.URGENT_600, AckType.MOVED, True),
        (ReminderStage.URGENT_600, AckType.DONE, False),
        (ReminderStage.LASTCALL_645, AckType.GOTIT, False),
        (ReminderStage.LASTCALL_645, AckType.NOTHOME, True),
        (ReminderStage.LASTCALL_645, AckType.MOVED, True),
        (ReminderStage.LASTCALL_645, AckType.DONE, True),
        (ReminderStage.ESCALATION_URGENT_655, AckType.GOTIT, True),
        (ReminderStage.ESCALATION_URGENT_655, AckType.NOTHOME, True),
        (ReminderStage.ESCALATION_URGENT_655, AckType.MOVED, True),
        (ReminderStage.ESCALATION_URGENT_655, AckType.DONE, True),
        (ReminderStage.ESCALATION_NUCLEAR_700, AckType.GOTIT, True),
        (ReminderStage.ESCALATION_NUCLEAR_700, AckType.NOTHOME, True),
        (ReminderStage.ESCALATION_NUCLEAR_700, AckType.MOVED, True),
        (ReminderStage.ESCALATION_NUCLEAR_700, AckType.DONE, True),
    ],
)
def test_full_ack_suppression_matrix(
    stage: ReminderStage,
    ack_type: AckType,
    expected_suppressed: bool,
) -> None:
    decision = suppression_for_stage(stage, [ack_type])

    assert decision.suppressed is expected_suppressed
    assert decision.ack_type == (ack_type if expected_suppressed else None)


def test_no_acks_do_not_suppress_any_stage() -> None:
    for stage in ReminderStage:
        assert suppression_for_stage(stage, []).suppressed is False


def test_suppression_accepts_ack_strings() -> None:
    decision = suppression_for_stage(ReminderStage.WARNING_545, ["gotit"])

    assert decision.suppressed is True
    assert decision.ack_type == AckType.GOTIT


@pytest.mark.parametrize(
    ("moment", "variant"),
    [
        (ny_datetime(2026, 4, 26, 12, 0), StatusVariant.SUNDAY_NO_MOVE),
        (ny_datetime(2026, 4, 20, 17, 59), StatusVariant.UPCOMING_MOVE),
        (ny_datetime(2026, 4, 20, 18, 0), StatusVariant.ACTIVE_WINDOW),
        (ny_datetime(2026, 4, 20, 18, 59), StatusVariant.ACTIVE_WINDOW),
        (ny_datetime(2026, 4, 20, 19, 0), StatusVariant.CONFIRMATION),
        (ny_datetime(2026, 4, 20, 23, 59), StatusVariant.CONFIRMATION),
    ],
)
def test_status_variant_boundaries(moment: datetime, variant: StatusVariant) -> None:
    assert status_variant_for_datetime(moment) == variant


def test_aware_utc_datetime_is_evaluated_in_new_york_time() -> None:
    moment = datetime(2026, 4, 20, 22, 0, tzinfo=timezone.utc)

    assert as_new_york(moment) == ny_datetime(2026, 4, 20, 18, 0)
    assert reminder_stage_for_datetime(moment) == ReminderStage.URGENT_600
    assert status_variant_for_datetime(moment) == StatusVariant.ACTIVE_WINDOW


def test_naive_datetime_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        parking_decision_for_datetime(datetime(2026, 4, 20, 18, 0))
