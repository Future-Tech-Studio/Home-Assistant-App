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
            elif command["type"] == "trace/list":
                result.append([{"run_id": "run", "state": "stopped", "script_execution": "finished", "variables": {"pin": "123456"}}])
            else:
                self.fail("Unexpected command: " + command["type"])
        return result

    def archive(self):
        return self.service.archive({"confirmed": True, "external_reviewed": True, "entities": ["input_select.fht_old"], "revision": self.service.review()["revision"]}, {"id": "admin"})

    def test_health_uses_cache_and_does_not_assume_sleeping_means_offline(self):
        self.snapshot["entities"] = [
            {"entity_id": "sensor.battery", "state": "9", "device_class": "battery", "device_id": "device", "device_name": "Bedroom button", "battery_type": "AAA", "last_updated": "2000-01-01T00:00:00Z"},
            {"entity_id": "event.button", "state": "2000-01-01", "device_id": "device"},
        ]
        result = self.service.health()["items"][0]
        self.assertEqual(result["status"], "Reporting")
        self.assertEqual(result["batteries"][0]["percent"], 9)
        self.assertTrue(result["attention"])
        self.assertEqual(self.calls, [])
        self.service.battery_assignments = lambda: {"sensor.battery": "CR2032"}
        self.assertEqual(self.service.health()["items"][0]["batteries"][0]["type"], "CR2032")

    def test_health_offline_recovery_and_update_warning(self):
        entity = {"entity_id": "light.bulb", "state": "unavailable", "device_id": "bulb", "last_changed": "2026-09-10T00:00:00Z"}
        self.snapshot["entities"] = [entity, {"entity_id": "update.bulb", "state": "on", "device_id": "bulb", "in_progress": True, "last_updated": "2000-01-01T00:00:00Z"}]
        item = self.service.health()["items"][0]
        self.assertEqual(item["status"], "Partially unavailable")
        self.assertEqual(item["entities"][0]["offline_since"], entity["last_changed"])
        self.assertTrue(item["updates"][0]["possibly_stalled"])
        recovered = {**entity, "state": "off"}
        self.service.observe(entity, recovered)
        self.assertIsNotNone(self.service.health()["items"][0]["entities"][0]["last_recovered"])
        self.assertEqual(self.service.health()["items"][0]["availability_history"][0]["status"], "Recovered")

    def test_timeline_context_evidence_redaction_and_bounds(self):
        self.service.observe(None, {"entity_id": "light.pantry", "state": "on", "context_parent_id": "cause"})
        self.service.observe(None, {"entity_id": "automation.pantry", "state": "on", "friendly_name": "Pantry door", "context_id": "cause"})
        self.service.observe(None, {"entity_id": "input_text.fht_pin", "state": "123456"})
        self.service.observe(None, {"entity_id": "input_select.fht_secret", "state": "123456"})
        self.assertEqual(self.service.timeline("light.pantry")["items"][0]["source"], "Pantry door")
        self.assertNotIn("123456", json.dumps(self.service.timeline()))
        self.assertEqual(self.service.timeline("fht_secret")["items"][0]["source"], "Source unavailable")
        for index in range(2100):
            self.service.observe(None, {"entity_id": "light.pantry", "state": "on", "brightness": index})
        self.assertEqual(len(self.service.events), 2000)
        page = self.service.timeline()
        self.assertEqual(len(page["items"]), 100)
        self.assertLess(self.service.timeline(before=page["next_before"])["items"][0]["id"], page["next_before"])

    def test_trace_summaries_use_registry_identity_and_omit_variables(self):
        self.registry.append({"entity_id": "automation.pantry", "unique_id": "pantry_automation"})
        result = self.service.traces("automation.pantry")
        self.assertNotIn("123456", json.dumps(result))
        self.assertEqual(self.calls[-1]["item_id"], "pantry_automation")
        with self.assertRaises(SERVER.MAINTENANCE.MaintenanceError):
            self.service.traces("light.pantry")

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

    def test_normalization_tolerates_bad_context(self):
        self.assertIsNone(SERVER.normalize_entities([{"entity_id": "light.test", "context": "bad"}])[0]["context_id"])
