from __future__ import annotations

import unittest

from zk_impedance_upload.config import (
    AppConfig,
    LogConfig,
    ScanConfig,
    ScanTargetConfig,
    ShareConfig,
    StationConfig,
    StationDbConfig,
    UploadConfig,
    WatchConfig,
)
from zk_impedance_upload.exceptions import ConfigError
from zk_impedance_upload.station_config import build_effective_scan_config


class FakeRepository:
    def __init__(self, targets=None, error: Exception | None = None):
        self.targets = targets or []
        self.error = error
        self.calls = 0

    def load_targets(self, db_config):
        self.calls += 1
        if self.error:
            raise self.error
        return self.targets


class StationConfigTest(unittest.TestCase):
    def test_json_mode_uses_scan_targets_without_repository(self):
        repository = FakeRepository(
            targets=[ScanTargetConfig(station_code="A50", dir="db-dir")]
        )

        effective = build_effective_scan_config(_config(source="json"), repository)

        self.assertEqual(repository.calls, 0)
        self.assertEqual(effective.effective_source, "json")
        self.assertEqual(effective.scan.targets[0].station_code, "A10")
        self.assertEqual(effective.scan.targets[0].dir, "json-dir")

    def test_db_mode_uses_repository_targets(self):
        repository = FakeRepository(
            targets=[ScanTargetConfig(station_code="A50", dir="db-dir")]
        )

        effective = build_effective_scan_config(_config(source="db"), repository)

        self.assertEqual(repository.calls, 1)
        self.assertEqual(effective.effective_source, "db")
        self.assertEqual(effective.scan.targets[0].station_code, "A50")
        self.assertEqual(effective.scan.targets[0].dir, "db-dir")
        self.assertEqual(effective.scan.target_dirs, [])

    def test_db_mode_raises_when_repository_fails(self):
        repository = FakeRepository(error=ConfigError("database connection failed"))

        with self.assertRaisesRegex(ConfigError, "database connection failed"):
            build_effective_scan_config(_config(source="db"), repository)

    def test_db_mode_raises_when_database_returns_empty_targets(self):
        repository = FakeRepository(targets=[])

        with self.assertRaisesRegex(ConfigError, "未返回任何启用"):
            build_effective_scan_config(_config(source="db"), repository)

    def test_db_then_json_uses_database_when_available(self):
        repository = FakeRepository(
            targets=[ScanTargetConfig(station_code="A50", dir="db-dir")]
        )

        effective = build_effective_scan_config(_config(source="db_then_json"), repository)

        self.assertEqual(effective.requested_source, "db_then_json")
        self.assertEqual(effective.effective_source, "db")
        self.assertIsNone(effective.fallback_reason)
        self.assertEqual(effective.scan.targets[0].station_code, "A50")

    def test_db_then_json_falls_back_to_json_when_repository_fails(self):
        repository = FakeRepository(error=ConfigError("database connection failed"))

        effective = build_effective_scan_config(_config(source="db_then_json"), repository)

        self.assertEqual(effective.requested_source, "db_then_json")
        self.assertEqual(effective.effective_source, "json")
        self.assertEqual(effective.scan.targets[0].station_code, "A10")
        self.assertIn("database connection failed", effective.fallback_reason)

    def test_db_then_json_falls_back_to_json_when_database_returns_empty_targets(self):
        repository = FakeRepository(targets=[])

        effective = build_effective_scan_config(_config(source="db_then_json"), repository)

        self.assertEqual(effective.effective_source, "json")
        self.assertEqual(effective.fallback_reason, "database returned no enabled targets")

    def test_duplicate_directory_config_raises_clear_error(self):
        repository = FakeRepository(
            targets=[
                ScanTargetConfig(station_code="A10", dir="same-dir"),
                ScanTargetConfig(station_code="A50", dir="same-dir"),
            ]
        )

        with self.assertRaisesRegex(ConfigError, "Duplicate station directory config"):
            build_effective_scan_config(_config(source="db"), repository)

    def test_absolute_directory_config_raises_clear_error(self):
        repository = FakeRepository(
            targets=[ScanTargetConfig(station_code="A10", dir=r"C:\share\station")]
        )

        with self.assertRaisesRegex(ConfigError, "relative to share.root"):
            build_effective_scan_config(_config(source="db"), repository)

    def test_unsupported_station_code_raises_clear_error(self):
        repository = FakeRepository(
            targets=[ScanTargetConfig(station_code="A 10", dir="station-a")]
        )

        with self.assertRaisesRegex(ConfigError, "unsupported characters"):
            build_effective_scan_config(_config(source="db"), repository)


def _config(source: str) -> AppConfig:
    return AppConfig(
        share=ShareConfig(root=r"\\server\share", username="IT", password="FQCIT"),
        log=LogConfig(dir=r"\\server\log"),
        upload=UploadConfig(url="http://example.test/upload"),
        scan=ScanConfig(
            target_dirs=["legacy-dir"],
            targets=[ScanTargetConfig(station_code="A10", dir="json-dir")],
        ),
        watch=WatchConfig(),
        station_config=StationConfig(
            source=source,
            on_db_error="fallback_to_json",
            db=StationDbConfig(
                enabled=source != "json",
                driver="sqlserver",
                host="127.0.0.1",
                port=1433,
                database="QMS",
                username="sa",
                password="secret",
                table="dbo.station_directory_config",
            ),
        ),
    )


if __name__ == "__main__":
    unittest.main()
