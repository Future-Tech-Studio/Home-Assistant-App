import unittest
from unittest.mock import Mock, patch

from test_server import SERVER


class SleepChoiceTests(unittest.TestCase):
    def test_only_current_sleep_enabled_bedrooms_are_offered(self):
        handler = SERVER.FutureHomesTechRequestHandler.__new__(SERVER.FutureHomesTechRequestHandler)
        handler.inventory = Mock()
        handler.inventory.peek.return_value = {"entities": []}
        handler.room_aliases = Mock()
        handler.room_aliases.read.return_value = {"Bedroom 1": "Master Bedroom", "Bathroom 1": "Master Bathroom"}
        handler.bedroom_modes = Mock()
        handler.bedroom_modes.read.return_value = {"Retired Bedroom": {}}
        handler.room_modes = Mock()
        handler.room_modes.read.return_value = {
            "Bedroom 1": ["sleep"], "Bathroom 1": ["sleep"],
            "Retired Bedroom": ["sleep"], "Bedroom 2": ["relax"],
        }
        handler.bedroom_mode_automations = Mock()
        handler.bedroom_mode_automations.house_settings.return_value = {}
        structure = {"floors": [{"name": "First Floor", "areas": [
            {"name": area} for area in ["Bedroom 1", "Bathroom 1", "Bedroom 2"]
        ]}]}
        with patch.object(SERVER, "home_structure_from_storage", return_value=structure):
            options = handler._home_configurator_index()["sleep_mode_options"]
        self.assertEqual(options, [{"entity_id": "input_select.fht_bedroom_1_mode", "label": "Master Bedroom", "floor_id": ""}])
