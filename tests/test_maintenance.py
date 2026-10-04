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
        self.fail_write = False
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
            elif command["type"] == "config/entity_registry/update":
                self.assertTrue(list(self.service.data.glob("*.json")), "Journal must exist before mutation")
                if self.fail_write:
                    raise RuntimeError("fixture failure")
                entry = next(item for item in self.registry if item["entity_id"] == command["entity_id"])
                entry.update({key: command[key] for key in ("disabled_by", "hidden_by")})
                result.append(copy.deepcopy(entry))
            else:
                self.fail("Unexpected command: " + command["type"])
        return result

    def archive(self):
        return self.service.archive({"confirmed": True, "external_reviewed": True, "entities": ["input_select.fht_old"], "revision": self.service.review()["revision"]}, {"id": "admin"})

    def test_review_never_mutates_and_reports_duplicate_members(self):
        self.states.extend([{"entity_id": entity_id, "attributes": {"entity_id": ["light.one", "light.two"]}} for entity_id in ("light.group1", "light.group2")])
        result = self.service.review()
        self.assertTrue(result["items"][0]["eligible"])
        self.assertEqual(len(result["duplicates"]), 1)
        self.assertFalse(any(item["type"].endswith("update") for item in self.calls))

    def test_review_lists_leftover_entities_not_made_by_the_app(self):
        self.registry.extend([
            {"entity_id": "sensor.old_weather", "unique_id": "abc-1", "platform": "openweathermap", "device_id": "dev"},
            {"entity_id": "switch.working", "unique_id": "abc-2", "platform": "zwave_js"},
            {"entity_id": "light.never_loaded", "unique_id": "abc-3", "platform": "hue"},
            {"entity_id": "light.disabled", "unique_id": "abc-4", "platform": "hue", "disabled_by": "user"},
            {"entity_id": "light.bedroom_6_desk_lights", "unique_id": "fht_bedroom_6_desk_lights", "platform": "group"},
            {"entity_id": "light.bedroom_4_all_lights", "unique_id": "bedroom_4_all_lights", "platform": "group"},
        ])
        self.states.extend([
            {"entity_id": "sensor.old_weather", "state": "unavailable", "attributes": {"restored": True, "friendly_name": "Old Weather"}},
            {"entity_id": "switch.working", "state": "on", "attributes": {}},
            {"entity_id": "light.bedroom_6_desk_lights", "state": "unavailable", "attributes": {"restored": True}},
            {"entity_id": "light.bedroom_4_all_lights", "state": "unavailable", "attributes": {"restored": True}},
        ])
        result = self.service.review()
        self.assertEqual([item["id"] for item in result["leftovers"]], ["light.never_loaded", "sensor.old_weather"])
        self.assertEqual(result["leftovers"][1], {"id": "sensor.old_weather", "name": "Old Weather",
                                                   "integration": "openweathermap", "device_linked": True})
        self.assertFalse(any(item["type"].endswith(("update", "remove")) for item in self.calls))

    def test_current_references_and_devices_are_protected(self):
        folder = self.config / "automations/rooms"
        folder.mkdir(parents=True)
        path = folder / "pantry.yml"
        path.write_text("entity_id: input_select.fht_old\n")
        result = self.service.review()["items"][0]
        self.assertFalse(result["eligible"])
        self.assertIn("automations/rooms/pantry.yml", result["references"])
        path.unlink()
        self.registry[0]["device_id"] = "physical"
        self.assertFalse(self.service.review()["items"][0]["eligible"])

    def test_explicit_nested_includes_are_scanned(self):
        (self.config / "configuration.yaml").write_text("automation: !include custom_components/rules.inc\n")
        directory = self.config / "custom_components"
        directory.mkdir()
        (directory / "rules.inc").write_text("nested: !include second.inc\n")
        (directory / "second.inc").write_text("entity_id: input_select.fht_old\nloop: !include rules.inc\n")
        result = self.service.review()["items"][0]
        self.assertFalse(result["eligible"])
        self.assertIn("custom_components/second.inc", result["references"])

    def test_everyday_configuration_scans_cleanly(self):
        """Commented-out and missing includes, and ESPHome files, do not block review."""
        (self.config / "configuration.yaml").write_text(
            "default_config:\n"
            "# themes: !include_dir_merge_named themes\n"
            "frontend:\n  themes: !include_dir_merge_named themes  # not created yet\n"
            "scene: !include scenes.yaml\n"
            "script: !include scripts.yaml\n")
        (self.config / "scripts.yaml").write_text("{}\n")
        (self.config / "configuration.yaml").write_text(
            (self.config / "configuration.yaml").read_text()
            + "homeassistant:\n  packages: !include_dir_named packages\n")
        backups = self.config / "packages/.fht-backups/future_homes_tech_bedroom_mode_automations.yaml"
        backups.mkdir(parents=True)
        (backups / "20260927.yaml").write_text("entity_id: input_select.fht_old\n")
        (self.config / "packages/fht.yaml").write_text("{}\n")
        esphome = self.config / "esphome"
        esphome.mkdir()
        (esphome / "desk.yaml").write_text("packages:\n  base: !include ../../shared/base.yaml\n")
        result = self.service.review()
        self.assertTrue(result["items"][0]["eligible"])

    def test_blocking_errors_name_the_source(self):
        (self.config / "configuration.yaml").write_text("automation: !include /not-mounted/test.yaml\n")
        with self.assertRaisesRegex(SERVER.MAINTENANCE.MaintenanceError, "configuration.yaml includes /not-mounted/test.yaml"):
            self.service.review()

    def test_missing_malformed_or_linked_sources_fail_closed(self):
        path = self.config / ".storage"
        path.mkdir()
        (path / "lovelace").write_text("bad json")
        with self.assertRaises(ValueError):
            self.service.review()
        (path / "lovelace").unlink()
        (self.config / "configuration.yaml").write_text("automation: !include /not-mounted/test.yaml\n")
        with self.assertRaises(SERVER.MAINTENANCE.MaintenanceError):
            self.service.review()
        (self.config / "configuration.yaml").unlink()
        with self.assertRaises(SERVER.MAINTENANCE.MaintenanceError):
            self.service.review()

    def test_archive_requires_confirmation_and_fresh_revision(self):
        for payload in ({}, {"confirmed": True}, {"confirmed": True, "external_reviewed": True, "entities": ["input_select.fht_old"], "revision": "old"}):
            with self.assertRaises(SERVER.MAINTENANCE.MaintenanceError):
                self.service.archive(payload, {})
        self.assertFalse(self.service.data.exists())

    def test_archive_restore_permissions_and_idempotent_recovery(self):
        result = self.archive()
        self.assertEqual(self.registry[0]["disabled_by"], "user")
        journal = self.service.data / (result["archive_id"] + ".json")
        self.assertEqual(journal.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.service.data.stat().st_mode & 0o777, 0o700)
        payload = {"archive_id": result["archive_id"], "confirmed": True}
        self.service.restore(payload)
        self.assertIsNone(self.registry[0]["disabled_by"])
        self.assertTrue(self.service.restore(payload)["already_restored"])
        self.assertFalse(any(command["type"].endswith("remove") for command in self.calls))

    def test_partial_archive_has_recoverable_journal(self):
        self.fail_write = True
        with self.assertRaises(SERVER.MAINTENANCE.MaintenanceError):
            self.archive()
        history = self.service.archives()["items"][0]
        self.assertEqual(history["status"], "partial-review-required")
        self.fail_write = False
        self.service.restore({"archive_id": history["id"], "confirmed": True})
        self.assertIsNone(self.registry[0]["disabled_by"])

    def test_changed_identity_blocks_restore(self):
        result = self.archive()
        self.registry[0]["unique_id"] = "replacement"
        with self.assertRaises(SERVER.MAINTENANCE.MaintenanceError):
            self.service.restore({"archive_id": result["archive_id"], "confirmed": True})

    def test_partial_restore_is_recorded(self):
        result = self.archive()
        self.fail_write = True
        with self.assertRaises(SERVER.MAINTENANCE.MaintenanceError):
            self.service.restore({"archive_id": result["archive_id"], "confirmed": True})
        self.assertEqual(self.service.archives()["items"][0]["status"], "partial-restore-review-required")
