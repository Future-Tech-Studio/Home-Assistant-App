"""Room-mode scene persistence, activation, isolation, and lightweight loading."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch


SPEC = importlib.util.spec_from_file_location("room_scenes_server", Path(__file__).resolve().parents[1] / "future_homes_tech_app/server.py")
SERVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SERVER)


class RoomSceneTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.modes = SERVER.RoomModeSettings(self.root / "room_modes.json")
        self.scenes = SERVER.RoomSceneSettings(self.root / "room_scenes.json")
        self.schedules = SERVER.RoomModeScheduleSettings(self.root / "room_mode_schedules.json")
        self.publisher = Mock()
        self.manager = SERVER.RoomSceneAutomationManager(self.root / "room_scenes.yaml", self.publisher)
        self.targets = {"light.fht_bedroom_2_all_lights", "light.bedroom_2_lamp_1"}
        self.modes.save("Bedroom 2", ["sleep", "movie"])

    def test_mode_schedule_sets_the_room_mode_helper_on_checked_days(self):
        handler = self.handler()
        handler.path = "/api/room-mode-schedules"
        days = {day: {"enabled": False, "time": "21:00"} for day in SERVER.RoomModeScheduleSettings.DAYS}
        for day in ("monday", "tuesday", "wednesday", "thursday", "friday"):
            days[day] = {"enabled": True, "time": "20:30"}
        days["saturday"] = {"enabled": True, "time": "22:00"}
        handler._read_json_object = Mock(return_value={"area": "Bedroom 2", "mode": "sleep", "schedule": {"enabled": True, "days": days}})
        handler._dispatch_POST()
        status, response = handler._send_json.call_args.args
        self.assertEqual(status, 200)
        self.assertTrue(response["schedules"]["Bedroom 2"]["sleep"]["enabled"])
        generated = (self.root / "bedrooms.yaml").read_text()
        self.assertIn("FHT - Bedroom 2 Sleep Schedule", generated)
        self.assertIn('at: "20:30:00"', generated)
        self.assertIn('at: "22:00:00"', generated)
        self.assertNotIn('at: "21:00:00"', generated)
        self.assertIn('"22:00": ["saturday"]', generated)
        self.assertIn("target: {entity_id: input_select.fht_bedroom_2_mode}", generated)
        self.assertIn('data: {option: "Sleep"}', generated)
        self.assertEqual(handler._room_modes_payload()["schedules"]["Bedroom 2"]["sleep"]["days"]["sunday"], {"enabled": False, "time": "21:00"})
        # Turning the mode off for the room, or the schedule off, drops the automation.
        self.modes.save("Bedroom 2", ["movie"])
        handler.bedroom_mode_automations.sync({}, [], [], reload_managed=False)
        self.assertNotIn("Sleep Schedule", (self.root / "bedrooms.yaml").read_text())

    def test_mode_schedule_rejects_unschedulable_modes_and_bad_times(self):
        for mode, schedule in [
            ("wake_up", {"enabled": True}),
            ("armed_away", {"enabled": True}),
            ("sleep", {"enabled": True, "days": {"monday": {"enabled": True, "time": "25:00"}}}),
            ("sleep", {"enabled": True, "days": {"monday": {"enabled": True, "time": ""}}}),
        ]:
            with self.subTest(mode=mode, schedule=schedule), self.assertRaises(ValueError):
                self.schedules.save("Bedroom 2", mode, schedule)
        self.assertEqual(self.schedules.read(), {})

    def test_room_and_alarm_settings_preserve_each_other(self):
        self.modes.save("Bedroom 2", ["sleep", "armed_away", "disarmed"])
        self.modes.save("Bedroom 2", ["movie"], scope="room")
        self.assertEqual(self.modes.read()["Bedroom 2"], ["armed_away", "disarmed", "movie"])
        self.modes.save("Bedroom 2", [], scope="armed_away")
        self.modes.save("Bedroom 2", ["armed_stay_kids"], scope="armed_stay_kids")
        self.assertEqual(self.modes.read()["Bedroom 2"], ["armed_stay_kids", "disarmed", "movie"])
        self.modes.save("Bedroom 2", [], scope="room")
        restored = SERVER.RoomModeSettings(self.root / "room_modes.json")
        self.assertEqual(restored.read()["Bedroom 2"], ["armed_stay_kids", "disarmed"])

    def test_invalid_mode_scope_cannot_overwrite_existing_settings(self):
        for scope, modes in [("room", ["armed_away"]), ("armed_away", ["sleep"]), ("unknown", []), ([], [])]:
            with self.subTest(scope=scope), self.assertRaises(ValueError):
                self.modes.save("Bedroom 2", modes, scope=scope)
        self.assertEqual(self.modes.read()["Bedroom 2"], ["movie", "sleep"])

    def test_alarm_scoped_post_preserves_room_modes_without_arming(self):
        handler = self.handler()
        handler.path = "/api/room-modes"
        handler._read_json_object = Mock(return_value={"area": "Bedroom 2", "enabled_modes": ["armed_away"], "mode_scope": "armed_away"})
        handler._dispatch_POST()
        self.assertEqual(handler._send_json.call_args.args[0], 200)
        self.assertEqual(self.modes.read()["Bedroom 2"], ["armed_away", "movie", "sleep"])
        handler.bedroom_modes.save.assert_not_called()

    def save(self, mode="sleep", **extra):
        return self.scenes.save("Bedroom 2", mode, {"targets": sorted(self.targets), "brightness_pct": 25, **extra}, self.modes.read(), self.targets)

    def handler(self):
        handler = SERVER.FutureHomesTechRequestHandler.__new__(SERVER.FutureHomesTechRequestHandler)
        handler.room_modes = self.modes
        handler.room_scenes = self.scenes
        handler.room_mode_schedules = self.schedules
        handler.room_scene_automations = self.manager
        handler.configuration_publisher = self.publisher
        handler.bedroom_modes = Mock()
        handler.bedroom_modes.read.return_value = {}
        handler.bedroom_mode_automations = SERVER.BedroomModeAutomationManager(self.root / "bedrooms.yaml", self.publisher, room_modes=self.modes, mode_schedules=self.schedules)
        handler.inventory = Mock()
        handler.inventory.fetch.return_value = {"entities": [{"entity_id": target} for target in self.targets]}
        handler.inventory.fetch_security.return_value = {"entities": []}
        handler.inventory.peek.return_value = {"entities": [
            {"entity_id": "fan.bedroom_2_ceiling_fan", "friendly_name": "Ceiling Fan", "original_area": "Bedroom 2", "area": "Bailey's Bedroom"},
            {"entity_id": "cover.bedroom_2_shade", "friendly_name": "Shade", "area": "Bedroom 2"},
            {"entity_id": "lock.bedroom_2_door", "friendly_name": "Door Lock", "area": "Bedroom 2"},
            {"entity_id": "switch.bedroom_2_fan_switch", "friendly_name": "Fan Switch", "area": "Bedroom 2", "wired_load_ids": ["fan.bedroom_2_ceiling_fan"]},
            {"entity_id": "switch.bedroom_2_led", "friendly_name": "Status LED", "area": "Bedroom 2", "entity_category": "config"},
            {"entity_id": "input_boolean.fht_bedroom_2_flag", "friendly_name": "Helper", "area": "Bedroom 2"},
            {"entity_id": "switch.pantry_fridge", "friendly_name": "Fridge", "area": "Pantry"},
        ]}
        handler._home_configurator_index = Mock(return_value={
            "house_settings": {"day_offset": 0},
            "floors": [{"rooms": [
                {"name": "Bedroom 2", "display_name": "Bailey's Bedroom", "mode_type": "bedroom", "current_mode": ""},
                {"name": "Bedroom 6", "display_name": "Chloe's Bedroom", "mode_type": "bedroom", "current_mode": ""},
                {"name": "Pantry", "display_name": "Pantry", "mode_type": "", "current_mode": ""},
            ]}],
        })
        handler._send_json = Mock()
        handler._catalog_revision = Mock(return_value="catalog-one")
        handler._request_is_allowed = Mock(return_value=True)
        return handler

    def test_preserves_disabled_scene_drafts_and_other_rooms(self):
        saved = self.save(color_mode="rgb", color_rgb=[20, 30, 255])
        self.save("movie", brightness_pct=65)
        self.modes.save("Bedroom 6", ["sleep"])
        self.scenes.save("Bedroom 6", "sleep", {"targets": [], "brightness_pct": 0}, self.modes.read(), self.targets)
        restored = SERVER.RoomSceneSettings(self.root / "room_scenes.json").read()
        self.assertEqual(restored["Bedroom 2"]["sleep"], saved["Bedroom 2"]["sleep"])
        self.assertEqual(restored["Bedroom 2"]["movie"]["brightness_pct"], 65)
        self.modes.save("Bedroom 2", ["movie"])
        self.manager.sync(restored, self.modes.read())
        self.assertNotIn('to: "Sleep"', (self.root / "room_scenes.yaml").read_text())
        self.assertIn('to: "Movie"', (self.root / "room_scenes.yaml").read_text())
        self.assertIn("sleep", self.scenes.read()["Bedroom 2"])
        self.modes.save("Bedroom 2", ["movie", "sleep"])
        self.manager.sync(restored, self.modes.read())
        self.assertIn("rgb_color: [20, 30, 255]", (self.root / "room_scenes.yaml").read_text())

    def test_modes_payload_uses_index_not_device_discovery(self):
        handler = self.handler()
        handler.inventory.fetch.side_effect = AssertionError("Full inventory was requested")
        handler.path = "/api/room-modes"
        handler.do_GET()
        status, response = handler._send_json.call_args.args
        self.assertEqual(status, 200)
        self.assertEqual([room["name"] for room in response["rooms"]], ["Bedroom 2", "Bedroom 6"])
        self.assertEqual(response["settings"]["Bedroom 2"], ["movie", "sleep"])

    def test_scene_cards_are_derived_from_enabled_modes_without_inventory(self):
        handler = self.handler()
        self.save()
        handler.path = "/api/room-scenes"
        handler.do_GET()
        status, response = handler._send_json.call_args.args
        self.assertEqual(status, 200)
        self.assertEqual([scene["mode"] for scene in response["scenes"]], ["day", "night", "movie", "sleep"])
        self.assertEqual(response["scenes"][3]["display_name"], "Bailey's Bedroom")
        self.assertTrue(response["scenes"][3]["configured"])
        # The house's Day and Night stay, since the room keeps its mode helper.
        self.modes.save("Bedroom 2", [])
        self.assertEqual([scene["mode"] for scene in handler._room_scenes_payload()["scenes"]], ["day", "night"])
        handler.inventory.fetch.assert_not_called()

    def test_mode_save_creates_helpers_without_enabling_special_behaviors(self):
        handler = self.handler()
        handler.path = "/api/room-modes"
        handler._read_json_object = Mock(return_value={"area": "Bedroom 6", "enabled_modes": ["sleep", "movie"]})
        handler._dispatch_POST()
        self.assertEqual(handler._send_json.call_args.args[0], 200)
        generated = (self.root / "bedrooms.yaml").read_text()
        self.assertIn("fht_bedroom_6_mode:", generated)
        self.assertIn("fht_bedroom_2_mode:", generated)
        self.assertNotIn("Disarmed Day Night", generated)
        self.assertNotIn("Random Lights", generated)
        handler.bedroom_modes.save.assert_not_called()
        self.publisher.reload_domains.assert_called_once_with(("input_select", "automation"))
        self.publisher.reload_automations.assert_not_called()
        self.assertEqual((self.root / "room_scenes.yaml").read_text(), "automation: []\n")
        self.modes.save("Bedroom 6", [])
        handler.bedroom_mode_automations.sync({}, [], [], reload_managed=False)
        self.assertIn("fht_bedroom_6_mode:", (self.root / "bedrooms.yaml").read_text())

    def test_scene_save_generates_mode_transition_not_live_light_calls(self):
        handler = self.handler()
        handler.path = "/api/room-scenes"
        handler._read_json_object = Mock(return_value={"area": "Bedroom 2", "mode": "sleep", "settings": {"targets": sorted(self.targets), "brightness_pct": 25, "color_mode": "kelvin", "color_kelvin": 2800}})
        handler._dispatch_POST()
        status, response = handler._send_json.call_args.args
        self.assertEqual(status, 200)
        self.assertTrue(response["saved"])
        self.assertTrue(response["activated"])
        output = (self.root / "room_scenes.yaml").read_text()
        self.assertIn("entity_id: input_select.fht_bedroom_2_mode", output)
        self.assertIn('to: "Sleep"', output)
        self.assertIn("trigger.from_state is not none", output)
        self.assertIn("brightness_pct: 25", output)
        self.assertIn("color_temp_kelvin: 2800", output)
        self.publisher.reload_automations.assert_called_once()
        self.assertEqual(len(self.publisher.method_calls), 1)
        handler.inventory.run_action.assert_not_called()

    def test_zero_brightness_turns_off_and_cleared_targets_remove_automation(self):
        self.manager.sync(self.save(brightness_pct=0, color_mode="rgb"), self.modes.read())
        output = (self.root / "room_scenes.yaml").read_text()
        self.assertIn("action: light.turn_off", output)
        self.assertNotIn("brightness_pct", output)
        self.assertNotIn("rgb_color", output)
        self.manager.sync(self.save(targets=[]), self.modes.read())
        self.assertEqual((self.root / "room_scenes.yaml").read_text(), "automation: []\n")

    def test_reload_failure_is_saved_but_not_activated_and_retry_is_possible(self):
        handler = self.handler()
        handler.path = "/api/room-scenes"
        handler._read_json_object = Mock(return_value={"area": "Bedroom 2", "mode": "sleep", "settings": {"targets": sorted(self.targets)}})
        self.publisher.reload_automations.side_effect = SERVER.HomeAssistantAPIError("Test reload failure")
        handler._dispatch_POST()
        status, response = handler._send_json.call_args.args
        self.assertEqual(status, 502)
        self.assertTrue(response["saved"])
        self.assertFalse(response["activated"])
        self.assertTrue(self.scenes.read()["Bedroom 2"]["sleep"]["targets"])
        self.publisher.reload_automations.side_effect = None
        handler._dispatch_POST()
        self.assertEqual(handler._send_json.call_args.args[0], 200)
        self.assertEqual(self.publisher.reload_automations.call_count, 2)

    def test_invalid_scene_targets_modes_and_values_never_overwrite(self):
        saved = self.save()
        for invalid in (
            {"targets": ["switch.fan"]},
            {"targets": ["light.bulb\nautomation:"]},
            {"targets": ["light.deleted"]},
            {"targets": "light.one"},
            {"brightness_pct": 101},
            {"brightness_pct": -1},
            {"brightness_pct": True},
            {"color_mode": "whatever"},
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.save(**invalid)
        with self.assertRaises(ValueError):
            self.save("relax")
        self.assertEqual(self.scenes.read(), saved)

    def test_empty_scene_package_and_startup_sync_do_not_reload(self):
        self.manager.sync({}, self.modes.read(), reload_automations=False)
        self.publisher.reload_automations.assert_not_called()
        self.assertEqual((self.root / "room_scenes.yaml").read_text(), "automation: []\n")

    def test_mode_lists_room_devices_and_sets_their_states(self):
        handler = self.handler()
        handler.path = "/api/room-scenes"
        handler.do_GET()
        devices = handler._send_json.call_args.args[1]["room_devices"]
        self.assertEqual([device["name"] for device in devices["Bedroom 2"]], ["Ceiling Fan", "Door Lock", "Shade"])
        self.assertEqual(devices["Pantry"][0]["entity_id"], "switch.pantry_fridge")
        handler.inventory.fetch.assert_not_called()
        states = {"fan.bedroom_2_ceiling_fan": "on", "cover.bedroom_2_shade": "closed", "lock.bedroom_2_door": "locked"}
        handler._read_json_object = Mock(return_value={"area": "Bedroom 2", "mode": "sleep", "settings": {"targets": [], "devices": states}})
        handler._dispatch_POST()
        status, response = handler._send_json.call_args.args
        self.assertEqual(status, 200)
        self.assertTrue(next(scene for scene in response["scenes"] if scene["mode"] == "sleep")["configured"])
        output = (self.root / "room_scenes.yaml").read_text()
        self.assertIn('to: "Sleep"', output)
        self.assertNotIn("light.turn", output)
        for action, entity_id in (("fan.turn_on", "fan.bedroom_2_ceiling_fan"), ("cover.close_cover", "cover.bedroom_2_shade"), ("lock.lock", "lock.bedroom_2_door")):
            self.assertIn(f"action: {action}\n        continue_on_error: true\n        target:\n          entity_id: \"{entity_id}\"", output)
        # A lights-only save keeps the device states.
        self.save()
        self.assertEqual(self.scenes.read()["Bedroom 2"]["sleep"]["devices"], states)
        self.manager.sync(self.scenes.read(), self.modes.read())
        output = (self.root / "room_scenes.yaml").read_text()
        self.assertIn("action: light.turn_on", output)
        self.assertIn("action: fan.turn_on", output)
        # "Leave as is" for every device drops them.
        self.save(devices={})
        self.assertNotIn("devices", self.scenes.read()["Bedroom 2"]["sleep"])

    def test_invalid_device_states_never_overwrite(self):
        saved = self.save()
        for devices in ({"fan.x": "open"}, {"lock.x": "unlocked"}, {"climate.x": "on"}, {"fan.x\nautomation:": "on"}, ["fan.x"]):
            with self.subTest(devices=devices), self.assertRaises(ValueError):
                self.save(devices=devices)
        with self.assertRaises(ValueError):
            self.scenes.save("Bedroom 2", "sleep", {"targets": [], "devices": {"fan.other_room": "on"}}, self.modes.read(), self.targets, {"fan.bedroom_2_ceiling_fan"})
        self.assertEqual(self.scenes.read(), saved)

    def test_house_day_and_night_scenes_run_in_every_room_with_a_helper(self):
        self.scenes.save("Bedroom 2", "night", {"targets": [], "devices": {"fan.bedroom_2_ceiling_fan": "off"}}, self.modes.read(), self.targets)
        self.manager.sync(self.scenes.read(), self.modes.read())
        output = (self.root / "room_scenes.yaml").read_text()
        self.assertIn('to: "Night"', output)
        self.assertIn("action: fan.turn_off", output)
        with self.assertRaises(ValueError):
            self.scenes.save("Pantry", "day", {"targets": []}, self.modes.read(), self.targets)

    def test_rooms_without_their_own_mode_follow_the_house(self):
        handler = self.handler()
        handler.bedroom_mode_automations.sync({}, [], [], reload_managed=False)
        output = (self.root / "bedrooms.yaml").read_text()
        self.assertIn("FHT - Bedroom 2 Follows House Day and Night", output)
        self.assertIn("states('input_select.fht_bedroom_2_mode') in ['Day', 'Night', 'unknown']", output)
        self.assertIn("option: \"{{ states('input_select.fht_house_mode') }}\"", output)
        # A bedroom with its own Day/Night schedule keeps it.
        handler.bedroom_mode_automations.sync({"Bedroom 2": {"disarmed_enabled": True}}, [], [], reload_managed=False)
        self.assertNotIn("Bedroom 2 Follows House", (self.root / "bedrooms.yaml").read_text())

    def test_adaptive_reuses_existing_solar_color_template(self):
        self.manager.sync(self.save(color_mode="adaptive"), self.modes.read())
        self.assertIn(json.dumps(SERVER.LightScheduleAutomationManager._adaptive_kelvin_template()), (self.root / "room_scenes.yaml").read_text())


class LightingProjectionTests(unittest.TestCase):
    def test_sensor_events_no_longer_invalidate_lighting_but_security_stays_live(self):
        channels = SERVER.EntityInventory._event_channels
        for device_class in ("temperature", "humidity", "illuminance", "presence", "motion", "door", "window"):
            with self.subTest(device_class=device_class):
                entity = {"entity_id": "sensor.test", "domain": "sensor", "device_class": device_class}
                self.assertNotIn("lighting", channels(entity))
        self.assertIn("lighting", channels({"domain": "light"}))
        self.assertIn("security", channels({"domain": "binary_sensor", "device_class": "door"}))
        self.assertIn("security", channels({"domain": "binary_sensor", "device_class": "window"}))

    def test_lighting_does_not_copy_sensor_payloads(self):
        inventory = SERVER.EntityInventory("test", "http://unused", "ws://unused")
        inventory._cached_entities = {
            "light.fht_room_all_lights": {"entity_id": "light.fht_room_all_lights", "state": "on", "domain": "light", "area": "Room", "brightness": 128},
            "sensor.room_temperature": {"entity_id": "sensor.room_temperature", "domain": "sensor", "area": "Room", "state": "72"},
        }
        inventory._live_connected = True
        original = SERVER.copy.deepcopy

        def copy_selected(value):
            if isinstance(value, dict) and value.get("entity_id") == "sensor.room_temperature":
                raise AssertionError("Lighting copied an environmental sensor")
            return original(value)

        with patch.object(SERVER.copy, "deepcopy", side_effect=copy_selected), patch.object(SERVER, "urlopen", side_effect=AssertionError("Network used")):
            result = inventory.fetch_lighting()
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["entities"][0]["brightness"], 128)
        self.assertNotIn("room_status", result)
