"""Pure rule functions for the parking reminder behavior contract."""

from __future__ import annotations

from datetime import datetime
from typing import Iterable

from .models import (
    AckType,
    ParkingDecision,
    ReminderStage,
    Side,
    StatusVariant,
    SuppressionDecision,
)
from .timezone import as_new_york


def parking_decision_for_datetime(moment: datetime) -> ParkingDecision:
    """Return the parking side decision for the local New York date.

    Contract mapping:
    - Monday, Wednesday, Friday: AWAY -> HOUSE.
    - Tuesday, Thursday, Saturday: HOUSE -> AWAY.
    - Sunday: no move required.
    """

    local = as_new_york(moment)
    weekday = local.weekday()  # Monday=0, Sunday=6

    if weekday == 6:
        return ParkingDecision(
            current_side=None,
            destination_side=None,
            no_move_required=True,
        )

    if weekday in {0, 2, 4}:
        return ParkingDecision(
            current_side=Side.AWAY,
            destination_side=Side.HOUSE,
        )

    return ParkingDecision(
        current_side=Side.HOUSE,
        destination_side=Side.AWAY,
    )


def reminder_stage_for_datetime(moment: datetime) -> ReminderStage | None:
    """Return the normal reminder stage for the local New York time, if any.

    Sunday returns no stage because the current product is no-move on Sunday.
    """

    local = as_new_york(moment)
    if local.weekday() == 6:
        return None

    hour = local.hour
    minute = local.minute

    if hour == 17 and 45 <= minute <= 47:
        return ReminderStage.WARNING_545
    if hour == 18 and 0 <= minute <= 2:
        return ReminderStage.URGENT_600
    if hour == 18 and 45 <= minute <= 47:
        return ReminderStage.LASTCALL_645

    return None


def escalation_stage_for_datetime(moment: datetime) -> ReminderStage | None:
    """Return an explicit escalation stage for the local New York time.

    This does not schedule anything; it only names the two escalation moments
    preserved from the current cron behavior.
    """

    local = as_new_york(moment)
    if local.weekday() == 6:
        return None

    if local.hour == 18 and local.minute == 55:
        return ReminderStage.ESCALATION_URGENT_655
    if local.hour == 19 and local.minute == 0:
        return ReminderStage.ESCALATION_NUCLEAR_700

    return None


def suppression_for_stage(
    stage: ReminderStage,
    acknowledgments: Iterable[AckType | str],
) -> SuppressionDecision:
    """Apply the shipped acknowledgment suppression matrix to a stage."""

    normalized_acks = {_to_ack_type(ack) for ack in acknowledgments}
    suppressors = _SUPPRESSION_MATRIX[stage]

    for ack_type in suppressors:
        if ack_type in normalized_acks:
            return SuppressionDecision(suppressed=True, ack_type=ack_type)

    return SuppressionDecision(suppressed=False)


def status_variant_for_datetime(moment: datetime) -> StatusVariant:
    """Return the status button message variant for local New York time."""

    local = as_new_york(moment)

    if local.weekday() == 6:
        return StatusVariant.SUNDAY_NO_MOVE
    if local.hour < 18:
        return StatusVariant.UPCOMING_MOVE
    if local.hour == 18:
        return StatusVariant.ACTIVE_WINDOW
    return StatusVariant.CONFIRMATION


def _to_ack_type(value: AckType | str) -> AckType:
    if isinstance(value, AckType):
        return value
    return AckType(value)


_SUPPRESSION_MATRIX: dict[ReminderStage, tuple[AckType, ...]] = {
    ReminderStage.WARNING_545: (
        AckType.NOTHOME,
        AckType.GOTIT,
    ),
    ReminderStage.URGENT_600: (
        AckType.NOTHOME,
        AckType.MOVED,
    ),
    ReminderStage.LASTCALL_645: (
        AckType.NOTHOME,
        AckType.MOVED,
        AckType.DONE,
    ),
    ReminderStage.ESCALATION_URGENT_655: (
        AckType.NOTHOME,
        AckType.GOTIT,
        AckType.MOVED,
        AckType.DONE,
    ),
    ReminderStage.ESCALATION_NUCLEAR_700: (
        AckType.NOTHOME,
        AckType.GOTIT,
        AckType.MOVED,
        AckType.DONE,
    ),
}
