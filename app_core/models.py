"""Typed value objects for the deterministic parking reminder core."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Side(str, Enum):
    """Parking sides named by the shipped Bash implementation."""

    AWAY = "AWAY"
    HOUSE = "HOUSE"


class AckType(str, Enum):
    """Acknowledgment types supported by the current notification buttons."""

    GOTIT = "gotit"
    NOTHOME = "nothome"
    MOVED = "moved"
    DONE = "done"


class ReminderStage(str, Enum):
    """Reminder and escalation stages from the behavior contract."""

    WARNING_545 = "545pm-warning"
    URGENT_600 = "6pm-urgent"
    LASTCALL_645 = "645pm-lastcall"
    ESCALATION_URGENT_655 = "655pm-urgent-escalation"
    ESCALATION_NUCLEAR_700 = "700pm-nuclear-escalation"


class StatusVariant(str, Enum):
    """Message variants used by the status button."""

    SUNDAY_NO_MOVE = "sunday-no-move"
    UPCOMING_MOVE = "upcoming-6-7pm-move"
    ACTIVE_WINDOW = "active-urgent-window"
    CONFIRMATION = "confirmation-after-window"


@dataclass(frozen=True)
class ParkingDecision:
    """Parking side decision for a local New York calendar day."""

    current_side: Side | None
    destination_side: Side | None
    no_move_required: bool = False


@dataclass(frozen=True)
class SuppressionDecision:
    """Result of applying acknowledgments to a reminder/escalation stage."""

    suppressed: bool
    ack_type: AckType | None = None
