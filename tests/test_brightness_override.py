"""Verify quick-cycle targeting and generated native override actions."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from test_server import SERVER


class BrightnessOverrideTests(unittest.TestCase):
    def setUp(self):
        self.entities = [
            {"entity_id": "switch.room", "domain": "switch", "device_id": "wall", "wired_load_ids": ["light.wired"]},
            {"entity_id": "light.wired", "domain": "light", "supported_color_modes": ["brightness"]},
            {"entity_id": "light.group", "domain": "light", "members": ["light.color", "light.fixed", "light.wired"]},
            {"entity_id": "light.color", "domain": "light", "supported_color_modes": ["rgb"]},
            {"entity_id": "light.fixed", "domain": "light", "supported_color_modes": ["onoff"]},
        ]

    def test_combines_wired_and_assigned_dimmable_leaves(self):
        descriptions = SERVER.ControlAutomationManager.describe({"switch.room": "light.group"}, self.entities)
        self.assertEqual(SERVER.SwitchBrightnessOverride.targets(self.entities, descriptions), {"switch.room": ["light.color", "light.wired"]})

    def test_excludes_inovelli_by_manufacturer_even_when_renamed(self):
        self.entities[0]["manufacturer"] = "Inovelli"
        self.assertEqual(SERVER.SwitchBrightnessOverride.targets(self.entities, []), {})

    def test_excludes_inovelli_event_device(self):
        self.entities.append({"entity_id": "event.room_button_up", "domain": "event", "device_id": "wall"})
        self.assertEqual(SERVER.SwitchBrightnessOverride.targets(self.entities, []), {})

    def test_onoff_and_unknown_capability_do_not_generate_override(self):
        for modes in [["onoff"], [], ["unknown"]]:
            self.entities[1]["supported_color_modes"] = modes
            self.assertEqual(SERVER.SwitchBrightnessOverride.targets(self.entities, []), {})

    def test_nested_group_cycle_is_safe(self):
        self.entities[2]["members"].append("light.group")
        descriptions = SERVER.ControlAutomationManager.describe({"switch.room": "light.group"}, self.entities)
        self.assertEqual(SERVER.SwitchBrightnessOverride.targets(self.entities, descriptions)["switch.room"], ["light.color", "light.wired"])

    def test_three_second_physical_cycle_and_clear_actions(self):
        helpers, automations = SERVER.SwitchBrightnessOverride.render({"switch.room": ["light.wired"]})
        cycle, clear = automations
        self.assertEqual(cycle["triggers"][0]["from"], "on")
        self.assertEqual(cycle["actions"][0]["timeout"], "00:00:03")
        self.assertFalse(cycle["actions"][0]["continue_on_timeout"])
        self.assertIn("parent_id is none", cycle["conditions"][0]["value_template"])
        self.assertIn("user_id is none", cycle["actions"][1]["value_template"])
        self.assertEqual(cycle["actions"][2]["action"], "input_boolean.turn_on")
        self.assertEqual(cycle["actions"][3]["data"], {"brightness_pct": 100})
        self.assertEqual(clear["triggers"][0]["to"], "off")
        self.assertEqual(clear["actions"][-1]["action"], "input_boolean.turn_off")
        self.assertFalse(next(iter(helpers.values()))["initial"])

    def test_wired_only_switch_generates_helpers_without_extra_assignments(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "controls.yaml"
            publisher = Mock()
            SERVER.ControlAutomationManager(path, publisher).sync({}, self.entities)
            source = path.read_text()
            self.assertIn("automation:\n", source)
            generated = [json.loads(line[4:]) for line in source.splitlines() if line.startswith("  - {")]
            self.assertEqual(len(generated), 2)
            self.assertIn("input_boolean:", source)
            publisher.reload_domains.assert_called_once_with(("input_boolean", "automation"))

    def test_presence_guards_both_activation_and_mode_change_but_not_vacancy(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "presence.yaml"
            SERVER.PresenceAutomationManager(path).sync({"binary_sensor.room": "light.group"}, self.entities)
            source = path.read_text()
            helper = SERVER.SwitchBrightnessOverride.helper("light.wired")
            self.assertEqual(source.count(helper), 2)
            self.assertIn("action: light.turn_off", source)

    def test_inventory_keeps_dimming_capability(self):
        result = SERVER.normalize_entities([{"entity_id": "light.test", "state": "off", "attributes": {"supported_color_modes": ["brightness"]}}])
        self.assertEqual(result[0]["supported_color_modes"], ["brightness"])
