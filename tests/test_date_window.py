import unittest
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from zk_impedance_upload.date_window import DateWindow, build_date_window


class DateWindowTest(unittest.TestCase):
    def test_builds_previous_day_window_in_shanghai_timezone(self):
        now = datetime(2026, 6, 14, 8, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

        window = build_date_window(now=now, day_offset=1)

        self.assertEqual(window.target_day, "2026-06-13")
        self.assertEqual(window.start, datetime(2026, 6, 13, 0, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai")))
        self.assertEqual(window.end, datetime(2026, 6, 14, 0, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai")))

    def test_contains_uses_left_closed_right_open_range(self):
        window = DateWindow(
            target_day="2026-06-13",
            start=datetime(2026, 6, 13, 0, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
            end=datetime(2026, 6, 14, 0, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
        )

        self.assertTrue(window.contains(datetime(2026, 6, 13, 0, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))))
        self.assertTrue(window.contains(datetime(2026, 6, 13, 23, 59, 59, tzinfo=ZoneInfo("Asia/Shanghai"))))
        self.assertFalse(window.contains(datetime(2026, 6, 14, 0, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))))
        self.assertFalse(window.contains(datetime(2026, 6, 12, 23, 59, 59, tzinfo=ZoneInfo("Asia/Shanghai"))))

    def test_contains_converts_utc_datetime_to_shanghai_timezone(self):
        window = DateWindow(
            target_day="2026-06-13",
            start=datetime(2026, 6, 13, 0, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
            end=datetime(2026, 6, 14, 0, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
        )

        self.assertTrue(window.contains(datetime(2026, 6, 12, 16, 0, 0, tzinfo=timezone.utc)))
        self.assertFalse(window.contains(datetime(2026, 6, 13, 16, 0, 0, tzinfo=timezone.utc)))

    def test_rejects_naive_datetimes(self):
        window = build_date_window(now=datetime(2026, 6, 14, 8, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai")))

        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            window.contains(datetime(2026, 6, 13, 8, 0, 0))


if __name__ == "__main__":
    unittest.main()
