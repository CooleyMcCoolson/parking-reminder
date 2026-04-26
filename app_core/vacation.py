"""File-backed vacation mode state for the future rewrite core."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .state import DEFAULT_STATE_DIR
from .timezone import as_new_york

DEFAULT_VACATION_FILENAME = "vacation-mode"
SECONDS_PER_DAY = 86400


class VacationState:
    """Read and mutate the vacation-mode flag file."""

    def __init__(
        self,
        state_dir: Path | str = DEFAULT_STATE_DIR,
        vacation_file: Path | str | None = None,
    ) -> None:
        self.state_dir = Path(state_dir)
        self.vacation_file = (
            Path(vacation_file)
            if vacation_file is not None
            else self.state_dir / DEFAULT_VACATION_FILENAME
        )

    def is_enabled(self, now: datetime) -> bool:
        """Return whether vacation mode is active at ``now``.

        Expired timestamp files are removed, matching the existing Bash library.
        """

        if not self.vacation_file.exists():
            return False

        raw_value = self.vacation_file.read_text().strip()
        if raw_value == "":
            return True

        try:
            expiry_timestamp = Decimal(raw_value)
        except InvalidOperation:
            return True

        if not expiry_timestamp.is_finite() or expiry_timestamp < 0:
            return True

        now_timestamp = Decimal(str(as_new_york(now).timestamp()))
        if now_timestamp > expiry_timestamp:
            self.disable()
            return False

        return True

    def toggle_web(self) -> bool:
        """Toggle web-style vacation mode and return the new enabled state."""

        if self.vacation_file.exists():
            self.disable()
            return False

        self.enable_indefinitely()
        return True

    def enable_indefinitely(self) -> None:
        """Create an empty vacation file with no expiration."""

        self.vacation_file.parent.mkdir(parents=True, exist_ok=True)
        self.vacation_file.write_text("")

    def enable_for_days(self, days: int, now: datetime) -> None:
        """Enable vacation mode until ``days`` from ``now``."""

        if days <= 0:
            raise ValueError("Vacation duration must be a positive number of days")

        expiry = int(as_new_york(now).timestamp()) + (days * SECONDS_PER_DAY)
        self.vacation_file.parent.mkdir(parents=True, exist_ok=True)
        self.vacation_file.write_text(str(expiry))

    def disable(self) -> None:
        """Disable vacation mode by removing the flag file if present."""

        self.vacation_file.unlink(missing_ok=True)
