"""Tests for the saved settings history and "Undo last change"."""

from __future__ import annotations

import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from test_server import SERVER

HISTORY = SERVER.HISTORY


class SettingsHistoryTests(unittest.TestCase):
    """Keep the version every settings write replaces, and put one back."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.data = Path(self.temporary.name)
        self.history = HISTORY.SettingsHistory([self.data], limit=3)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def versions(self, name: str) -> list[Path]:
        return sorted((self.data / "history" / name).glob("*.json"))

    def test_records_the_replaced_content_and_keeps_the_newest_versions(self) -> None:
        store = self.data / "room_modes.json"
        self.assertIsNotNone(self.history.record(store, None))
        for revision in range(4):
            self.history.record(store, json.dumps({"revision": revision}))
        kept = self.versions("room_modes.json")
        self.assertEqual(len(kept), 3, "Only the newest versions stay")
        self.assertEqual(
            [json.loads(path.read_text())["revision"] for path in kept], [1, 2, 3]
        )
        self.assertTrue(all(HISTORY.TIMESTAMP_PATTERN.fullmatch(path.stem) for path in kept))

    def test_ignores_files_that_are_not_settings_stores(self) -> None:
        self.assertIsNone(self.history.record(self.data / "cleanup_pending.json", "{}"))
        self.assertIsNone(self.history.record(self.data / "package.yaml", "a: 1"))
        self.assertIsNone(self.history.record(self.data / "maintenance" / "log.json", "{}"))
        self.assertIsNone(self.history.record(Path("/elsewhere") / "room_modes.json", "{}"))
        self.assertFalse((self.data / "history").exists())

    def test_atomic_writes_keep_history_through_the_shared_hook(self) -> None:
        store = self.data / "room_aliases.json"
        with patch.object(SERVER, "SETTINGS_HISTORY", self.history):
            SERVER.atomic_write_json(store, {"Bedroom 1": "Nursery"})
            SERVER.atomic_write_json(store, {"Bedroom 1": "Nursery"})
            SERVER.atomic_write_json(store, {"Bedroom 1": "Nursery", "Bedroom 2": "Den"})
            SERVER.atomic_write_text(store, "{}\n", retain_previous=False)
        kept = self.versions("room_aliases.json")
        self.assertEqual([path.read_text() for path in kept][0], "", "The first write records that the store did not exist")
        self.assertEqual(json.loads(kept[1].read_text()), {"Bedroom 1": "Nursery"})
        self.assertEqual(len(kept), 2, "Unchanged content and untracked writes add nothing")

    def test_entries_describe_each_change_newest_first(self) -> None:
        store = self.data / "presence_light_group_timings.json"
        self.history.record(store, json.dumps({"Kitchen": {"delay": 5}, "Hall": {"delay": 2}}))
        self.history.record(store, json.dumps({"Kitchen": {"delay": 9}, "Hall": {"delay": 2}}))
        store.write_text(json.dumps({"Kitchen": {"delay": 9}}))
        entries = self.history.entries("presence_light_group_timings.json", store)
        self.assertEqual([entry["summary"] for entry in entries], ["Removed Hall", "Changed Kitchen › delay"])
        self.assertEqual(entries[0]["label"], "Presence delays")
        self.assertEqual(entries[0]["store"], "presence_light_group_timings.json")
        self.assertTrue(entries[0]["saved_at"].endswith("+00:00"))
        self.assertGreater(entries[0]["timestamp"], entries[1]["timestamp"])

    def test_summaries_cover_lists_and_many_changes(self) -> None:
        self.assertEqual(
            HISTORY.describe_change(["light.fht_a"], ["light.fht_a", "light.fht_b"]),
            "Added light.fht_b",
        )
        self.assertEqual(
            HISTORY.describe_change({str(n): n for n in range(5)}, {}),
            "Removed 0, Removed 1, Removed 2 and 2 more",
        )
        self.assertEqual(HISTORY.describe_change({"a": 1}, {"a": 1}), "")
        self.assertEqual(HISTORY.describe_change(None, {"a": 1}), "Changed settings")

    def test_page_entries_merge_the_stores_a_page_owns(self) -> None:
        paths = {
            "light_schedules.json": self.data / "light_schedules.json",
            "room_scenes.json": self.data / "room_scenes.json",
            "room_modes.json": self.data / "room_modes.json",
        }
        self.history.record(paths["room_scenes.json"], "{}")
        self.history.record(paths["light_schedules.json"], "{}")
        self.history.record(paths["room_modes.json"], "{}")
        self.history.record(paths["light_schedules.json"], '{"a": 1}')
        paths["room_aliases.json"] = self.data / "room_aliases.json"
        self.history.record(paths["room_aliases.json"], "{}")
        entries = self.history.page_entries("rooms", paths)
        self.assertEqual(
            [entry["store"] for entry in entries],
            ["room_aliases.json", "light_schedules.json", "light_schedules.json"],
        )
        self.assertEqual([entry["store"] for entry in self.history.page_entries("scenes", paths)], ["room_scenes.json"])
        with self.assertRaisesRegex(ValueError, "settings page"):
            self.history.page_entries("dashboard", paths)
        with self.assertRaisesRegex(ValueError, "does not belong"):
            self.history.page_store_path("scenes", "room_modes.json", paths)

    def test_door_left_open_reminders_can_be_reverted_from_the_alarm_page(self) -> None:
        self.assertIn("door_open_alert_settings.json", HISTORY.page_stores("alarm"))
        self.assertEqual(HISTORY.STORE_PAGE["door_open_alert_settings.json"], "alarm")
        self.assertEqual(HISTORY.STORE_LABELS["door_open_alert_settings.json"], "Door Left Open reminders")

    def test_all_entries_merge_every_store_with_its_page(self) -> None:
        paths = {"room_modes.json": self.data / "room_modes.json", "switch_control_settings.json": self.data / "switch_control_settings.json"}
        self.history.record(paths["room_modes.json"], "{}")
        self.history.record(paths["switch_control_settings.json"], "{}")
        entries = self.history.all_entries(paths)
        self.assertEqual([entry["page"] for entry in entries], ["switches", "room-modes"])
        self.assertEqual(entries[0]["page_label"], "Switches, Doors and Buttons")
        self.assertEqual(entries[1]["label"], "Room modes")

    def test_restore_writes_the_version_back_and_can_itself_be_undone(self) -> None:
        store = self.data / "room_modes.json"
        self.history = HISTORY.SettingsHistory([self.data], limit=10)
        with patch.object(SERVER, "SETTINGS_HISTORY", self.history):
            SERVER.atomic_write_json(store, {"Bedroom 2": ["sleep"]})
            SERVER.atomic_write_json(store, {"Bedroom 2": []})
            before = self.history.entries("room_modes.json", store)[0]
            self.assertTrue(self.history.restore(store, before["timestamp"], SERVER.atomic_write_text))
            self.assertEqual(json.loads(store.read_text()), {"Bedroom 2": ["sleep"]})
            latest = self.history.entries("room_modes.json", store)[0]
            self.assertEqual(latest["summary"], "Added Bedroom 2 › sleep")
            self.assertTrue(self.history.restore(store, latest["timestamp"], SERVER.atomic_write_text))
            self.assertEqual(json.loads(store.read_text()), {"Bedroom 2": []})
            # The oldest version marks that the store did not exist: undoing to it removes the file.
            oldest = self.history.entries("room_modes.json", store)[-1]
            self.assertTrue(self.history.restore(store, oldest["timestamp"], SERVER.atomic_write_text))
            self.assertFalse(store.exists())
            self.assertFalse(self.history.restore(store, oldest["timestamp"], SERVER.atomic_write_text))

    def test_restore_rejects_unknown_or_unsafe_versions(self) -> None:
        store = self.data / "room_modes.json"
        self.history.record(store, "{}")
        writer = Mock()
        for timestamp in ("", "../../room_modes", "20261003T140200000000Z"):
            with self.assertRaises(ValueError):
                self.history.restore(store, timestamp, writer)
        writer.assert_not_called()


class SettingsHistoryRoutesTests(unittest.TestCase):
    """Serve the history to a page and put a version back on request."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.data = Path(self.temporary.name)
        self.history = HISTORY.SettingsHistory([self.data])
        self.history_patch = patch.object(SERVER, "SETTINGS_HISTORY", self.history)
        self.history_patch.start()
        self.addCleanup(self.history_patch.stop)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def handler(self, path: str, body: dict | None = None) -> SERVER.FutureHomesTechRequestHandler:
        handler = object.__new__(SERVER.FutureHomesTechRequestHandler)
        handler.path = path
        handler._request_is_allowed = Mock(return_value=True)
        handler.headers = {}
        handler.wfile = io.BytesIO()
        handler.send_response = Mock()
        handler.send_header = Mock()
        handler.end_headers = Mock()
        handler.client_address = ("172.30.32.2", 1)
        if body is not None:
            raw = json.dumps(body).encode("utf-8")
            handler.headers = {"Content-Length": str(len(raw))}
            handler.rfile = io.BytesIO(raw)
        store = lambda name: SimpleNamespace(_path=self.data / name)  # noqa: E731
        handler.switch_control_settings = store("switch_control_settings.json")
        handler.presence_assignments = store("presence_light_group_assignments.json")
        handler.presence_timings = store("presence_light_group_timings.json")
        handler.presence_mode_settings = store("presence_mode_settings.json")
        handler.room_modes = store("room_modes.json")
        handler.light_schedules = store("light_schedules.json")
        handler.room_scenes = store("room_scenes.json")
        handler.fridge_alarm_settings = store("fridge_alarm_settings.json")
        handler.door_open_alert_settings = store("door_open_alert_settings.json")
        handler.room_aliases = store("room_aliases.json")
        handler.future_tech_portal = SimpleNamespace(settings=store("future_tech_portal_settings.json"))
        handler.homekit_light_groups = SERVER.HomeKitLightGroupSelection(
            self.data / "homekit_light_groups.json",
            self.data / "homekit_climate_entities.json",
            self.data / "packages" / "future_homes_tech_homekit.yaml",
            self.data / "homekit_security_entities.json",
        )
        handler.configuration_publisher = Mock()
        handler.registry_organizer = Mock()
        handler.inventory = Mock()
        handler.inventory.fetch.return_value = {
            "entities": [{"entity_id": "light.fht_kitchen_all_lights", "friendly_name": "Kitchen All Lights"}]
        }
        return handler

    @staticmethod
    def response(handler: SERVER.FutureHomesTechRequestHandler) -> tuple[int, dict]:
        return handler.send_response.call_args.args[0], json.loads(handler.wfile.getvalue())

    def test_history_route_lists_the_pages_stores(self) -> None:
        store = self.data / "presence_mode_settings.json"
        SERVER.atomic_write_json(store, {"Kitchen": {"day": 50}})
        SERVER.atomic_write_json(store, {"Kitchen": {"day": 80}})
        handler = self.handler("/api/settings/history?page=presence")
        handler.do_GET()
        status, payload = self.response(handler)
        self.assertEqual(status, 200)
        self.assertEqual(payload["page"], "presence")
        self.assertEqual(payload["entries"][0]["summary"], "Changed Kitchen › day")
        self.assertEqual(payload["entries"][0]["store"], "presence_mode_settings.json")
        self.assertEqual(len(payload["entries"]), 2)

        handler = self.handler("/api/settings/history")
        handler.do_GET()
        status, payload = self.response(handler)
        self.assertEqual(status, 200)
        self.assertEqual(payload["entries"][0]["page"], "presence")
        self.assertEqual(len(payload["entries"]), 2)

        handler = self.handler("/api/settings/history?page=lighting")
        handler.do_GET()
        status, payload = self.response(handler)
        self.assertEqual(status, 400)
        self.assertFalse(payload["ok"])

    def test_revert_route_restores_then_rebuilds_the_generated_configuration(self) -> None:
        store = self.data / "room_modes.json"
        SERVER.atomic_write_json(store, {"Bedroom 3": ["sleep"]})
        SERVER.atomic_write_json(store, {"Bedroom 3": ["sleep", "toddler"]})
        timestamp = self.history.entries("room_modes.json", store)[0]["timestamp"]
        events: list[str] = []

        class RecordingLock:
            def __enter__(self) -> None:
                events.append("lock")

            def __exit__(self, *args: object) -> None:
                events.append("unlock")

        handler = self.handler("/api/settings/revert", {"page": "room-modes", "store": "room_modes.json", "timestamp": timestamp})
        with patch.object(SERVER, "sync_generated_configuration_on_startup", side_effect=lambda *a, **k: events.append("sync")) as sync, \
                patch.object(SERVER, "CONFIGURATION_ACTIVATION_LOCK", RecordingLock()):
            handler.do_POST()
        status, payload = self.response(handler)
        self.assertEqual(status, 200, payload)
        self.assertEqual(payload["restored"], True)
        self.assertEqual(payload["activated"], True)
        self.assertEqual(json.loads(store.read_text()), {"Bedroom 3": ["sleep"]})
        self.assertEqual(events, ["lock", "sync", "unlock"], "Undo runs in the configuration lane")
        self.assertIs(sync.call_args.args[0], SERVER.FutureHomesTechRequestHandler)
        self.assertEqual(sync.call_args.kwargs, {"attempts": 1, "raise_errors": True})
        self.assertEqual(payload["entries"][0]["summary"], "Removed Bedroom 3 › toddler")

    def test_revert_route_reports_a_restore_whose_activation_failed(self) -> None:
        store = self.data / "light_schedules.json"
        SERVER.atomic_write_json(store, {"light.a": {"enabled": True}})
        SERVER.atomic_write_json(store, {"light.a": {"enabled": False}})
        timestamp = self.history.entries("light_schedules.json", store)[0]["timestamp"]
        handler = self.handler("/api/settings/revert", {"page": "rooms", "store": "light_schedules.json", "timestamp": timestamp})
        with patch.object(SERVER, "sync_generated_configuration_on_startup", side_effect=SERVER.HomeAssistantAPIError("Home Assistant is restarting.")):
            handler.do_POST()
        status, payload = self.response(handler)
        self.assertEqual(status, 502)
        self.assertEqual(payload, {"ok": False, "saved": True, "activated": False, "error": "Home Assistant is restarting."})
        self.assertEqual(json.loads(store.read_text()), {"light.a": {"enabled": True}})

    def test_portal_configurator_reverts_the_portal_reporting_settings(self) -> None:
        store = self.data / "future_tech_portal_settings.json"
        SERVER.atomic_write_json(store, {"enabled": True, "integrations": ["zha"]})
        SERVER.atomic_write_json(store, {"enabled": False, "integrations": ["zha"]})
        entries = self.history.page_entries("portal", self.handler("/")._settings_store_paths())
        self.assertEqual([entry["label"] for entry in entries][:1], ["Portal reporting"])
        self.assertTrue(entries[0]["summary"].startswith("Changed enabled"))
        self.assertEqual(HISTORY.PAGE_LABELS["portal"], "Portal Configurator")
        handler = self.handler("/api/settings/revert", {"page": "portal", "store": "future_tech_portal_settings.json", "timestamp": entries[0]["timestamp"]})
        with patch.object(SERVER, "sync_generated_configuration_on_startup") as sync:
            handler.do_POST()
        status, payload = self.response(handler)
        self.assertEqual(status, 200, payload)
        sync.assert_called_once()
        self.assertEqual(json.loads(store.read_text()), {"enabled": True, "integrations": ["zha"]})

    def test_revert_route_refuses_a_store_the_page_does_not_own(self) -> None:
        store = self.data / "room_modes.json"
        SERVER.atomic_write_json(store, {"Bedroom 3": ["sleep"]})
        SERVER.atomic_write_json(store, {})
        timestamp = self.history.entries("room_modes.json", store)[0]["timestamp"]
        handler = self.handler("/api/settings/revert", {"page": "doors", "store": "room_modes.json", "timestamp": timestamp})
        with patch.object(SERVER, "sync_generated_configuration_on_startup") as sync:
            handler.do_POST()
        status, payload = self.response(handler)
        self.assertEqual(status, 400)
        self.assertEqual(payload["saved"], False)
        sync.assert_not_called()
        self.assertEqual(json.loads(store.read_text()), {})

    def test_revert_route_rebuilds_the_homekit_package_and_asks_for_a_restart(self) -> None:
        handler = self.handler("/api/settings/revert")
        selection = handler.homekit_light_groups
        names = {"light.fht_kitchen_all_lights": "Kitchen All Lights"}
        selection.save("light.fht_kitchen_all_lights", True, names)
        selection.save("light.fht_kitchen_all_lights", False, names)
        self.assertNotIn("light.fht_kitchen_all_lights", selection._package_path.read_text())
        timestamp = self.history.entries("homekit_light_groups.json", selection._path)[0]["timestamp"]
        handler = self.handler("/api/settings/revert", {"page": "homekit", "store": "homekit_light_groups.json", "timestamp": timestamp})
        with patch.object(SERVER, "sync_generated_configuration_on_startup"):
            handler.do_POST()
        status, payload = self.response(handler)
        self.assertEqual(status, 200, payload)
        self.assertEqual(payload["activation_required"], "home_assistant_restart")
        self.assertEqual(selection.read(), ["light.fht_kitchen_all_lights"])
        self.assertIn('"light.fht_kitchen_all_lights"', selection._package_path.read_text())

    def test_revert_is_a_serialized_configuration_mutation(self) -> None:
        self.assertIn("/api/settings/revert", SERVER.CONFIGURATION_MUTATION_PATHS)

    def test_startup_sync_can_raise_instead_of_logging(self) -> None:
        handler = Mock()
        handler.presence_groups.discover.side_effect = SERVER.HomeAssistantAPIError("offline")
        with self.assertRaisesRegex(SERVER.HomeAssistantAPIError, "offline"):
            SERVER.sync_generated_configuration_on_startup(handler, Mock(), Mock(), attempts=1, raise_errors=True)
        with patch("builtins.print") as printed:
            SERVER.sync_generated_configuration_on_startup(handler, Mock(), Mock(), attempts=1)
        self.assertIn("ERROR offline", printed.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
