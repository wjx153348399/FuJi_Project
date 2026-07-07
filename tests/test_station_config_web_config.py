from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from station_config_web.config import load_web_config
from zk_impedance_upload.exceptions import ConfigError


class StationConfigWebConfigTest(unittest.TestCase):
    def test_loads_web_config(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "web_config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "server": {"host": "127.0.0.1", "port": 8090},
                        "db": {
                            "driver": "ODBC Driver 17 for SQL Server",
                            "host": "192.168.0.253",
                            "port": 1433,
                            "database": "QMS",
                            "username": "sa",
                            "password": "secret",
                            "table": "dbo.station_directory_config",
                        },
                        "share": {
                            "root": r"\\server\share\impedance",
                            "username": "IT",
                            "password": "FQCIT",
                        },
                        "log": {"dir": r"\\server\share\ZK_LOG"},
                        "auth": {"username": "admin", "password": "secret"},
                    }
                ),
                encoding="utf-8",
            )

            config = load_web_config(config_path)

        self.assertEqual(config.server.port, 8090)
        self.assertEqual(config.db.database, "QMS")
        self.assertEqual(config.db.table, "dbo.station_directory_config")
        self.assertEqual(config.share.root, r"\\server\share\impedance")
        self.assertEqual(config.share.username, "IT")
        self.assertEqual(config.share.password, "FQCIT")
        self.assertEqual(config.log.dir, r"\\server\share\ZK_LOG")
        self.assertEqual(config.auth.username, "admin")

    def test_missing_auth_password_raises_clear_error(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "web_config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "db": {
                            "host": "192.168.0.253",
                            "database": "QMS",
                            "username": "sa",
                            "password": "secret",
                        },
                        "share": {"root": r"\\server\share"},
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ConfigError, "auth.password"):
                load_web_config(config_path)


if __name__ == "__main__":
    unittest.main()
