"""Tests for moving saved settings from a local install to a repository install."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

MODULE_PATH = Path(__file__).resolve().parents[1] / "future_homes_tech_app" / "fht_transfer.py"
SPEC = importlib.util.spec_from_file_location("fht_transfer", MODULE_PATH)
TRANSFER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TRANSFER)


class SettingsTransferTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.local = root / "local"
        self.repository = root / "repository"
        self.transfer = root / "homeassistant/.future_homes_tech_transfer/app-data.tar.gz"
        self.local.mkdir()
        self.repository.mkdir()
        (self.local / "options.json").write_text('{"protect_api_key": "local"}')
        (self.local / "room_modes.json").write_text('{"Kitchen": "day"}')
        (self.local / "users_access").mkdir()
        (self.local / "users_access/users.json").write_text("[]")
        (self.local / "beta/releases").mkdir(parents=True)
        (self.repository / "options.json").write_text('{"protect_api_key": ""}')

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_moves_saved_settings_and_options_once(self) -> None:
        options = {"protect_api_key": "secret", "entry_delay_seconds": 45}
        self.assertEqual(TRANSFER.export_settings(options, self.local, self.transfer), 2)
        self.assertEqual(self.transfer.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.transfer.parent.stat().st_mode & 0o777, 0o700)

        imported = TRANSFER.import_settings(self.repository, self.transfer)

        self.assertEqual(imported, options)
        self.assertEqual((self.repository / "room_modes.json").read_text(), '{"Kitchen": "day"}')
        self.assertEqual((self.repository / "users_access/users.json").read_text(), "[]")
        self.assertEqual((self.repository / "options.json").read_text(), '{"protect_api_key": ""}')
        self.assertFalse((self.repository / "beta").exists())
        self.assertTrue((self.repository / TRANSFER.IMPORTED_MARKER).is_file())
        self.assertFalse(self.transfer.exists())

        TRANSFER.export_settings(options, self.local, self.transfer)
        self.assertIsNone(TRANSFER.import_settings(self.repository, self.transfer))

    def test_never_overwrites_an_install_with_saved_settings(self) -> None:
        TRANSFER.export_settings({}, self.local, self.transfer)
        (self.repository / "room_modes.json").write_text("{}")
        self.assertIsNone(TRANSFER.import_settings(self.repository, self.transfer))
        self.assertEqual((self.repository / "room_modes.json").read_text(), "{}")
        self.assertTrue(self.transfer.exists())

    def test_nothing_to_import_without_a_transfer_file(self) -> None:
        self.assertIsNone(TRANSFER.import_settings(self.repository, self.transfer))

    def test_command_line_round_trip(self) -> None:
        import io
        from unittest.mock import patch

        environment = {"FHT_DATA_DIR": str(self.local), "FHT_TRANSFER_PATH": str(self.transfer)}
        with patch.dict(TRANSFER.os.environ, environment), patch("sys.stdin", io.StringIO('{"beta_mode": true}')), patch("sys.stdout", io.StringIO()):
            self.assertEqual(TRANSFER.main(["transfer", "export"]), 0)
        environment["FHT_DATA_DIR"] = str(self.repository)
        output = io.StringIO()
        with patch.dict(TRANSFER.os.environ, environment), patch("sys.stdout", output):
            self.assertEqual(TRANSFER.main(["transfer", "import"]), 0)
        self.assertEqual(json.loads(output.getvalue()), {"beta_mode": True})
        with patch.dict(TRANSFER.os.environ, environment):
            self.assertEqual(TRANSFER.main(["transfer", "import"]), 3)


if __name__ == "__main__":
    unittest.main()
