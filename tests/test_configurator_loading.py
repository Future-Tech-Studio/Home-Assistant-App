"""Regressions for shared catalogs and non-blocking room navigation."""

import importlib.util
import json
import tempfile
from pathlib import Path
import threading
import unittest
from unittest.mock import Mock, patch

SPEC = importlib.util.spec_from_file_location("loading_server", Path(__file__).resolve().parents[1] / "future_homes_tech_app/server.py")
SERVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SERVER)


class ConfiguratorLoadingTests(unittest.TestCase):
    def test_bedroom_closet_ignores_global_sleep(self):
        door = "binary_sensor.bedroom_2_closet_door"
        entities = [{"entity_id": door, "friendly_name": "Closet Door", "area": "Bedroom 2"}, {"entity_id": "light.closet"}]
        modes = ["sleep", "floor:second", "room:bedroom_2:sleep", "day", "night", "room:bedroom_2:chill"]
        assignments = {f"door:{door}|{mode}": ["light_group:light.closet"] for mode in modes}
        automations = SERVER.ControlAutomationManager.describe({}, entities, action_assignments=assignments)
        self.assertEqual({item["house_mode"] for item in automations}, set(modes) - {"sleep", "floor:second"})
        manager = SERVER.ControlAutomationManager(Path("/tmp/closet-controls.yaml"))
        day = next(item for item in automations if item["house_mode"] == "day")
        condition = "".join(manager._door_condition_lines(day, automations))
        self.assertNotIn(SERVER.HOUSE_MODE_HELPER, condition)
        self.assertIn("after: sunrise", condition)
        self.assertIn("before: sunset", condition)
        self.assertIn("input_select.fht_bedroom_2_mode", condition)
        self.assertIn("not (", condition)

    def test_door_card_timeout_and_atomic_save(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = SERVER.SwitchControlSettings(root / "settings.json")
            key = "door:binary_sensor.door"
            saved = store.save_door_card(key, ["light_group:light.one"], {"day": {"enabled": True, "brightness_pct": 30}, "night": {"enabled": False}}, 5)
            before = (root / "settings.json").read_bytes()
            with self.assertRaises(ValueError):
                store.save_door_card(key, ["light_group:light.one"], {"day": {}}, -1)
            self.assertEqual((root / "settings.json").read_bytes(), before)
            self.assertEqual(store.read()["action_settings"][key + "|day"]["timeout_minutes"], 5)
            SERVER.ControlAutomationManager(root / "controls.yaml").sync({}, [{"entity_id": "binary_sensor.door"}, {"entity_id": "light.one"}], action_assignments=saved["action_assignments"], action_settings=saved["action_settings"], reload_automations=False)
            output = (root / "controls.yaml").read_text()
            self.assertIn("minutes: 5", output)
            self.assertIn("mode: restart", output)
            self.assertIn("id: turn_off", output)
            self.assertLess(output.index("action: light.turn_on"), output.index("minutes: 5"))
            self.assertLess(output.index("minutes: 5"), output.index("action: light.turn_off"))

    def test_quiet_mode_is_persistent_local_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "modes.json"
            settings = SERVER.RoomModeSettings(path)
            settings.save("Bedroom 1", ["sleep", "quiet"], scope="room")
            self.assertEqual(SERVER.RoomModeSettings(path).read()["Bedroom 1"], ["quiet", "sleep"])
        template = SERVER.ControlAutomationManager(Path("/tmp/controls.yaml"))._door_mode_template("room:bedroom_1:quiet")
        self.assertIn("'quiet'", template)
        self.assertNotIn(SERVER.HOUSE_MODE_HELPER, template)
        floor = SERVER.BedroomModeAutomationManager.floor_sleep_templates({"first": {"name": "First Floor", "sources": ["input_select.fht_bedroom_1_mode"]}})
        self.assertIn("'eq', 'Sleep'", floor[0]["state"])
        self.assertNotIn("Quiet", floor[0]["state"])
        self.assertIn("quiet", SERVER.PresenceModeSettings.normalize({"quiet": {"enabled": True, "brightness": 25}}))

    def test_door_modes_include_only_current_room_and_floor(self):
        handler = self.handler()
        handler.room_modes.read.return_value = {"Bedroom 1": ["sleep", "chill"], "Bedroom 2": ["movie"]}
        with patch.object(SERVER, "home_structure_from_storage", return_value={"floors": [
            {"floor_id": "first", "name": "First Floor", "areas": [{"name": "Bedroom 1"}]},
            {"floor_id": "second", "name": "Second Floor", "areas": [{"name": "Bedroom 2"}]},
        ]}):
            options = handler._door_mode_options("Bedroom 1")
        self.assertEqual([option["id"] for option in options], ["day", "night", "sleep", "floor:first", "room:bedroom_1:sleep", "room:bedroom_1:chill"])

    def test_door_mode_keys_and_priority(self):
        manager = SERVER.ControlAutomationManager(Path("/tmp/fht-test-controls.yaml"))
        for mode in ("room:bedroom_1:chill", "floor:first", "sleep"):
            self.assertEqual(SERVER.parse_door_assignment_id("door:binary_sensor.door|" + mode), ("binary_sensor.door", mode))
        day = {"trigger_entity_id": "binary_sensor.door", "house_mode": "day"}
        chill = {**day, "house_mode": "room:bedroom_1:chill"}
        template = manager._door_activation_template(day, [day, chill])
        self.assertIn("not (", template)
        self.assertIn("input_select.fht_bedroom_1_mode", template)
        self.assertIn("chill", template)

    def test_floor_door_mode_uses_configured_sources_and_persists(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "future_homes_tech_bedroom_mode_automations.house.json").write_text(json.dumps({"floor_sleep_modes": {"first": {"sources": ["input_select.fht_bedroom_1_mode"]}}}))
            manager = SERVER.ControlAutomationManager(root / "controls.yaml")
            template = manager._door_mode_template("floor:first")
            self.assertIn("input_select.fht_bedroom_1_mode", template)
            self.assertIn("'Sleep'", template)
            settings = SERVER.SwitchControlSettings(root / "settings.json")
            assignment = "door:binary_sensor.door|floor:first"
            settings.save_actions(assignment, ["light_group:light.one"], {"enabled": True, "brightness_pct": 25})
            restored = SERVER.SwitchControlSettings(root / "settings.json").read()
            self.assertEqual(restored["action_assignments"][assignment], ["light_group:light.one"])
            self.assertEqual(restored["action_settings"][assignment]["brightness_pct"], 25)

    def handler(self):
        handler = SERVER.FutureHomesTechRequestHandler.__new__(SERVER.FutureHomesTechRequestHandler)
        handler.inventory = Mock()
        handler.inventory._config_directory = Path("/tmp/fht-nonexistent-test-config")
        handler.inventory._freshness_payload.return_value = {"revision": 1, "metadata_revision": 1}
        handler.inventory.fetch.return_value = {"entities": []}
        for name in ("bedroom_modes", "wake_routines", "switch_control_settings", "room_aliases",
                     "room_modes", "presence_assignments", "presence_timings", "presence_mode_settings",
                     "switch_assignments", "fridge_alarm_settings"):
            setattr(handler, name, Mock())
            getattr(handler, name).read.return_value = {}
        handler.room_modes.catalog.return_value = {}
        return handler

    def test_catalog_built_once_and_revalidated_on_settings_or_inventory(self):
        handler = self.handler()
        handler._shared_action_catalog = Mock(return_value={"lights": []})
        handler._wake_routine_catalog = Mock(return_value={})
        handler._toddler_entity_catalog = Mock(return_value={})
        first = handler._shared_editor_catalog()
        self.assertIs(first, handler._shared_editor_catalog())
        handler._shared_action_catalog.assert_called_once()
        handler.switch_control_settings.read.return_value = {"action_assignments": {"switch.one": ["light:light.one"]}}
        changed = handler._shared_editor_catalog()
        self.assertNotEqual(first["revision"], changed["revision"])
        handler.inventory._freshness_payload.return_value = {"revision": 2, "metadata_revision": 1}
        self.assertIs(changed, handler._shared_editor_catalog())
        handler.inventory._freshness_payload.return_value = {"revision": 3, "metadata_revision": 2}
        self.assertNotEqual(changed["revision"], handler._shared_editor_catalog()["revision"])
        self.assertEqual(handler._shared_action_catalog.call_count, 3)
        handler.room_modes.read.return_value = {"Bedroom 1": ["sleep"]}
        handler._shared_editor_catalog()
        self.assertEqual(handler._shared_action_catalog.call_count, 4)

    def test_room_does_not_wait_for_discovery_or_build_global_catalogs(self):
        handler = self.handler()
        handler.inventory.refresh_room.return_value = {"room": "Pantry", "entities": [{"entity_id": "switch.pantry", "domain": "switch"}]}
        handler.button_inventory = Mock()
        handler.button_inventory.peek.return_value = {"buttons": [], "pending": True}
        handler.switch_assignments.read.return_value = {"switch.pantry": "light.pantry", "switch.office": "light.office"}
        handler._shared_action_catalog = Mock(side_effect=AssertionError("catalog rebuilt in room"))
        handler._wake_routine_catalog = Mock(side_effect=AssertionError("wake catalog rebuilt in room"))
        result = handler._home_configurator_room("Pantry")
        handler.button_inventory.fetch.assert_not_called()
        self.assertTrue(result["buttons_pending"])
        self.assertNotIn("action_catalog", result)
        self.assertNotIn("wake_catalog", result)
        self.assertEqual(result["control_settings"]["assignments"], {"switch.pantry": "light.pantry"})

    def room_controls_handler(self):
        handler = self.handler()
        entities = [
            {"entity_id": "binary_sensor.pantry_door", "domain": "binary_sensor", "device_class": "door", "area": "Pantry", "state": "off"},
            {"entity_id": "binary_sensor.pantry_battery", "domain": "binary_sensor", "device_class": "battery", "area": "Pantry"},
            {"entity_id": "binary_sensor.bedroom_window", "domain": "binary_sensor", "device_class": "window", "area": "Bedroom 6"},
            {"entity_id": "binary_sensor.unassigned_door", "domain": "binary_sensor", "device_class": "door", "area": None},
            {"entity_id": "switch.bedroom_switch", "domain": "switch", "area": "Bedroom 6", "hidden_by": "integration", "device_name": "Bedroom 6 Switch", "device_id": "wall"},
            {"entity_id": "event.bedroom_button_up", "domain": "event", "area": "Bedroom 6", "event_types": ["press", "double_press"], "device_id": "wall"},
            {"entity_id": "fan.bedroom_floor_fan", "domain": "fan", "area": "Bedroom 6"},
            {"entity_id": "light.bedroom_load", "domain": "light", "area": "Bedroom 6"},
        ]

        def project(*, include_all, predicate, fields):
            self.assertTrue(include_all)
            selected = [entity.copy() for entity in entities if predicate(entity)]
            if fields is not None:
                selected = [{key: entity.get(key) for key in fields} for entity in selected]
            return {"entities": selected, "revision": 1}

        handler.inventory.fetch.side_effect = project
        handler.room_aliases.read.return_value = {"Bedroom 6": "Chloe's Bedroom"}
        return handler

    def test_room_controls_index_carries_every_room_from_one_projection(self):
        """The Doors index answers every room card at once: settings read once, no per-room requests."""
        handler = self.room_controls_handler()
        result = handler._room_controls("doors")
        self.assertEqual(len(result["entities"]), 3)
        self.assertEqual(result["aliases"], {"Bedroom 6": "Chloe's Bedroom"})
        self.assertTrue(result["rooms_ready"])
        self.assertEqual(set(result["door_mode_options_by_room"]), {"", "Bedroom 6", "Pantry"})
        self.assertEqual(set(result["enabled_room_modes_by_room"]), {"", "Bedroom 6", "Pantry"})
        self.assertIn("control_settings", result)
        self.assertNotIn("event_types", result["entities"][0])
        self.assertIsNotNone(handler.inventory.fetch.call_args.kwargs["fields"])
        handler.switch_control_settings.read.assert_called()
        handler.inventory.refresh_room.assert_not_called()

    def test_door_editor_preserves_mode_assignments_and_settings_in_room_only(self):
        handler = self.room_controls_handler()
        day = "door:binary_sensor.pantry_door|day"
        night = "door:binary_sensor.pantry_door|night"
        sleep = "door:binary_sensor.pantry_door|sleep"
        elsewhere = "door:binary_sensor.bedroom_window"
        assignments = {key: ["light_group:light.fht_pantry_all_lights"] for key in (day, night, sleep)}
        settings = {key: {"enabled": True, "brightness_pct": 25, "color_mode": "adaptive"} for key in assignments}
        handler.switch_control_settings.read.return_value = {
            "action_assignments": {**assignments, elsewhere: ["light_group:light.other"]},
            "action_settings": {**settings, elsewhere: {"enabled": False}},
        }
        result = handler._room_controls("doors", "Pantry")
        self.assertEqual([entity["entity_id"] for entity in result["door_sensors"]], ["binary_sensor.pantry_door"])
        self.assertEqual(result["control_settings"]["action_assignments"], assignments)
        self.assertEqual(result["control_settings"]["action_settings"], settings)
        self.assertEqual(result["room"], "Pantry")
        self.assertIn("catalog_revision", result)
        self.assertNotIn("action_catalog", result)
        handler.switch_control_settings.write.assert_not_called()

    def test_switch_editor_preserves_hidden_channels_and_event_assignments(self):
        handler = self.room_controls_handler()
        event_id = "event.bedroom_button_up|double_press"
        handler.switch_control_settings.read.return_value = {
            "action_assignments": {event_id: ["light_group:light.fht_bedroom_all_lights"], "switch.other": []},
        }
        handler.switch_assignments.read.return_value = {"switch.bedroom_switch": "light.bedroom_load", "switch.other": "light.other"}
        result = handler._room_controls("switches", "Bedroom 6")
        self.assertEqual(result["display_name"], "Chloe's Bedroom")
        self.assertEqual(len(result["entities"]), 2)
        self.assertEqual(result["entities"][0]["hidden_by"], "integration")
        self.assertEqual(result["entities"][1]["event_types"], ["press", "double_press"])
        self.assertEqual(result["control_settings"]["assignments"], {"switch.bedroom_switch": "light.bedroom_load"})
        self.assertEqual(list(result["control_settings"]["action_assignments"]), [event_id])
        self.assertEqual(result["door_sensors"], [])
        handler.inventory.refresh_room.assert_not_called()

    def test_room_controls_real_projection_keeps_original_area_after_aliasing(self):
        handler = self.handler()
        handler.room_aliases.read.return_value = {"Bedroom 6": "Chloe's Bedroom"}
        inventory = SERVER.EntityInventory("token", "http://unused", "ws://unused", room_aliases=handler.room_aliases)
        inventory._ensure_snapshot = Mock()
        inventory._cached_entities = {
            "switch.bedroom_switch": {"entity_id": "switch.bedroom_switch", "domain": "switch", "area": "Bedroom 6", "device_name": "Bedroom 6 Switch"},
            "binary_sensor.bedroom_door": {"entity_id": "binary_sensor.bedroom_door", "domain": "binary_sensor", "area": "Bedroom 6", "device_class": "door"},
        }
        handler.inventory = inventory
        for kind in ("switches", "doors"):
            with self.subTest(kind=kind):
                index = handler._room_controls(kind)
                entity = index["entities"][0]
                self.assertEqual(entity["area"], "Chloe's Bedroom")
                self.assertEqual(entity["original_area"], "Bedroom 6")
                detail = handler._room_controls(kind, entity["original_area"])
                self.assertEqual(len(detail["entities"]), 1)
                self.assertEqual(detail["entities"][0]["entity_id"], entity["entity_id"])
                self.assertEqual(detail["display_name"], "Chloe's Bedroom")

    def test_room_controls_route_retains_explicit_unassigned_room(self):
        handler = self.room_controls_handler()
        handler.path = "/api/room-controls?kind=doors&room="
        handler._request_is_allowed = Mock(return_value=True)
        handler._send_json = Mock()
        handler.do_GET()
        status, result = handler._send_json.call_args.args
        self.assertEqual(status, 200)
        self.assertTrue(result["ok"])
        self.assertEqual(result["room"], "")
        self.assertEqual(result["display_name"], "Unassigned")
        self.assertEqual([entity["entity_id"] for entity in result["entities"]], ["binary_sensor.unassigned_door"])

    def test_room_controls_reject_invalid_kind_before_reading_inventory(self):
        handler = self.room_controls_handler()
        with self.assertRaises(ValueError):
            handler._room_controls("cameras")
        handler.inventory.fetch.assert_not_called()
        handler.path = "/api/room-controls?kind=cameras"
        handler._request_is_allowed = Mock(return_value=True)
        handler._send_json = Mock()
        handler.do_GET()
        self.assertEqual(handler._send_json.call_args.args[0], 400)

    def test_button_warmup_is_single_flight_and_peek_never_waits(self):
        inventory = SERVER.ButtonDeviceInventory("token", "ws://unused", Path("/tmp"))
        entered, release = threading.Event(), threading.Event()

        def discover(*args):
            entered.set()
            release.wait(2)
            return [{"device_id": "one"}]

        with patch.object(SERVER, "fetch_button_devices", side_effect=discover) as discovery:
            try:
                inventory.warm()
                self.assertTrue(entered.wait(1))
                for _ in range(20):
                    self.assertTrue(inventory.peek()["pending"])
                discovery.assert_called_once()
            finally:
                release.set()
            self.assertEqual(inventory.fetch(), [{"device_id": "one"}])
            discovery.assert_called_once()

    def test_expired_buttons_stay_visible_during_refresh(self):
        inventory = SERVER.ButtonDeviceInventory("token", "ws://unused", Path("/tmp"), cache_ttl=0)
        inventory._cache = [{"device_id": "cached"}]
        with patch.object(inventory, "warm"):
            self.assertEqual(inventory.peek()["buttons"], [{"device_id": "cached"}])

    def inventory(self):
        return SERVER.EntityInventory("token", "http://unused", "ws://unused")

    def test_registry_burst_triggers_one_refresh(self):
        inventory = self.inventory()
        finished = threading.Event()
        inventory._fetch_full_inventory = Mock(side_effect=finished.set)
        for _ in range(100):
            inventory._schedule_registry_refresh()
        self.assertTrue(finished.wait(2))
        inventory._fetch_full_inventory.assert_called_once()
        inventory.stop_live_updates()

    def test_state_event_survives_concurrent_snapshot(self):
        inventory = self.inventory()
        old = {"entity_id": "light.one", "state": "off", "attributes": {}}
        new = {**old, "state": "on"}
        inventory._cached_entities = {"light.one": SERVER.normalize_entities([old])[0]}

        def snapshot():
            inventory._apply_state_changed("light.one", new)
            inventory._cached_entities = {"light.one": SERVER.normalize_entities([old])[0]}
            return inventory._cached_entities, ""

        inventory._fetch_full_inventory_snapshot = snapshot
        inventory._fetch_full_inventory()
        self.assertEqual(inventory._cached_entities["light.one"]["state"], "on")
        self.assertIsNone(inventory._events_during_refresh)


if __name__ == "__main__":
    unittest.main()
