"""File-backed acknowledgment state for the future rewrite core."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable

from .models import AckType
from .timezone import as_new_york

DEFAULT_STATE_DIR = Path("/var/lib/parking-reminder")
ACK_MAX_AGE_SECONDS = Decimal("14400")
ACK_FUTURE_SKEW_SECONDS = Decimal("300")


@dataclass(frozen=True)
class CleanupResult:
    """Summary of files removed by acknowledgment cleanup."""

    deleted: tuple[Path, ...]


@dataclass(frozen=True)
class ParsedAckFile:
    """Parsed acknowledgment filename details."""

    path: Path
    ack_type: AckType | None
    timestamp: Decimal | None
    malformed: bool = False


class AcknowledgmentState:
    """Read, create, and clean up timestamped acknowledgment files."""

    def __init__(self, state_dir: Path | str = DEFAULT_STATE_DIR) -> None:
        self.state_dir = Path(state_dir)

    def valid_ack_types(self, now: datetime) -> set[AckType]:
        """Return supported ack types that are currently valid at ``now``."""

        now_timestamp = _aware_timestamp(now)
        valid: set[AckType] = set()

        if not self.state_dir.exists():
            return valid

        for parsed in self._iter_ack_files():
            if (
                parsed.malformed
                or parsed.ack_type is None
                or parsed.timestamp is None
            ):
                continue
            if _timestamp_is_valid(parsed.timestamp, now_timestamp):
                valid.add(parsed.ack_type)

        return valid

    def create_ack(self, ack_type: AckType | str, now: datetime | None = None) -> Path:
        """Create an empty ack file atomically and return its path."""

        normalized_ack = _to_ack_type(ack_type)
        self.state_dir.mkdir(parents=True, exist_ok=True)

        timestamp = _creation_timestamp(now)
        ack_path = self.state_dir / f"ack-{normalized_ack.value}.{timestamp}"

        try:
            _create_empty_file_exclusive(ack_path)
            return ack_path
        except FileExistsError:
            fallback_path = self.state_dir / f"ack-{normalized_ack.value}.{time.time_ns()}"
            _create_empty_file_exclusive(fallback_path)
            return fallback_path

    def cleanup(self, now: datetime) -> CleanupResult:
        """Delete malformed ack files and expired timestamped ack files."""

        now_timestamp = _aware_timestamp(now)
        deleted: list[Path] = []

        if not self.state_dir.exists():
            return CleanupResult(deleted=())

        for parsed in self._iter_ack_files():
            should_delete = parsed.malformed
            if parsed.timestamp is not None and _timestamp_is_expired(
                parsed.timestamp,
                now_timestamp,
            ):
                should_delete = True

            if should_delete:
                try:
                    parsed.path.unlink()
                except FileNotFoundError:
                    continue
                deleted.append(parsed.path)

        return CleanupResult(deleted=tuple(deleted))

    def _iter_ack_files(self) -> Iterable[ParsedAckFile]:
        for path in sorted(self.state_dir.iterdir()):
            if path.is_file() and path.name.startswith("ack-"):
                yield parse_ack_filename(path)


def parse_ack_filename(path: Path) -> ParsedAckFile:
    """Parse ``ack-TYPE.TIMESTAMP`` using the filename as source of truth."""

    name = path.name
    if not name.startswith("ack-"):
        return ParsedAckFile(path=path, ack_type=None, timestamp=None, malformed=True)

    body = name.removeprefix("ack-")
    if "." not in body:
        return ParsedAckFile(path=path, ack_type=None, timestamp=None, malformed=True)

    ack_type_text, timestamp_text = body.split(".", 1)

    try:
        ack_type = AckType(ack_type_text)
    except ValueError:
        ack_type = None

    try:
        timestamp = Decimal(timestamp_text)
    except InvalidOperation:
        return ParsedAckFile(
            path=path,
            ack_type=ack_type,
            timestamp=None,
            malformed=True,
        )

    if not timestamp.is_finite() or timestamp < 0:
        return ParsedAckFile(
            path=path,
            ack_type=ack_type,
            timestamp=None,
            malformed=True,
        )

    return ParsedAckFile(path=path, ack_type=ack_type, timestamp=timestamp)


def _to_ack_type(value: AckType | str) -> AckType:
    if isinstance(value, AckType):
        return value
    return AckType(value)


def _aware_timestamp(moment: datetime) -> Decimal:
    return Decimal(str(as_new_york(moment).timestamp()))


def _creation_timestamp(now: datetime | None) -> str:
    if now is None:
        return f"{time.time():.6f}"
    return f"{_aware_timestamp(now):.6f}"


def _timestamp_is_valid(timestamp: Decimal, now_timestamp: Decimal) -> bool:
    age = now_timestamp - timestamp
    return -ACK_FUTURE_SKEW_SECONDS <= age <= ACK_MAX_AGE_SECONDS


def _timestamp_is_expired(timestamp: Decimal, now_timestamp: Decimal) -> bool:
    return now_timestamp - timestamp > ACK_MAX_AGE_SECONDS


def _create_empty_file_exclusive(path: Path) -> None:
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    os.close(fd)
