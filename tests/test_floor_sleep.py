import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from test_server import SERVER


class FloorSleepTests(unittest.TestCase):
    def test_independent_persisted_floors_and_generated_helpers(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bedrooms.yaml"
            publisher = Mock()
            manager = SERVER.BedroomModeAutomationManager(path, publisher)
            floors = {
                "first": {"name": "First Floor", "sources": ["input_select.fht_bedroom_1_mode"]},
                "second": {"name": "Second Floor", "sources": ["input_select.fht_bedroom_2_mode"]},
                "empty": {"name": "Basement", "sources": []},
            }
            manager.save_house_settings({"day_offset": 0, "night_offset": 0, "sleep_mode_sources": [], "floor_sleep_modes": floors})
            self.assertEqual(manager.house_settings()["floor_sleep_modes"], floors)
            manager.save_house_settings({"day_offset": 15, "night_offset": -15})
            self.assertEqual(manager.house_settings()["floor_sleep_modes"], floors)
            templates = manager.floor_sleep_templates(floors)
            first = next(item for item in templates if item["name"] == "First Floor Sleep Mode")
            self.assertIn("fht_bedroom_1_mode", first["state"])
            self.assertNotIn("fht_bedroom_2_mode", first["state"])
            self.assertIn("'Sleep'", first["state"])
            manager.sync({}, [], [])
            self.assertIn("First Floor Sleep Mode", path.read_text())
            self.assertIn("template", publisher.reload_domains.call_args.args[0])

    def test_reject_invalid_sources(self):
        for sources in ["input_select.fht_bedroom_1_mode", ["switch.fan"], ["*"]]:
            with self.assertRaises(ValueError):
                SERVER.BedroomModeAutomationManager.clean_floor_sleep_modes({"first": {"name": "First Floor", "sources": sources}})
