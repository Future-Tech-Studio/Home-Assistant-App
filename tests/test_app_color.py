import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from test_server import SERVER


class AppColorTests(unittest.TestCase):
    def test_persistence_validation_and_isolation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bedrooms.yaml"
            manager = SERVER.BedroomModeAutomationManager(path, Mock())
            self.assertEqual(manager.app_color(), "blue")
            manager.save_house_settings({"day_offset": 15, "night_offset": -30})
            before = path.with_suffix(".house.json").read_bytes()
            for color in ("red", "green", "blue"):
                manager.save_app_color(color)
                self.assertEqual(SERVER.BedroomModeAutomationManager(path, Mock()).app_color(), color)
                self.assertEqual(path.with_suffix(".house.json").read_bytes(), before)
            for invalid in (None, "purple", [], 1):
                with self.assertRaises(ValueError):
                    manager.save_app_color(invalid)
            path.with_suffix(".appearance.json").write_text("invalid")
            self.assertEqual(manager.app_color(), "blue")
