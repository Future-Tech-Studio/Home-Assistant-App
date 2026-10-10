import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from access_preview import SERVER


class MaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.config = self.root / "config"
        self.config.mkdir()
        (self.config / "configuration.yaml").write_text("default_config:\n")
        self.registry = [{"entity_id": "input_select.fht_old", "unique_id": "fht_old_helper", "platform": "input_select", "device_id": None, "config_entry_id": None, "disabled_by": None, "hidden_by": None}]
        self.states = [{"entity_id": "input_select.fht_old", "state": "unavailable", "attributes": {"restored": True, "friendly_name": "Retired helper"}}]
        self.snapshot = {"entities": [], "stale": False, "live_connected": True}
        self.calls = []
        self.journaled = []
        self.service = SERVER.MAINTENANCE.Maintenance(SimpleNamespace(peek=lambda **kwargs: self.snapshot), self.commands, self.config, self.root / "data/maintenance")

    def tearDown(self):
        self.directory.cleanup()

    def commands(self, commands):
        result = []
        for command in commands:
            self.calls.append(copy.deepcopy(command))
            if command["type"] == "config/entity_registry/list":
                result.append(copy.deepcopy(self.registry))
            elif command["type"] == "get_states":
                result.append(copy.deepcopy(self.states))
            elif command["type"] == "config/entity_registry/remove":
                self.assertTrue(self.journaled, "Journal must exist before deletion")
                self.registry = [item for item in self.registry if item["entity_id"] != command["entity_id"]]
                result.append(None)
            else:
                self.fail("Unexpected command: " + command["type"])
        return result

    def unused(self):
        return [entry["entity_id"] for entry in self.service.find_unused_helpers()]

    def test_unused_app_helper_is_removed_after_journaling(self):
        removed = self.service.remove_unused_helpers(self.journaled.extend)
        self.assertEqual(removed, ["input_select.fht_old"])
        self.assertEqual(self.journaled[0]["unique_id"], "fht_old_helper")
        self.assertEqual(self.registry, [])
        self.assertEqual(self.service.remove_unused_helpers(self.journaled.extend), [])

    def test_only_unavailable_restored_app_helpers_qualify(self):
        self.registry.extend([
            {"entity_id": "input_boolean.fht_live", "unique_id": "fht_live_helper", "platform": "input_boolean"},
            {"entity_id": "input_boolean.guest_mode", "unique_id": "guest_mode_x", "platform": "input_boolean"},
            {"entity_id": "input_number.fht_device", "unique_id": "fht_device_helper", "platform": "input_number", "device_id": "dev"},
            {"entity_id": "input_text.fht_short", "unique_id": "fht", "platform": "input_text"},
            {"entity_id": "sensor.fht_temperature", "unique_id": "fht_temperature", "platform": "template"},
        ])
        self.states.extend([
            {"entity_id": "input_boolean.fht_live", "state": "on", "attributes": {}},
            {"entity_id": "input_boolean.guest_mode", "state": "unavailable", "attributes": {"restored": True}},
            {"entity_id": "input_number.fht_device", "state": "unavailable", "attributes": {"restored": True}},
            {"entity_id": "input_text.fht_short", "state": "unavailable", "attributes": {"restored": True}},
            {"entity_id": "sensor.fht_temperature", "state": "unavailable", "attributes": {"restored": True}},
        ])
        self.assertEqual(self.unused(), ["input_select.fht_old"])

    def test_helpers_an_earlier_safe_cleanup_archived_are_removed(self):
        self.registry[0].update(disabled_by="user", hidden_by="user")
        self.states.clear()
        self.assertEqual(self.unused(), [])
        self.service.data.mkdir(parents=True)
        (self.service.data / "20260920T101010-0123456789abcdef.json").write_text(json.dumps({
            "status": "archived",
            "records": [{"entity_id": "input_select.fht_old", "unique_id": "fht_old_helper"}],
        }))
        self.assertEqual(self.unused(), ["input_select.fht_old"])
        self.registry[0]["unique_id"] = "fht_replacement"
        self.assertEqual(self.unused(), [])

    def test_current_references_and_devices_are_protected(self):
        folder = self.config / "automations/rooms"
        folder.mkdir(parents=True)
        path = folder / "pantry.yml"
        path.write_text("entity_id: input_select.fht_old\n")
        self.assertEqual(self.unused(), [])
        path.unlink()
        self.registry[0]["device_id"] = "physical"
        self.assertEqual(self.unused(), [])

    def test_app_settings_protect_helpers(self):
        (self.root / "data/room_modes.json").parent.mkdir(parents=True, exist_ok=True)
        (self.root / "data/room_modes.json").write_text('{"helper": "input_select.fht_old"}')
        self.assertEqual(self.unused(), [])

    def test_explicit_nested_includes_are_scanned(self):
        (self.config / "configuration.yaml").write_text("automation: !include custom_components/rules.inc\n")
        directory = self.config / "custom_components"
        directory.mkdir()
        (directory / "rules.inc").write_text("nested: !include second.inc\n")
        (directory / "second.inc").write_text("entity_id: input_select.fht_old\nloop: !include rules.inc\n")
        self.assertEqual(self.unused(), [])

    def test_everyday_configuration_scans_cleanly(self):
        """Commented-out and missing includes, and ESPHome files, do not block cleanup."""
        (self.config / "configuration.yaml").write_text(
            "default_config:\n"
            "# themes: !include_dir_merge_named themes\n"
            "frontend:\n  themes: !include_dir_merge_named themes  # not created yet\n"
            "scene: !include scenes.yaml\n"
            "script: !include scripts.yaml\n"
            "homeassistant:\n  packages: !include_dir_named packages\n")
        (self.config / "scripts.yaml").write_text("{}\n")
        backups = self.config / "packages/.fht-backups/future_homes_tech_bedroom_mode_automations.yaml"
        backups.mkdir(parents=True)
        (backups / "20260927.yaml").write_text("entity_id: input_select.fht_old\n")
        (self.config / "packages/fht.yaml").write_text("{}\n")
        esphome = self.config / "esphome"
        esphome.mkdir()
        (esphome / "desk.yaml").write_text("packages:\n  base: !include ../../shared/base.yaml\n")
        self.assertEqual(self.unused(), ["input_select.fht_old"])

    def test_blocking_errors_name_the_source_and_delete_nothing(self):
        (self.config / "configuration.yaml").write_text("automation: !include /not-mounted/test.yaml\n")
        with self.assertRaisesRegex(SERVER.MAINTENANCE.MaintenanceError, "configuration.yaml includes /not-mounted/test.yaml"):
            self.service.remove_unused_helpers(self.journaled.extend)
        self.assertFalse(any(command["type"].endswith("remove") for command in self.calls))

    def test_missing_malformed_or_linked_sources_fail_closed(self):
        path = self.config / ".storage"
        path.mkdir()
        (path / "lovelace").write_text("bad json")
        with self.assertRaises(ValueError):
            self.service.find_unused_helpers()
        (path / "lovelace").unlink()
        (self.config / "configuration.yaml").unlink()
        with self.assertRaises(SERVER.MAINTENANCE.MaintenanceError):
            self.service.find_unused_helpers()
