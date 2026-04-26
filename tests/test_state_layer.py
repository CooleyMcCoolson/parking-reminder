from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app_core import AckType, AcknowledgmentState, NEW_YORK_TZ, VacationState


def ny_datetime(year: int, month: int, day: int, hour: int, minute: int) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=NEW_YORK_TZ)


def write_file(path: Path, content: str = "x") -> Path:
    path.write_text(content)
    return path


def ack_path(state_dir: Path, ack_type: str, timestamp: float | int | str) -> Path:
    return state_dir / f"ack-{ack_type}.{timestamp}"


def test_valid_ack_parsing_for_integer_timestamps(tmp_path: Path) -> None:
    now = ny_datetime(2026, 4, 20, 18, 0)
    write_file(ack_path(tmp_path, "gotit", int(now.timestamp())))

    state = AcknowledgmentState(tmp_path)

    assert state.valid_ack_types(now) == {AckType.GOTIT}


def test_valid_ack_parsing_for_decimal_timestamps(tmp_path: Path) -> None:
    now = ny_datetime(2026, 4, 20, 18, 0)
    write_file(ack_path(tmp_path, "moved", f"{now.timestamp():.6f}"))

    state = AcknowledgmentState(tmp_path)

    assert state.valid_ack_types(now) == {AckType.MOVED}


def test_expired_ack_is_ignored(tmp_path: Path) -> None:
    now = ny_datetime(2026, 4, 20, 18, 0)
    expired = now - timedelta(seconds=14401)
    write_file(ack_path(tmp_path, "done", int(expired.timestamp())))

    state = AcknowledgmentState(tmp_path)

    assert state.valid_ack_types(now) == set()


def test_ack_up_to_five_minutes_in_future_is_accepted(tmp_path: Path) -> None:
    now = ny_datetime(2026, 4, 20, 18, 0)
    future = now + timedelta(minutes=5)
    write_file(ack_path(tmp_path, "nothome", int(future.timestamp())))

    state = AcknowledgmentState(tmp_path)

    assert state.valid_ack_types(now) == {AckType.NOTHOME}


def test_ack_too_far_in_future_is_ignored(tmp_path: Path) -> None:
    now = ny_datetime(2026, 4, 20, 18, 0)
    future = now + timedelta(minutes=5, seconds=1)
    write_file(ack_path(tmp_path, "nothome", int(future.timestamp())))

    state = AcknowledgmentState(tmp_path)

    assert state.valid_ack_types(now) == set()


def test_malformed_ack_files_are_ignored_and_cleanup_deletes_them(
    tmp_path: Path,
) -> None:
    now = ny_datetime(2026, 4, 20, 18, 0)
    malformed = write_file(tmp_path / "ack-gotit.not-a-timestamp")
    missing_timestamp = write_file(tmp_path / "ack-moved")

    state = AcknowledgmentState(tmp_path)

    assert state.valid_ack_types(now) == set()

    result = state.cleanup(now)

    assert set(result.deleted) == {malformed, missing_timestamp}
    assert not malformed.exists()
    assert not missing_timestamp.exists()


def test_unknown_ack_types_are_ignored(tmp_path: Path) -> None:
    now = ny_datetime(2026, 4, 20, 18, 0)
    unknown = write_file(ack_path(tmp_path, "surprise", int(now.timestamp())))

    state = AcknowledgmentState(tmp_path)

    assert state.valid_ack_types(now) == set()
    assert unknown.exists()


def test_create_ack_creates_empty_file_with_expected_name(tmp_path: Path) -> None:
    now = ny_datetime(2026, 4, 20, 18, 0)
    state = AcknowledgmentState(tmp_path)

    created = state.create_ack(AckType.GOTIT, now=now)

    assert created.parent == tmp_path
    assert created.name.startswith("ack-gotit.")
    assert created.read_text() == ""
    assert state.valid_ack_types(now) == {AckType.GOTIT}


def test_create_ack_rejects_unknown_ack_type(tmp_path: Path) -> None:
    state = AcknowledgmentState(tmp_path)

    with pytest.raises(ValueError):
        state.create_ack("unknown")


def test_cleanup_deletes_expired_and_malformed_ack_files_but_keeps_valid(
    tmp_path: Path,
) -> None:
    now = ny_datetime(2026, 4, 20, 18, 0)
    valid = write_file(ack_path(tmp_path, "gotit", int(now.timestamp())))
    expired_time = now - timedelta(hours=4, seconds=1)
    expired = write_file(ack_path(tmp_path, "moved", int(expired_time.timestamp())))
    malformed = write_file(tmp_path / "ack-done.invalid")

    state = AcknowledgmentState(tmp_path)

    result = state.cleanup(now)

    assert set(result.deleted) == {expired, malformed}
    assert valid.exists()
    assert not expired.exists()
    assert not malformed.exists()


def test_missing_vacation_file_is_disabled(tmp_path: Path) -> None:
    vacation = VacationState(tmp_path)

    assert vacation.is_enabled(ny_datetime(2026, 4, 20, 12, 0)) is False


def test_empty_vacation_file_is_enabled_indefinitely(tmp_path: Path) -> None:
    vacation = VacationState(tmp_path)
    vacation.vacation_file.parent.mkdir(parents=True, exist_ok=True)
    vacation.vacation_file.write_text("")

    assert vacation.is_enabled(ny_datetime(2026, 4, 20, 12, 0)) is True


def test_invalid_vacation_file_is_enabled_indefinitely(tmp_path: Path) -> None:
    vacation = VacationState(tmp_path)
    vacation.vacation_file.parent.mkdir(parents=True, exist_ok=True)
    vacation.vacation_file.write_text("not-a-timestamp")

    assert vacation.is_enabled(ny_datetime(2026, 4, 20, 12, 0)) is True


def test_future_vacation_timestamp_is_enabled(tmp_path: Path) -> None:
    now = ny_datetime(2026, 4, 20, 12, 0)
    future = now + timedelta(days=1)
    vacation = VacationState(tmp_path)
    vacation.vacation_file.parent.mkdir(parents=True, exist_ok=True)
    vacation.vacation_file.write_text(str(int(future.timestamp())))

    assert vacation.is_enabled(now) is True
    assert vacation.vacation_file.exists()


def test_past_vacation_timestamp_is_disabled_and_file_removed(tmp_path: Path) -> None:
    now = ny_datetime(2026, 4, 20, 12, 0)
    past = now - timedelta(seconds=1)
    vacation = VacationState(tmp_path)
    vacation.vacation_file.parent.mkdir(parents=True, exist_ok=True)
    vacation.vacation_file.write_text(str(int(past.timestamp())))

    assert vacation.is_enabled(now) is False
    assert not vacation.vacation_file.exists()


def test_web_toggle_enable_disable_works(tmp_path: Path) -> None:
    vacation = VacationState(tmp_path)

    assert vacation.toggle_web() is True
    assert vacation.vacation_file.exists()
    assert vacation.vacation_file.read_text() == ""

    assert vacation.toggle_web() is False
    assert not vacation.vacation_file.exists()


def test_enable_for_days_writes_future_expiration(tmp_path: Path) -> None:
    now = ny_datetime(2026, 4, 20, 12, 0)
    vacation = VacationState(tmp_path)

    vacation.enable_for_days(7, now)

    expected = int(now.timestamp()) + (7 * 86400)
    assert vacation.vacation_file.read_text() == str(expected)
    assert vacation.is_enabled(now) is True
