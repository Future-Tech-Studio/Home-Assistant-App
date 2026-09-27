import tempfile
import unittest
from pathlib import Path

from test_server import SERVER


class ExhaustTimerTests(unittest.TestCase):
    def test_storage_validation_and_disable(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = SERVER.SwitchControlSettings(Path(directory) / "controls.json")
            settings.save_exhaust_timer("switch.toilet", 5)
            self.assertEqual(settings.read()["exhaust_timers"], {"switch.toilet": 5})
            for value in [-1, 121, 1.5, True, "5"]:
                with self.assertRaises(ValueError):
                    settings.save_exhaust_timer("switch.toilet", value)
            settings.save_exhaust_timer("switch.toilet", 0)
            self.assertEqual(settings.read()["exhaust_timers"], {})

    def test_wired_fan_timer_and_cancel(self):
        entities = [{"entity_id": "switch.toilet", "wired_load_names": {"fan.toilet": "Toilet Exhaust Fan"}}]
        automations = SERVER.ExhaustFanTimer.render({"switch.toilet": 5, "switch.light": 10}, entities)
        self.assertEqual(len(automations), 1)
        timer = automations[0]
        self.assertEqual(timer["mode"], "restart")
        self.assertEqual(timer["triggers"][1]["to"], "off")
        self.assertEqual(timer["actions"][1], {"delay": {"minutes": 5}})
        self.assertEqual(timer["actions"][-1]["target"]["entity_id"], "switch.toilet")

    def test_package_contains_timer_without_action_assignment(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "controls.yaml"
            manager = SERVER.ControlAutomationManager(path)
            manager.sync({}, [{"entity_id": "switch.fan", "friendly_name": "Exhaust Fan"}], exhaust_timers={"switch.fan": 5})
            self.assertIn('"minutes": 5', path.read_text())
