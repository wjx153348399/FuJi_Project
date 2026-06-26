from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True)
class DateWindow:
    target_day: str
    start: datetime
    end: datetime

    def contains(self, value: datetime) -> bool:
        if value.tzinfo is None:
            raise ValueError("datetime must be timezone-aware")

        local_value = value.astimezone(self.start.tzinfo)
        return self.start <= local_value < self.end


def build_date_window(now: datetime | None = None, day_offset: int = 1) -> DateWindow:
    if day_offset < 0:
        raise ValueError("day_offset must be greater than or equal to 0")

    current_time = now or datetime.now(SHANGHAI_TZ)
    if current_time.tzinfo is None:
        raise ValueError("now must be timezone-aware")

    current_time = current_time.astimezone(SHANGHAI_TZ)
    target_date = current_time.date() - timedelta(days=day_offset)
    start = datetime.combine(target_date, time.min, tzinfo=SHANGHAI_TZ)
    end = start + timedelta(days=1)

    return DateWindow(
        target_day=target_date.isoformat(),
        start=start,
        end=end,
    )
