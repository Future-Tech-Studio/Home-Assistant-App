"""Tests for the Future Homes Tech App Ingress server."""

from __future__ import annotations

import importlib.util
import io
import json
from datetime import datetime, timezone
from pathlib import Path
import socket
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from action_catalog_fixture import bedroom_lights

MODULE_PATH = (
    Path(__file__).parents[1]
    / "future_homes_tech_app"
    / "server.py"
)
CONFIG_PATH = MODULE_PATH.with_name("config.yaml")
SPEC = importlib.util.spec_from_file_location("server", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
SERVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SERVER)


class MockResponse:
    """Provide a context-managed JSON API response."""

    def __init__(self, payload: object) -> None:
        """Initialize the mock response."""
        self._content = io.BytesIO(json.dumps(payload).encode("utf-8"))

    def __enter__(self) -> MockResponse:
        """Enter the response context."""
        return self

    def __exit__(self, *args: object) -> None:
        """Exit the response context."""

    def read(self, size: int = -1) -> bytes:
        """Read response bytes."""
        return self._content.read(size)


class RoomAliasTests(unittest.TestCase):
    """Verify App-only room display names."""

    def test_room_aliases_persist_and_can_be_removed(self) -> None:
        """Store aliases without changing Home Assistant configuration."""
        with tempfile.TemporaryDirectory() as directory:
            aliases = SERVER.RoomAliases(Path(directory) / "rooms.json")
            self.assertEqual(
                aliases.save("Bedroom 1", "Master Bedroom"),
                {"Bedroom 1": "Master Bedroom"},
            )
            self.assertEqual(aliases.read(), {"Bedroom 1": "Master Bedroom"})
            self.assertEqual(aliases.save("Bedroom 1", ""), {})

    def test_room_alias_masks_names_but_not_entity_ids(self) -> None:
        """Replace room text only in App-facing display fields."""
        entities = [
            {
                "entity_id": "light.bedroom_1_fan_light",
                "friendly_name": "Bedroom 1 Fan Light",
                "area": "Bedroom 1",
            },
            {
                "entity_id": "light.fht_bedroom_1_all_lights",
                "friendly_name": "Bedroom 1 All Lights",
                "area": "",
            },
        ]
        SERVER.apply_room_aliases(
            entities,
            {"Bedroom 1": "Master Bedroom"},
        )
        self.assertEqual(entities[0]["area"], "Master Bedroom")
        self.assertEqual(
            entities[0]["friendly_name"],
            "Master Bedroom Fan Light",
        )
        self.assertEqual(
            entities[0]["entity_id"],
            "light.bedroom_1_fan_light",
        )
        self.assertEqual(entities[0]["original_area"], "Bedroom 1")
        self.assertEqual(
            entities[1]["friendly_name"],
            "Master Bedroom All Lights",
        )


class WakeRoutineTests(unittest.TestCase):
    """Verify per-room wake schedules and override helpers."""

    def test_wake_routine_persists_functions_and_generates_package(self) -> None:
        """Keep individual lights and FHT groups in separate action blocks."""
        with tempfile.TemporaryDirectory() as directory:
            settings = SERVER.WakeRoutineSettings(Path(directory) / "wake.json")
            saved = settings.save(
                "Bedroom 1",
                {
                    "enabled": True,
                    "times": {"monday": "06:30", "saturday": "08:15"},
                    "actions": [
                        {"type": "lights", "entities": ["light.bedroom_lamp"]},
                        {"type": "light_groups", "entities": ["light.fht_bedroom_all_lights"]},
                    ],
                    "target_entities": [
                        "light.bedroom_lamp",
                        "light.fht_bedroom_all_lights",
                    ],
                    "brightness_pct": 65,
                    "override_time": "07:45",
                },
                {"light.bedroom_lamp", "light.fht_bedroom_all_lights"},
            )
            package = Path(directory) / "wake.yaml"
            automations = SERVER.WakeRoutineAutomationManager(package).sync(
                saved,
                [
                    {"entity_id": "light.bedroom_lamp"},
                    {"entity_id": "light.fht_bedroom_all_lights"},
                ],
            )
            content = package.read_text(encoding="utf-8")
            self.assertEqual(saved["Bedroom 1"]["actions"][0]["type"], "lights")
            self.assertIn("input_button.fht_bedroom_1_wake_override", content)
            self.assertIn('at: "06:30:00"', content)
            self.assertIn("brightness_pct: 65", content)
            self.assertEqual(len(automations), 2)

    def test_wake_times_from_ten_oclock_are_quoted_in_yaml(self) -> None:
        """Quote wake times so 10:00 and later do not parse as base-60 numbers."""
        with tempfile.TemporaryDirectory() as directory:
            settings = SERVER.WakeRoutineSettings(Path(directory) / "wake.json")
            saved = settings.save(
                "Bedroom 1",
                {
                    "enabled": True,
                    "times": {"monday": "06:30", "saturday": "10:00", "sunday": "23:59"},
                    "actions": [{"type": "lights", "entities": ["light.bedroom_lamp"]}],
                    "target_entities": ["light.bedroom_lamp"],
                    "override_time": "07:00",
                },
                {"light.bedroom_lamp"},
            )
            package = Path(directory) / "wake.yaml"
            SERVER.WakeRoutineAutomationManager(package).sync(
                saved, [{"entity_id": "light.bedroom_lamp"}],
            )
            content = package.read_text(encoding="utf-8")
            self.assertIn('at: "06:30:00"', content)
            self.assertIn('at: "10:00:00"', content)
            self.assertIn('at: "23:59:00"', content)
            self.assertNotIn("at: 10:00:00", content)

    def test_wake_sync_keeps_routines_whose_targets_are_missing(self) -> None:
        """A renamed or not-yet-loaded device must not stop the package being written."""
        with tempfile.TemporaryDirectory() as directory:
            settings = SERVER.WakeRoutineSettings(Path(directory) / "wake.json")
            settings.save(
                "Bedroom 1",
                {
                    "enabled": True,
                    "times": {"monday": "06:30"},
                    "actions": [{"type": "lights", "entities": ["light.bedroom_lamp"]}],
                    "target_entities": ["light.bedroom_lamp"],
                },
                {"light.bedroom_lamp", "light.office_lamp"},
            )
            saved = settings.save(
                "Office",
                {
                    "enabled": True,
                    "times": {"monday": "07:00"},
                    "actions": [{"type": "lights", "entities": ["light.office_lamp"]}],
                    "target_entities": ["light.office_lamp"],
                },
                {"light.bedroom_lamp", "light.office_lamp"},
            )
            package = Path(directory) / "wake.yaml"
            with patch("builtins.print") as mocked_print:
                automations = SERVER.WakeRoutineAutomationManager(package).sync(
                    saved, [{"entity_id": "light.office_lamp"}],
                )
            content = package.read_text(encoding="utf-8")
            self.assertEqual(len(automations), 4)
            self.assertIn("fht_wake_bedroom_1_run", content)
            self.assertIn("entity_id: light.bedroom_lamp", content)
            self.assertIn("fht_wake_office_run", content)
            logged = " ".join(str(call.args[0]) for call in mocked_print.call_args_list)
            self.assertIn("[Wake Routines]", logged)
            self.assertIn("Bedroom 1", logged)
            self.assertIn("light.bedroom_lamp", logged)
            self.assertNotIn("Office", logged)

    def test_wake_save_uses_the_complete_inventory_for_mode_helpers(self) -> None:
        """Saving must see the bedroom package's mode helpers, not re-declare them."""
        with tempfile.TemporaryDirectory() as directory:
            handler = object.__new__(SERVER.FutureHomesTechRequestHandler)
            handler.path = "/api/wake-routines"
            body = json.dumps({
                "area": "Bedroom 1",
                "settings": {
                    "enabled": True,
                    "times": {"monday": "06:30"},
                    "actions": [{
                        "type": "room_mode",
                        "entities": [],
                        "entity_id": "input_select.fht_bedroom_1_mode",
                        "option": "Wake Up",
                    }],
                },
            }).encode("utf-8")
            handler.headers = {"Content-Length": str(len(body))}
            handler.rfile = io.BytesIO(body)
            handler.wfile = io.BytesIO()
            handler.send_response = Mock()
            handler.send_header = Mock()
            handler.end_headers = Mock()
            handler.wake_routines = SERVER.WakeRoutineSettings(Path(directory) / "wake.json")
            package = Path(directory) / "wake.yaml"
            handler.wake_routine_automations = SERVER.WakeRoutineAutomationManager(package)
            handler.registry_organizer = Mock()
            everything = [
                {"entity_id": "input_select.fht_bedroom_1_mode"},
                {"entity_id": "light.bedroom_lamp"},
            ]
            handler.inventory = Mock()
            handler.inventory.fetch.side_effect = lambda include_all=False, **_: {
                "entities": [
                    entity for entity in everything
                    if include_all or not entity["entity_id"].startswith("input_")
                ]
            }

            handler._dispatch_POST()

            handler.send_response.assert_called_once_with(200)
            content = package.read_text(encoding="utf-8")
            self.assertIn("input_select.select_option", content)
            self.assertNotIn("input_select:\n", content)
            self.assertNotIn("fht_bedroom_1_mode:", content)

    def test_control_settings_accept_wake_override_target(self) -> None:
        """Allow a physical switch or button gesture to arm the override."""
        with tempfile.TemporaryDirectory() as directory:
            settings = SERVER.SwitchControlSettings(Path(directory) / "controls.json")
            payload = settings.save_mode(
                "switch.bedroom_1_switch_3g_switch_3",
                "input_button.fht_bedroom_1_wake_override",
            )
            self.assertEqual(
                payload["mode_assignments"]["switch.bedroom_1_switch_3g_switch_3"],
                "input_button.fht_bedroom_1_wake_override",
            )

    def test_wake_routine_generates_room_mode_and_audio_actions(self) -> None:
        """Generate a room-mode helper and media playback from wake actions."""
        with tempfile.TemporaryDirectory() as directory:
            settings = SERVER.WakeRoutineSettings(Path(directory) / "wake.json")
            saved = settings.save(
                "Bathroom 1",
                {
                    "enabled": True,
                    "times": {"monday": "06:30"},
                    "actions": [
                        {
                            "type": "room_mode",
                            "entities": [],
                            "entity_id": "input_select.fht_bathroom_1_mode",
                            "option": "Morning",
                        },
                        {
                            "type": "audio",
                            "entities": ["media_player.bathroom_speaker"],
                            "media_content_id": "media-source://wake-up",
                            "media_content_type": "music",
                        },
                    ],
                    "brightness_pct": 70,
                    "override_time": "07:00",
                },
                {"media_player.bathroom_speaker"},
            )
            package = Path(directory) / "wake.yaml"
            SERVER.WakeRoutineAutomationManager(package).sync(
                saved,
                [{"entity_id": "media_player.bathroom_speaker"}],
            )
            content = package.read_text(encoding="utf-8")
            self.assertIn("fht_bathroom_1_mode:", content)
            self.assertIn('option: "Morning"', content)
            self.assertIn("action: media_player.play_media", content)
            self.assertIn('media_content_id: "media-source://wake-up"', content)


class FridgeAlarmTests(unittest.TestCase):
    """Verify refrigerator alert discovery, persistence, and automation output."""

    def test_device_alarm_room_aliases_remain_compatible(self) -> None:
        for name in ("Bridges", "Device Alarms", "Fridges"):
            with self.subTest(name=name):
                self.assertTrue(SERVER.is_device_alarm_room_name(name))
        self.assertFalse(SERVER.is_device_alarm_room_name("Kitchen"))

    def test_catalog_groups_temperature_and_door_sensors_by_device(self) -> None:
        entities = [
            {
                "entity_id": "sensor.kitchen_fridge_temperature",
                "domain": "sensor",
                "device_id": "fridge-1",
                "device_name": "Kitchen Refrigerator",
                "friendly_name": "Kitchen Refrigerator Temperature",
                "device_class": "temperature",
                "state": "37",
                "unit_of_measurement": "°F",
            },
            {
                "entity_id": "binary_sensor.kitchen_fridge_door",
                "domain": "binary_sensor",
                "device_id": "fridge-1",
                "device_name": "Kitchen Refrigerator",
                "friendly_name": "Kitchen Refrigerator Door",
                "device_class": "door",
                "state": "off",
            },
        ]

        catalog = SERVER.fridge_alarm_catalog(entities)

        self.assertEqual(len(catalog), 1)
        self.assertEqual(catalog[0]["name"], "Kitchen Refrigerator")
        self.assertEqual(len(catalog[0]["temperature_sensors"]), 1)
        self.assertEqual(len(catalog[0]["door_sensors"]), 1)

    def test_catalog_lists_only_actionable_sirens_and_chimes(self) -> None:
        entities = [
            {
                "entity_id": "siren.hallway_siren",
                "friendly_name": "Hallway Siren",
            },
            {
                "entity_id": "button.kitchen_chime_play_buzzer",
                "friendly_name": "Kitchen Chime Play Buzzer",
            },
            {
                "entity_id": "button.kitchen_chime_play_chime",
                "friendly_name": "Kitchen Chime Play Chime",
            },
            {
                "entity_id": "button.upstairs_hallway_chime_play_siren",
                "friendly_name": "Upstairs Hallway Chime Play Siren",
            },
            {
                "entity_id": "button.kitchen_chime_restart",
                "friendly_name": "Kitchen Chime Restart",
            },
            {
                "entity_id": "button.kitchen_chime_unadopt_device",
                "friendly_name": "Kitchen Chime Unadopt Device",
            },
            {
                "entity_id": "button.playroom_door_sensor_identify",
                "friendly_name": "Playroom Door Sensor Identify",
            },
            {
                "entity_id": "button.playroom_fan_light",
                "friendly_name": "Playroom Fan Light",
            },
        ]

        catalog = SERVER.fridge_alarm_output_catalog(entities)

        self.assertEqual(
            [item["entity_id"] for item in catalog["sirens"]],
            ["siren.hallway_siren", "button.upstairs_hallway_chime_play_siren"],
        )
        self.assertEqual(
            [item["entity_id"] for item in catalog["chimes"]],
            ["button.kitchen_chime_play_buzzer"],
        )
        self.assertEqual(catalog["chimes"][0]["name"], "Kitchen Chime")
        converted = SERVER.device_alarm_buzzer_settings({"sensor.fridge": {"alert_targets": ["button.kitchen_chime_play_chime"]}}, entities)
        self.assertEqual(converted["sensor.fridge"]["alert_targets"], ["button.kitchen_chime_play_buzzer"])

    def test_settings_persist_validated_alerts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = SERVER.FridgeAlarmSettings(Path(directory) / "fridge.json")
            saved = settings.save(
                "sensor.kitchen_fridge_temperature",
                "temperature",
                {
                    "enabled": True,
                    "threshold": 41.5,
                    "delay_minutes": 10,
                    "alert_target": "siren.hallway_siren",
                    "alert_behavior": "until_clear",
                },
            )
            self.assertEqual(saved["sensor.kitchen_fridge_temperature"]["threshold"], 41.5)
            self.assertEqual(
                saved["sensor.kitchen_fridge_temperature"]["alert_targets"],
                ["siren.hallway_siren"],
            )
            self.assertEqual(
                saved["sensor.kitchen_fridge_temperature"]["alert_behavior"],
                "until_clear",
            )
            with self.assertRaises(ValueError):
                settings.save(
                    "binary_sensor.kitchen_fridge_door",
                    "door",
                    {"enabled": True, "delay_minutes": 181},
                )

    def test_manager_writes_temperature_and_door_automations(self) -> None:
        entities = [
            {
                "entity_id": "sensor.kitchen_fridge_temperature",
                "domain": "sensor",
                "friendly_name": "Kitchen Refrigerator Temperature",
                "device_class": "temperature",
                "unit_of_measurement": "°F",
            },
            {
                "entity_id": "binary_sensor.kitchen_fridge_door",
                "domain": "binary_sensor",
                "friendly_name": "Kitchen Refrigerator Door",
                "device_class": "door",
            },
            {
                "entity_id": "siren.hallway_siren",
                "domain": "siren",
                "friendly_name": "Hallway Siren",
            },
            {
                "entity_id": "button.kitchen_chime_play_chime",
                "domain": "button",
                "friendly_name": "Kitchen Chime Play Chime",
            },
            {
                "entity_id": "button.upstairs_hallway_chime_play_buzzer",
                "domain": "button",
                "friendly_name": "Upstairs Hallway Chime Play Buzzer",
            },
        ]
        settings = {
            "sensor.kitchen_fridge_temperature": {
                "kind": "temperature",
                "enabled": True,
                "threshold": 40,
                "delay_minutes": 5,
                "alert_targets": [
                    "button.kitchen_chime_play_chime",
                    "button.upstairs_hallway_chime_play_buzzer",
                ],
                "alert_behavior": "until_clear",
            },
            "binary_sensor.kitchen_fridge_door": {
                "kind": "door",
                "enabled": True,
                "delay_minutes": 2,
                "alert_targets": ["siren.hallway_siren"],
                "alert_behavior": "once",
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory) / "fridge.yaml"
            automations = SERVER.FridgeAlarmAutomationManager(package).sync(settings, entities)
            content = package.read_text(encoding="utf-8")

        self.assertEqual(len(automations), 2)
        self.assertIn("trigger: numeric_state", content)
        self.assertIn("above: 40", content)
        self.assertIn('to: "on"', content)
        self.assertIn("persistent_notification.create", content)
        self.assertIn("persistent_notification.dismiss", content)
        self.assertIn("action: siren.turn_on", content)
        self.assertIn("action: siren.turn_off", content)
        self.assertIn("action: button.press", content)
        self.assertIn(
            '["button.kitchen_chime_play_chime", "button.upstairs_hallway_chime_play_buzzer"]',
            content,
        )
        self.assertIn('["siren.hallway_siren"]', content)
        self.assertIn("repeat:", content)
        self.assertIn("while:", content)
        self.assertNotIn("delay: 5", content)
        self.assertTrue(all(item["alert_behavior"] == "until_clear" for item in automations))
        self.assertIn(SERVER.FRIDGE_ALARM_AUTOMATION_UNIQUE_ID_PREFIX, content)


    def test_device_webhook_is_opt_in_and_separate_from_audible_repeat(self) -> None:
        entity = {"entity_id": "binary_sensor.fridge_door", "domain": "binary_sensor", "device_class": "door", "friendly_name": "Fridge Door"}
        setting = {"kind": "door", "enabled": True, "unifi_webhook": True, "alert_behavior": "once"}
        with tempfile.TemporaryDirectory() as directory, patch.dict(SERVER.os.environ, {"DEVICE_ALARM_WEBHOOK": "https://example.test/webhook/DeviceAlarm"}):
            path = Path(directory) / "alarms.yaml"
            manager = SERVER.FridgeAlarmAutomationManager(path)
            manager.sync({entity["entity_id"]: setting}, [entity])
            self.assertIn("rest_command.fht_device_alarm_webhook", path.read_text())
            self.assertEqual(path.read_text().count("rest_command.fht_device_alarm_webhook"), 1)
            setting["unifi_webhook"] = False
            manager.sync({entity["entity_id"]: setting}, [entity])
            self.assertNotIn("rest_command.fht_device_alarm_webhook", path.read_text())


class DoorOpenAlertTests(unittest.TestCase):
    """Verify door-left-open reminder settings, payloads, and automations."""

    ENTITIES = [
        {"entity_id": "binary_sensor.front_door_sensor", "domain": "binary_sensor", "friendly_name": "Front Door Sensor", "device_class": "door", "area": "Entry", "state": "off"},
        {"entity_id": "binary_sensor.kitchen_window", "domain": "binary_sensor", "friendly_name": "Kitchen Window Contact Sensor", "device_class": "window", "area": "Kitchen", "state": "on"},
        {"entity_id": "binary_sensor.kitchen_fridge_door", "domain": "binary_sensor", "friendly_name": "Kitchen Refrigerator Door", "device_class": "door", "area": "Kitchen", "state": "off"},
        {"entity_id": "binary_sensor.hall_motion", "domain": "binary_sensor", "friendly_name": "Hall Motion", "device_class": "motion", "area": "Hall", "state": "off"},
        {"entity_id": "siren.hallway_siren", "domain": "siren", "friendly_name": "Hallway Siren"},
        {"entity_id": "button.kitchen_chime_play_buzzer", "domain": "button", "friendly_name": "Kitchen Chime Play Buzzer"},
        {"entity_id": "input_select.fht_house_mode", "domain": "input_select", "friendly_name": "Future Homes Tech House Mode", "state": "Night"},
    ]

    def test_normalize_applies_defaults_and_rejects_bad_values(self) -> None:
        self.assertEqual(
            SERVER.DoorOpenAlertSettings.normalize({}),
            {"enabled": False, "delay_minutes": 5, "when": "any", "alert_targets": [], "unifi_webhook": False, "notification": True},
        )
        normalized = SERVER.DoorOpenAlertSettings.normalize({
            "enabled": 1,
            "delay_minutes": "30",
            "when": "Night_Sleep",
            "alert_targets": ["siren.hallway_siren", "siren.hallway_siren", "", "button.kitchen_chime_play_buzzer"],
            "unifi_webhook": True,
            "notification": False,
            "extra": "ignored",
        })
        self.assertEqual(normalized, {
            "enabled": True,
            "delay_minutes": 30,
            "when": "night_sleep",
            "alert_targets": ["siren.hallway_siren", "button.kitchen_chime_play_buzzer"],
            "unifi_webhook": True,
            "notification": False,
        })
        self.assertFalse(SERVER.DoorOpenAlertSettings.normalize({"unifi_webhook": "yes"})["unifi_webhook"])
        for bad in (
            {"delay_minutes": 181},
            {"delay_minutes": -1},
            {"delay_minutes": "soon"},
            {"when": "weekends"},
            {"alert_targets": ["light.lamp"]},
            {"alert_targets": "siren.hallway_siren"},
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                SERVER.DoorOpenAlertSettings.normalize(bad)

    def test_settings_persist_and_skip_invalid_entries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "door_open_alert_settings.json"
            settings = SERVER.DoorOpenAlertSettings(path)
            self.assertEqual(settings.read(), {})
            saved = settings.save(
                "binary_sensor.front_door_sensor",
                {"enabled": True, "delay_minutes": 10, "when": "night", "alert_targets": ["siren.hallway_siren"]},
            )
            self.assertEqual(saved["binary_sensor.front_door_sensor"]["when"], "night")
            self.assertTrue(saved["binary_sensor.front_door_sensor"]["notification"])
            settings.save("binary_sensor.kitchen_window", {"enabled": False})
            self.assertEqual(sorted(settings.read()), ["binary_sensor.front_door_sensor", "binary_sensor.kitchen_window"])
            reopened = SERVER.DoorOpenAlertSettings(path).read()
            self.assertEqual(reopened["binary_sensor.front_door_sensor"]["delay_minutes"], 10)
            for entity_id, value in (
                ("sensor.kitchen_temperature", {"enabled": True}),
                ("binary_sensor.", {"enabled": True}),
                ("binary_sensor.front_door_sensor", {"delay_minutes": 999}),
            ):
                with self.subTest(entity_id=entity_id), self.assertRaises(ValueError):
                    settings.save(entity_id, value)
            self.assertEqual(settings.read()["binary_sensor.front_door_sensor"]["delay_minutes"], 10)
            path.write_text(json.dumps({
                "binary_sensor.ok": {"enabled": True},
                "binary_sensor.bad": {"when": "weekends"},
                "sensor.nope": {"enabled": True},
                "junk": 1,
            }), encoding="utf-8")
            self.assertEqual(list(settings.read()), ["binary_sensor.ok"])
            self.assertEqual(settings.read()["binary_sensor.ok"]["delay_minutes"], 5)
            path.write_text("{broken", encoding="utf-8")
            with self.assertRaises(SERVER.HomeAssistantAPIError):
                settings.save("binary_sensor.ok", {"enabled": True})
            self.assertEqual(path.read_text(encoding="utf-8"), "{broken")

    def test_display_name_trims_sensor_words(self) -> None:
        for friendly_name, expected in (
            ("Front Door Sensor", "Front Door"),
            ("Kitchen Window Contact Sensor", "Kitchen Window"),
            ("Patio Door Opening", "Patio Door"),
            ("FHT - Garage Door", "Garage Door"),
            ("Sensor", "Sensor"),
            ("", "Side Door"),
        ):
            with self.subTest(friendly_name=friendly_name):
                self.assertEqual(
                    SERVER.door_open_alert_display_name({"entity_id": "binary_sensor.side_door", "friendly_name": friendly_name}),
                    expected,
                )

    def test_manager_writes_door_reminders_with_house_mode_and_clear(self) -> None:
        settings = {
            "binary_sensor.front_door_sensor": {"enabled": True, "delay_minutes": 10, "when": "night_sleep", "alert_targets": ["siren.hallway_siren", "button.kitchen_chime_play_buzzer"], "unifi_webhook": True, "notification": True},
            "binary_sensor.kitchen_window": {"enabled": True, "delay_minutes": 0, "when": "any", "alert_targets": [], "notification": True},
            "binary_sensor.kitchen_fridge_door": {"enabled": True, "delay_minutes": 5, "when": "any", "notification": True},
            "binary_sensor.hall_motion": {"enabled": True, "notification": True},
            "binary_sensor.gone_sensor": {"enabled": True, "notification": True},
        }
        publisher = Mock()
        with tempfile.TemporaryDirectory() as directory, patch.dict(SERVER.os.environ, {"DEVICE_ALARM_WEBHOOK": "https://example.test/hook"}):
            package = Path(directory) / "future_homes_tech_door_open_alerts.yaml"
            manager = SERVER.DoorOpenAlertAutomationManager(package, publisher)
            automations = manager.sync(settings, self.ENTITIES)
            content = package.read_text(encoding="utf-8")
            publisher.reload_automations.assert_called_once()
            self.assertEqual(manager.sync(settings, self.ENTITIES), automations)
            publisher.reload_automations.assert_called_once()

        self.assertEqual(
            [item["entity_id"] for item in automations],
            ["binary_sensor.front_door_sensor", "binary_sensor.kitchen_window"],
        )
        self.assertEqual(automations[0]["name"], "Front Door")
        self.assertTrue(automations[0]["unique_id"].startswith(SERVER.DOOR_OPEN_ALERT_AUTOMATION_UNIQUE_ID_PREFIX))
        self.assertNotIn("siren_targets", automations[0])
        for excluded in ("kitchen_fridge_door", "hall_motion", "gone_sensor", SERVER.FRIDGE_ALARM_AUTOMATION_UNIQUE_ID_PREFIX):
            self.assertNotIn(excluded, content)
        self.assertIn("id: fht_door_open_alert_", content)
        self.assertIn('alias: "FHT - Front Door Left Open"', content)
        self.assertIn('alias: "FHT - Kitchen Window Left Open"', content)
        self.assertIn('title: "Door Left Open"', content)
        self.assertIn('message: "Front Door has been open for 10 minutes."', content)
        self.assertIn('message: "Kitchen Window is open."', content)
        self.assertIn("entity_id: input_select.fht_house_mode", content)
        self.assertIn('state: ["Night", "Sleep"]', content)
        self.assertIn("rest_command.fht_device_alarm_webhook", content)
        self.assertIn("persistent_notification.dismiss", content)
        try:
            import yaml
        except ImportError:
            return
        front, window = yaml.safe_load(content)["automation"]
        self.assertEqual(front["id"], automations[0]["unique_id"])
        self.assertEqual(front["mode"], "restart")
        self.assertEqual([trigger["id"] for trigger in front["triggers"]], ["alert", "house_mode", "clear"])
        self.assertEqual(front["triggers"][0]["for"], {"minutes": 10})
        self.assertEqual(front["triggers"][1]["to"], ["Night", "Sleep"])
        alert_branch, clear_branch = front["actions"][0]["choose"]
        self.assertEqual(
            alert_branch["conditions"][0],
            {"condition": "state", "entity_id": "input_select.fht_house_mode", "state": ["Night", "Sleep"]},
        )
        self.assertEqual(alert_branch["conditions"][1]["condition"], "or")
        self.assertEqual(
            alert_branch["conditions"][1]["conditions"][1]["conditions"][1],
            {"condition": "state", "entity_id": "binary_sensor.front_door_sensor", "state": "on", "for": {"minutes": 10}},
        )
        self.assertEqual(
            [action.get("action", "repeat") for action in alert_branch["sequence"]],
            ["persistent_notification.create", "siren.turn_on", "rest_command.fht_device_alarm_webhook", "repeat"],
        )
        self.assertEqual(
            alert_branch["sequence"][3]["repeat"]["while"],
            [{"condition": "state", "entity_id": "binary_sensor.front_door_sensor", "state": "on"}],
        )
        self.assertEqual(clear_branch["conditions"], [{"condition": "trigger", "id": "clear"}])
        self.assertEqual(
            [action["action"] for action in clear_branch["sequence"]],
            ["persistent_notification.dismiss", "siren.turn_off"],
        )
        self.assertEqual([trigger["id"] for trigger in window["triggers"]], ["alert", "clear"])
        self.assertNotIn("for", window["triggers"][0])
        window_alert = window["actions"][0]["choose"][0]
        self.assertEqual(window_alert["conditions"], [{"condition": "trigger", "id": "alert"}])
        self.assertEqual([action["action"] for action in window_alert["sequence"]], ["persistent_notification.create"])

    def test_manager_skips_silent_reminders_and_makes_notification_optional(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.dict(SERVER.os.environ, {"DEVICE_ALARM_WEBHOOK": ""}):
            package = Path(directory) / "doors.yaml"
            manager = SERVER.DoorOpenAlertAutomationManager(package)
            automations = manager.sync({
                "binary_sensor.front_door_sensor": {"enabled": False, "notification": True},
                "binary_sensor.kitchen_window": {"enabled": True, "notification": False, "alert_targets": [], "unifi_webhook": True},
            }, self.ENTITIES)
            self.assertEqual(automations, [])
            self.assertEqual(package.read_text(encoding="utf-8"), "# Managed by Future Homes Tech App.\nautomation: []\n")
            automations = manager.sync({
                "binary_sensor.kitchen_window": {"enabled": True, "notification": False, "alert_targets": ["siren.hallway_siren"], "delay_minutes": 2},
            }, self.ENTITIES)
            content = package.read_text(encoding="utf-8")
        self.assertEqual(len(automations), 1)
        self.assertNotIn("persistent_notification", content)
        self.assertIn("action: siren.turn_on", content)
        self.assertIn("action: siren.turn_off", content)
        self.assertIn("id: clear", content)

    def handler(self, directory: Path) -> SERVER.FutureHomesTechRequestHandler:
        handler = SERVER.FutureHomesTechRequestHandler.__new__(SERVER.FutureHomesTechRequestHandler)
        handler.inventory = Mock()
        handler.inventory.fetch.return_value = {"entities": self.ENTITIES, "stale": False}
        handler.room_aliases = Mock()
        handler.room_aliases.read.return_value = {"Entry": "Mudroom"}
        handler.door_open_alert_settings = SERVER.DoorOpenAlertSettings(directory / "door_open_alert_settings.json")
        handler.door_open_alert_automations = SERVER.DoorOpenAlertAutomationManager(directory / "door_open_alerts.yaml")
        handler.registry_organizer = Mock()
        handler._send_json = Mock()
        handler._request_is_allowed = Mock(return_value=True)
        return handler

    def test_payload_groups_sensors_by_room_and_keeps_missing_enabled_sensors(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.dict(SERVER.os.environ, {"DEVICE_ALARM_WEBHOOK": ""}):
            handler = self.handler(Path(directory))
            handler.door_open_alert_settings.save("binary_sensor.gone_sensor", {"enabled": True})
            handler.door_open_alert_settings.save("binary_sensor.also_gone", {"enabled": False})
            payload = handler._door_open_alert_payload()["door_open_alerts"]
        self.assertEqual([room["display_name"] for room in payload["rooms"]], ["Kitchen", "Mudroom", "Unassigned"])
        self.assertEqual(payload["rooms"][1]["area"], "Entry")
        self.assertEqual([sensor["entity_id"] for sensor in payload["rooms"][0]["sensors"]], ["binary_sensor.kitchen_window"])
        self.assertEqual(payload["rooms"][0]["sensors"][0]["display_name"], "Kitchen Window")
        self.assertEqual(payload["rooms"][0]["sensors"][0]["state"], "on")
        missing = payload["rooms"][2]["sensors"]
        self.assertEqual([sensor["entity_id"] for sensor in missing], ["binary_sensor.gone_sensor"])
        self.assertTrue(missing[0]["missing"])
        self.assertEqual(missing[0]["state"], "unavailable")
        self.assertEqual(payload["house_mode"], "Night")
        self.assertFalse(payload["webhook_configured"])
        self.assertEqual([item["entity_id"] for item in payload["alarm_targets"]["sirens"]], ["siren.hallway_siren"])
        self.assertEqual([item["entity_id"] for item in payload["alarm_targets"]["chimes"]], ["button.kitchen_chime_play_buzzer"])
        self.assertTrue(payload["settings"]["binary_sensor.gone_sensor"]["enabled"])

    def test_post_saves_reminder_writes_package_and_rejects_other_sensors(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.dict(SERVER.os.environ, {"DEVICE_ALARM_WEBHOOK": ""}):
            handler = self.handler(Path(directory))
            handler.path = "/api/door-open-alerts"
            handler._read_json_object = Mock(return_value={
                "entity_id": "binary_sensor.front_door_sensor",
                "enabled": True,
                "delay_minutes": 15,
                "when": "night",
                "alert_targets": ["button.kitchen_chime_play_buzzer"],
                "notification": True,
                "unifi_webhook": False,
            })
            handler._dispatch_POST()
            status, body = handler._send_json.call_args.args
            self.assertEqual(status, 200)
            self.assertTrue(body["saved"])
            self.assertTrue(body["activated"])
            self.assertEqual(body["settings"]["binary_sensor.front_door_sensor"]["when"], "night")
            self.assertEqual([item["entity_id"] for item in body["automations"]], ["binary_sensor.front_door_sensor"])
            content = (Path(directory) / "door_open_alerts.yaml").read_text(encoding="utf-8")
            self.assertIn('alias: "FHT - Front Door Left Open"', content)
            self.assertIn('["button.kitchen_chime_play_buzzer"]', content)
            handler.registry_organizer.categorize_automations.assert_called_once_with(attempts=1)
            for rejected in (
                {"entity_id": "binary_sensor.kitchen_fridge_door", "enabled": True},
                {"entity_id": "binary_sensor.hall_motion", "enabled": True},
                {"entity_id": "binary_sensor.unknown_door", "enabled": True},
                {"entity_id": "binary_sensor.front_door_sensor", "alert_targets": ["siren.unknown"]},
                {"entity_id": "binary_sensor.front_door_sensor", "when": "weekends"},
            ):
                with self.subTest(rejected=rejected):
                    handler._send_json.reset_mock()
                    handler._read_json_object = Mock(return_value=rejected)
                    handler._dispatch_POST()
                    self.assertEqual(handler._send_json.call_args.args[0], 400)
                    self.assertFalse(handler._send_json.call_args.args[1]["saved"])
            self.assertEqual(handler.door_open_alert_settings.read()["binary_sensor.front_door_sensor"]["delay_minutes"], 15)
            handler.door_open_alert_settings.save("binary_sensor.gone_sensor", {"enabled": True})
            handler._send_json.reset_mock()
            handler._read_json_object = Mock(return_value={"entity_id": "binary_sensor.gone_sensor", "enabled": False})
            handler._dispatch_POST()
            self.assertEqual(handler._send_json.call_args.args[0], 200)
            self.assertFalse(handler.door_open_alert_settings.read()["binary_sensor.gone_sensor"]["enabled"])

    def test_door_reminders_are_categorized_as_device_alarms(self) -> None:
        organizer = SERVER.HomeAssistantRegistryOrganizer(
            token="test-token",
            websocket_url="ws://homeassistant.test/api/websocket",
        )
        entities = [
            {"entity_id": "automation.fht_front_door_left_open", "unique_id": "fht_door_open_alert_1234567890abcdef", "categories": {}},
            {"entity_id": "automation.fht_front_door_lights", "unique_id": "fht_door_1234567890abcdef", "categories": {}},
        ]
        category_ids = {
            SERVER.DOOR_AUTOMATION_CATEGORY_NAME: "door-category",
            SERVER.SWITCH_AUTOMATION_CATEGORY_NAME: "switch-category",
            SERVER.SWITCH_ACTIVATION_CATEGORY_NAME: "activation-category",
            SERVER.LIGHT_SYNC_CATEGORY_NAME: "sync-category",
            SERVER.CLIMATE_AUTOMATION_CATEGORY_NAME: "climate-category",
            SERVER.PRESENCE_AUTOMATION_CATEGORY_NAME: "presence-category",
            SERVER.MOTION_AUTOMATION_CATEGORY_NAME: "motion-category",
            SERVER.SCENE_AUTOMATION_CATEGORY_NAME: "scene-category",
            SERVER.DEVICE_ALARM_AUTOMATION_CATEGORY_NAME: "device-alarm-category",
        }
        with patch.object(
            organizer,
            "_automation_category_id",
            side_effect=lambda name: category_ids[name],
        ), patch.object(
            organizer,
            "_commands",
            side_effect=[[entities], [{"entity_entry": entities[0]}, {"entity_entry": entities[1]}]],
        ) as mocked_commands:
            organizer.categorize_automations(attempts=1, retry_delay=0)
        self.assertEqual(
            mocked_commands.call_args_list[1].args[0],
            [
                {
                    "type": "config/entity_registry/update",
                    "entity_id": "automation.fht_front_door_left_open",
                    "categories": {"automation": "device-alarm-category"},
                },
                {
                    "type": "config/entity_registry/update",
                    "entity_id": "automation.fht_front_door_lights",
                    "categories": {"automation": "door-category"},
                },
            ],
        )


class ActionCatalogGroupTests(unittest.TestCase):
    def test_retired_bathroom_group_is_not_an_action_choice(self):
        old = "light.fht_downstairs_bathroom_all_bathroom_lights"
        current = "light.fht_downstairs_bathroom_all_lights"
        entities = [
            {"entity_id": old, "domain": "light", "friendly_name": "Downstairs Bathroom All Bathroom Lights", "area": "Downstairs Bathroom", "members": ["light.vanity"]},
            {"entity_id": current, "domain": "light", "friendly_name": "Downstairs Bathroom All Lights", "area": "Downstairs Bathroom", "members": ["light.vanity", "light.toilet"]},
        ]
        for state in ["on", "unavailable"]:
            entities[0]["state"] = state
            catalog = SERVER.action_catalog_from_entities(entities)
            self.assertEqual([entity["entity_id"] for entity in catalog["light_groups"]], [current])
            self.assertIn(old, catalog["light_groups"][0]["action_aliases"])
            self.assertFalse(catalog["individual_lights"])
        self.assertFalse(SERVER.action_catalog_from_entities(entities[:1])["light_groups"])

    """Verify the shared action catalog exposes one canonical area group."""

    def test_area_less_legacy_groups_do_not_duplicate_renamed_room_choices(self) -> None:
        entities = bedroom_lights()
        SERVER.apply_room_aliases(entities, {"Bedroom 2": "Bailey’s Bedoom"})
        original = json.dumps(entities, sort_keys=True)
        saved = {"switch.bedroom_2_switch_1": ["light_group:light.bedroom_2_fan_lights"]}
        catalog = SERVER.action_catalog_from_entities(entities, saved_actions=saved)
        groups = {entity["entity_id"]: entity for entity in catalog["light_groups"]}
        self.assertEqual(set(groups), {
            "light.fht_bedroom_2_all_lights", "light.fht_bedroom_2_closet_lights",
            "light.fht_bedroom_2_fan_lights", "light.bedroom_2_headboard_lights",
        })
        self.assertEqual(groups["light.fht_bedroom_2_fan_lights"]["action_aliases"], ["light.bedroom_2_fan_lights"])
        self.assertEqual(len(catalog["individual_lights"]), 4)
        self.assertEqual(catalog["unavailable_targets"], [])
        self.assertEqual(json.dumps(entities, sort_keys=True), original)
        self.assertEqual(saved["switch.bedroom_2_switch_1"], ["light_group:light.bedroom_2_fan_lights"])

    def test_retired_fan_groups_resolve_to_only_generated_fan_choice(self) -> None:
        bulbs = ["light.bedroom_6_fan_light_1", "light.bedroom_6_fan_light_2"]
        entities = [
            {"entity_id": group, "domain": "light", "area": "Bedroom 6", "state": state,
             "friendly_name": name, "members": members}
            for group, state, name, members in (
                ("light.fht_bedroom_6_fan_lights", "off", "Bedroom 6 Fan Lights", bulbs),
                ("light.fht_bedroom_6_all_lights", "unavailable", "Bedroom 6 All Lights", []),
                ("light.bedroom_6_fan_lights", "unavailable", "Bedroom 6 Fan Lights", []),
            )
        ]
        catalog = SERVER.action_catalog_from_entities(entities)
        self.assertEqual([group["entity_id"] for group in catalog["light_groups"]], ["light.fht_bedroom_6_fan_lights"])

    def test_groups_no_longer_generated_are_not_offered(self) -> None:
        """Hide an old All Lights group that Home Assistant still remembers."""
        bulbs = ["light.bedroom_5_fan_light_1", "light.bedroom_5_fan_light_2"]
        entities = [
            *({"entity_id": bulb, "domain": "light", "area": "Bedroom 5", "friendly_name": name}
              for bulb, name in zip(bulbs, ("Bedroom 5 Fan Light 1", "Bedroom 5 Fan Light 2"))),
            {"entity_id": "light.fht_bedroom_5_fan_lights", "domain": "light", "area": "Bedroom 5",
             "state": "off", "friendly_name": "Bedroom 5 Fan Lights", "members": bulbs},
            # Left over from an earlier release: still on, no area, own members.
            {"entity_id": "light.fht_bedroom_5_all_lights", "domain": "light", "area": "",
             "state": "off", "friendly_name": "Bedroom 5 All Lights", "members": bulbs[:1]},
        ]
        saved = {"switch.bedroom_5": ["light_group:light.fht_bedroom_5_all_lights"]}
        catalog = SERVER.action_catalog_from_entities(
            entities, saved_actions=saved,
            generated_group_ids={"light.fht_bedroom_5_fan_lights"},
        )
        self.assertEqual([group["entity_id"] for group in catalog["light_groups"]], ["light.fht_bedroom_5_fan_lights"])
        self.assertIn("light.fht_bedroom_5_all_lights", catalog["light_groups"][0]["action_aliases"])

    def test_old_all_lights_folds_into_room_only_group(self) -> None:
        """An early-release All Lights group does not reappear beside Fan Lights."""
        bulbs = ["light.bedroom_4_fan_light_1", "light.bedroom_4_fan_light_2"]
        for legacy_area in ("Bedroom 4", ""):
            entities = [
                *({"entity_id": bulb, "domain": "light", "area": "Bedroom 4", "friendly_name": f"Bedroom 4 Fan Light {index}"}
                  for index, bulb in enumerate(bulbs, 1)),
                {"entity_id": "light.fht_bedroom_4_fan_lights", "domain": "light", "area": "Bedroom 4",
                 "state": "off", "friendly_name": "Bedroom 4 Fan Lights", "members": bulbs},
                {"entity_id": "light.bedroom_4_all_lights", "domain": "light", "area": legacy_area,
                 "state": "unavailable", "friendly_name": "Bedroom 4 All Lights"},
            ]
            catalog = SERVER.action_catalog_from_entities(
                entities, generated_group_ids={"light.fht_bedroom_4_fan_lights"})
            with self.subTest(legacy_area=legacy_area):
                self.assertEqual([group["entity_id"] for group in catalog["light_groups"]],
                                 ["light.fht_bedroom_4_fan_lights"])

    def test_single_light_all_lights_choice_uses_actual_light(self) -> None:
        entities = [
            {"entity_id": "light.laundry_light", "domain": "light", "friendly_name": "Laundry Room Light", "area": "Laundry Room"},
            {"entity_id": "light.fht_laundry_all_lights", "domain": "light", "friendly_name": "Laundry Room All Lights", "area": "Laundry Room", "members": ["light.laundry_light"]},
        ]
        catalog = SERVER.action_catalog_from_entities(entities)
        self.assertEqual(len(catalog["light_groups"]), 1)
        self.assertEqual(catalog["light_groups"][0]["entity_id"], "light.laundry_light")
        self.assertIn("light.fht_laundry_all_lights", catalog["light_groups"][0]["action_aliases"])
        self.assertNotIn("action_aliases", entities[0])

    def test_single_fixture_helper_uses_real_light(self) -> None:
        entities = [
            {"entity_id": "light.closet", "domain": "light", "friendly_name": "Master Bedroom Closet Light", "area": "Master Bedroom"},
            {"entity_id": "light.fht_closet", "domain": "light", "friendly_name": "FHT - Master Bedroom Closet Light", "area": "Master Bedroom", "members": ["light.closet"]},
        ]
        catalog = SERVER.action_catalog_from_entities(entities)
        self.assertEqual([item["entity_id"] for item in catalog["light_groups"]], ["light.closet"])
        self.assertIn("light.fht_closet", catalog["light_groups"][0]["action_aliases"])

    def test_stale_single_light_area_choices_use_actual_light(self) -> None:
        entities = [
            {"entity_id": "light.entry_light", "domain": "light", "friendly_name": "Entry Light", "area": "Entry", "state": "off"},
            {"entity_id": "light.entry_all_lights", "domain": "light", "friendly_name": "Entry All Lights", "area": "Entry", "state": "unavailable"},
            {"entity_id": "light.entry_lights", "domain": "light", "friendly_name": "Entry Lights", "area": "Entry", "state": "unavailable"},
        ]
        catalog = SERVER.action_catalog_from_entities(entities)
        self.assertEqual([item["entity_id"] for item in catalog["light_groups"]], ["light.entry_light"])
        self.assertEqual(set(catalog["light_groups"][0]["action_aliases"]), {"light.entry_all_lights", "light.entry_lights"})
        entities[1]["state"] = "on"
        catalog = SERVER.action_catalog_from_entities(entities)
        self.assertIn("light.entry_all_lights", [item["entity_id"] for item in catalog["light_groups"]])

    def test_shower_light_relative_alias_collapses_within_area(self) -> None:
        entities = [
            {"entity_id": "light.upstairs_shower", "domain": "light", "friendly_name": "Upstairs Bathroom Shower Light", "area": "Upstairs Bathroom", "state": "off"},
            {"entity_id": "light.old_shower_lights", "domain": "light", "friendly_name": "Shower Lights", "area": "Upstairs Bathroom", "state": "unavailable"},
            {"entity_id": "light.downstairs_shower", "domain": "light", "friendly_name": "Shower Light", "area": "Downstairs Bathroom", "state": "off"},
        ]
        catalog = SERVER.action_catalog_from_entities(entities)
        groups = {item["entity_id"]: item for item in catalog["light_groups"]}
        self.assertEqual(set(groups), {"light.upstairs_shower", "light.downstairs_shower"})
        self.assertIn("light.old_shower_lights", groups["light.upstairs_shower"]["action_aliases"])
        self.assertNotIn("action_aliases", groups["light.downstairs_shower"])

    def test_presence_room_mode_override_persists_and_generates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SERVER.PresenceModeSettings(Path(directory) / 'settings.json')
            store.save('binary_sensor.presence', {'chill': {'enabled': True, 'brightness': 35}})
            settings = store.read()
            self.assertEqual(settings['binary_sensor.presence']['chill']['brightness'], 35)
            path = Path(directory) / 'presence.yaml'
            manager = SERVER.PresenceAutomationManager(path)
            entities = [{'entity_id': 'binary_sensor.presence', 'area': 'Bedroom 1'}]
            manager.sync({'binary_sensor.presence': ['light.bed']}, entities, mode_settings=settings, room_modes={'Bedroom 1': ['chill']})
            content = path.read_text()
            self.assertIn('input_select.fht_bedroom_1_mode', content)
            self.assertIn("room_mode in ['chill']", content)
            self.assertIn('input_select.fht_house_mode', content)
            manager.sync({'binary_sensor.presence': ['light.bed']}, entities, mode_settings=settings, room_modes={'Bedroom 1': []})
            self.assertNotIn('input_select.fht_bedroom_1_mode', path.read_text())

    def test_stairway_single_light_choices_collapse(self) -> None:
        entities = [
            {"entity_id": "light.stairway_light", "domain": "light", "friendly_name": "Light", "area": "Stairway", "state": "off"},
            {"entity_id": "light.stairway_all_lights", "domain": "light", "friendly_name": "All Lights", "area": "Stairway", "state": "unavailable"},
            {"entity_id": "light.stairway_lights", "domain": "light", "friendly_name": "Lights", "area": "Stairway", "members": ["light.stairway_light"], "state": "off"},
        ]
        catalog = SERVER.action_catalog_from_entities(entities)
        self.assertEqual([item["entity_id"] for item in catalog["light_groups"]], ["light.stairway_light"])
        self.assertEqual(set(catalog["light_groups"][0]["action_aliases"]), {"light.stairway_all_lights", "light.stairway_lights"})

    def test_kitchen_retired_switch_groups_and_indicators_are_not_choices(self) -> None:
        stale = ["light.kitchen_1g_lights", "light.kitchen_switch_1g_load_control_lights", "light.kitchen_switch_1g_rgb_indicator_lights"]
        entities = [{"entity_id": entity_id, "domain": "light", "state": "unavailable", "members": []} for entity_id in stale]
        entities.extend([
            {"entity_id": "light.kitchen_switch_rgb_light", "domain": "light", "state": "off"},
            {"entity_id": "light.kitchen_switch_under_cabinet_light_1", "domain": "light", "state": "off"},
            {"entity_id": "light.kitchen_rgb_strip", "domain": "light", "state": "off"},
        ])
        catalog = SERVER.action_catalog_from_entities(entities)
        choices = {item["entity_id"] for item in catalog["light_groups"] + catalog["individual_lights"]}
        self.assertEqual(choices, {"light.kitchen_switch_under_cabinet_light_1", "light.kitchen_rgb_strip"})
        self.assertEqual(entities[0]["state"], "unavailable")

    def test_action_modes_use_only_enabled_admin_modes(self) -> None:
        catalog = SERVER.action_catalog_from_entities([], bedroom_areas=["Bedroom 2", "Bedroom 6"], enabled_room_modes={"Bedroom 2": ["movie", "sleep"]})
        self.assertEqual(len(catalog["room_modes"]), 1)
        self.assertEqual(catalog["room_modes"][0]["options"], ["Sleep", "Movie"])
        self.assertEqual(catalog["room_modes"][0]["entity_id"], "input_select.fht_bedroom_2_mode")

    def test_wired_load_mapping_uses_registry_link_not_device_name(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            storage = root / ".storage"
            storage.mkdir()
            entities = [
                {"id": "source-uuid", "entity_id": "switch.closet_1", "hidden_by": "integration", "device_id": "multi"},
                {"id": "other-uuid", "entity_id": "switch.closet_2", "device_id": "multi"},
                {"entity_id": "light.renamed_closet", "platform": "switch_as_x", "config_entry_id": "wrapper"},
            ]
            (storage / "core.entity_registry").write_text(json.dumps({"data": {"entities": entities}}))
            for source in ["source-uuid", "switch.closet_1"]:
                (storage / "core.config_entries").write_text(json.dumps({"data": {"entries": [{"entry_id": "wrapper", "domain": "switch_as_x", "options": {"entity_id": source}}]}}))
                metadata = SERVER.entity_control_metadata_from_storage(root)
                self.assertEqual(metadata["switch.closet_1"]["wired_load_ids"], ["light.renamed_closet"])
                self.assertEqual(metadata["switch.closet_1"]["wired_load_names"], {"light.renamed_closet": "Renamed Closet"})
                self.assertNotIn("wired_load_ids", metadata["switch.closet_2"])
            entities[0]["disabled_by"] = "user"
            (storage / "core.entity_registry").write_text(json.dumps({"data": {"entities": entities}}))
            self.assertNotIn("wired_load_ids", SERVER.entity_control_metadata_from_storage(root)["switch.closet_1"])

    def test_same_labels_in_other_rooms_or_ambiguous_unassigned_groups_remain(self) -> None:
        entities = [
            {"entity_id": "light.fht_kitchen_all_lights", "domain": "light", "friendly_name": "All Lights", "area": "Kitchen"},
            {"entity_id": "light.fht_office_all_lights", "domain": "light", "friendly_name": "All Lights", "area": "Office"},
            {"entity_id": "light.other_all_lights", "domain": "light", "friendly_name": "All Lights", "area": None},
            {"entity_id": "light.kitchen_all_lights", "domain": "light", "friendly_name": "All Lights", "area": "Workshop"},
        ]
        catalog = SERVER.action_catalog_from_entities(entities)
        self.assertEqual({entity["entity_id"] for entity in catalog["light_groups"]}, {entity["entity_id"] for entity in entities})

    def test_generic_lights_alias_without_area_uses_all_lights_choice(self) -> None:
        for room, slug, alias in (("Dining Room", "dining_room", "Dining Room"), ("Bedroom 2", "bedroom_2", "Bailey’s Bedoom")):
            with self.subTest(room=room):
                entities = [
                    {"entity_id": f"light.fht_{slug}_all_lights", "domain": "light", "friendly_name": f"{room} All Lights", "area": room, "members": [f"light.{slug}_light_1", f"light.{slug}_light_2"]},
                    {"entity_id": f"light.{slug}_lights", "domain": "light", "friendly_name": f"{room} Lights", "area": None, "members": []},
                    {"entity_id": f"light.{slug}_porch_lights", "domain": "light", "friendly_name": f"{room} Porch Lights", "area": room, "members": []},
                ]
                SERVER.apply_room_aliases(entities, {room: alias})
                catalog = SERVER.action_catalog_from_entities(entities)
                groups = {entity["entity_id"]: entity for entity in catalog["light_groups"]}
                self.assertEqual(set(groups), {f"light.fht_{slug}_all_lights", f"light.{slug}_porch_lights"})
                self.assertEqual(groups[f"light.fht_{slug}_all_lights"]["action_aliases"], [f"light.{slug}_lights"])
                entities[1]["area"] = alias
                assigned_catalog = SERVER.action_catalog_from_entities(entities)
                self.assertEqual({entity["entity_id"] for entity in assigned_catalog["light_groups"]}, set(groups))

    def test_hides_legacy_generic_groups_when_fht_all_lights_exists(self) -> None:
        entities = [
            {
                "entity_id": "light.fht_pantry_all_lights",
                "domain": "light",
                "friendly_name": "Pantry All Lights",
                "area": "Pantry",
                "members": ["light.pantry_light_1", "light.pantry_light_2"],
            },
            {
                "entity_id": "light.pantry_all_lights",
                "domain": "light",
                "friendly_name": "All Lights",
                "area": "Pantry",
                "members": [],
            },
            {
                "entity_id": "light.pantry_lights",
                "domain": "light",
                "friendly_name": "Lights",
                "area": "Pantry",
                "members": [],
            },
        ]

        catalog = SERVER.action_catalog_from_entities(entities)

        self.assertEqual(
            [entity["entity_id"] for entity in catalog["light_groups"]],
            ["light.fht_pantry_all_lights"],
        )

    def test_prefers_fht_group_when_room_and_name_are_duplicated(self) -> None:
        entities = [
            {"entity_id": "light.bailey_all_lights", "domain": "light", "friendly_name": "All Lights — Bailey's Bedroom", "area": "Bailey's Bedroom"},
            {"entity_id": "light.fht_bailey_all_lights", "domain": "light", "friendly_name": "Bailey's Bedroom All Lights", "area": "Bailey's Bedroom"},
        ]

        catalog = SERVER.action_catalog_from_entities(entities)

        self.assertEqual(
            [entity["entity_id"] for entity in catalog["light_groups"]],
            ["light.fht_bailey_all_lights"],
        )


class FloorRegistryTests(unittest.TestCase):
    """Verify Home Configurator uses Home Assistant Floor assignments."""

    def test_whole_home_floor_always_sorts_first(self) -> None:
        """Keep Whole Home above physical floors regardless of its level."""
        floors = [
            {"name": "Unassigned", "level": None},
            {"name": "Second Floor", "level": 1},
            {"name": "Whole Home", "level": None},
            {"name": "First Floor", "level": 0},
        ]

        ordered = sorted(floors, key=SERVER.home_configurator_floor_sort_key)

        self.assertEqual(
            [floor["name"] for floor in ordered],
            ["Whole Home", "First Floor", "Second Floor", "Unassigned"],
        )

    def test_entity_area_override_to_deleted_area_uses_device_area(self) -> None:
        """Keep a sensor in its device's room when its own area was deleted."""
        with tempfile.TemporaryDirectory() as directory:
            storage = Path(directory) / ".storage"
            storage.mkdir()
            storage.joinpath("core.area_registry").write_text(json.dumps({"data": {"areas": [
                {"area_id": "stairway", "name": "Stairway"},
                {"area_id": "hall", "name": "Hall"}]}}), encoding="utf-8")
            storage.joinpath("core.device_registry").write_text(json.dumps({"data": {"devices": [
                {"id": "pir-1", "area_id": "stairway"}]}}), encoding="utf-8")
            storage.joinpath("core.entity_registry").write_text(json.dumps({"data": {"entities": [
                {"entity_id": "binary_sensor.stairway_pir_1", "device_id": "pir-1", "area_id": "deleted_room"},
                {"entity_id": "binary_sensor.stairway_pir_1_light", "device_id": "pir-1", "area_id": "hall"},
            ]}}), encoding="utf-8")

            areas = SERVER.entity_areas_from_storage(Path(directory))

        self.assertEqual(areas["binary_sensor.stairway_pir_1"], "Stairway")
        self.assertEqual(areas["binary_sensor.stairway_pir_1_light"], "Hall")

    def test_maps_entities_to_floor_through_their_device_area(self) -> None:
        """Resolve a device Area to its configured Floor display name."""
        with tempfile.TemporaryDirectory() as directory:
            storage = Path(directory) / ".storage"
            storage.mkdir()
            storage.joinpath("core.floor_registry").write_text(
                json.dumps({"data": {"floors": [{
                    "floor_id": "first_floor",
                    "name": "First Floor",
                }]}}),
                encoding="utf-8",
            )
            storage.joinpath("core.area_registry").write_text(
                json.dumps({"data": {"areas": [{
                    "area_id": "kitchen",
                    "name": "Kitchen",
                    "floor_id": "first_floor",
                }]}}),
                encoding="utf-8",
            )
            storage.joinpath("core.device_registry").write_text(
                json.dumps({"data": {"devices": [{
                    "id": "kitchen-switch",
                    "area_id": "kitchen",
                }]}}),
                encoding="utf-8",
            )
            storage.joinpath("core.entity_registry").write_text(
                json.dumps({"data": {"entities": [{
                    "entity_id": "switch.kitchen_switch_1",
                    "device_id": "kitchen-switch",
                }]}}),
                encoding="utf-8",
            )

            self.assertEqual(
                SERVER.entity_floors_from_storage(Path(directory)),
                {"switch.kitchen_switch_1": "First Floor"},
            )


class PresenceGroupManagerTests(unittest.TestCase):
    """Verify grouped presence helper generation."""

    def test_groups_numbered_occupancy_channels_by_device(self) -> None:
        """Create one occupancy helper that is on when any member is on."""
        with tempfile.TemporaryDirectory() as directory:
            config_directory = Path(directory)
            storage_directory = config_directory / ".storage"
            storage_directory.mkdir()
            storage_directory.joinpath("core.area_registry").write_text(
                json.dumps({"data": {"areas": [{
                    "area_id": "upstairs_bathroom",
                    "name": "Upstairs Bathroom",
                }]}}),
                encoding="utf-8",
            )
            storage_directory.joinpath("core.device_registry").write_text(
                json.dumps({"data": {"devices": [{
                    "id": "presence-device",
                    "name_by_user": "Upstairs Bathroom Presence 1",
                    "area_id": "upstairs_bathroom",
                }]}}),
                encoding="utf-8",
            )
            storage_directory.joinpath("core.entity_registry").write_text(
                json.dumps({"data": {"entities": [
                    {
                        "entity_id": "binary_sensor.upstairs_bathroom_presence_1_occupancy",
                        "device_id": "presence-device",
                        "original_name": "Occupancy",
                        "original_device_class": "occupancy",
                    },
                    {
                        "entity_id": "binary_sensor.upstairs_bathroom_presence_1_occupancy_2",
                        "device_id": "presence-device",
                        "original_name": "Occupancy 2",
                        "original_device_class": "occupancy",
                    },
                    {
                        "entity_id": "binary_sensor.upstairs_bathroom_presence_1_occupancy_3",
                        "device_id": "presence-device",
                        "original_name": "Occupancy 3",
                        "original_device_class": "occupancy",
                    },
                ]}}),
                encoding="utf-8",
            )
            output_path = config_directory / "presence_groups.yaml"
            manager = SERVER.PresenceGroupManager(output_path, config_directory)

            changed, groups = manager.sync()

            self.assertTrue(changed)
            self.assertEqual(len(groups), 1)
            self.assertEqual(
                groups[0]["entity_id"],
                "binary_sensor.fht_upstairs_bathroom_presence_1_group_presence",
            )
            self.assertEqual(groups[0]["area"], "Upstairs Bathroom")
            content = output_path.read_text(encoding="utf-8")
            self.assertIn("device_class: occupancy", content)
            self.assertIn("fht_presence_members: >-", content)
            self.assertIn(
                "{{ [\"binary_sensor.upstairs_bathroom_presence_1_occupancy\"",
                content,
            )
            self.assertIn(
                "binary_sensor.upstairs_bathroom_presence_1_occupancy_3",
                content,
            )
            self.assertIn("selectattr('state', 'eq', 'on')", content)

    def test_camera_motion_is_not_grouped_as_presence(self) -> None:
        """Leave camera motion and person sensors out of presence groups."""
        with tempfile.TemporaryDirectory() as directory:
            config_directory = Path(directory)
            storage_directory = config_directory / ".storage"
            storage_directory.mkdir()
            storage_directory.joinpath("core.area_registry").write_text(
                json.dumps({"data": {"areas": [{"area_id": "garage", "name": "Garage"}]}}), encoding="utf-8")
            storage_directory.joinpath("core.device_registry").write_text(
                json.dumps({"data": {"devices": [
                    {"id": "presence-1", "name_by_user": "Garage Presence 1", "area_id": "garage"},
                    {"id": "presence-2", "name_by_user": "Garage Presence 2", "area_id": "garage"},
                    {"id": "g4", "name": "Garage G4 Pro", "area_id": "garage"},
                ]}}), encoding="utf-8")
            storage_directory.joinpath("core.entity_registry").write_text(
                json.dumps({"data": {"entities": [
                    {"entity_id": "binary_sensor.garage_presence_1_occupancy", "device_id": "presence-1",
                     "original_name": "Occupancy", "original_device_class": "occupancy"},
                    {"entity_id": "binary_sensor.garage_presence_2_occupancy", "device_id": "presence-2",
                     "original_name": "Occupancy", "original_device_class": "occupancy"},
                    {"entity_id": "camera.garage_g4_pro_high", "device_id": "g4"},
                    {"entity_id": "binary_sensor.garage_g4_pro_motion", "device_id": "g4",
                     "original_name": "Motion", "original_device_class": "motion"},
                    {"entity_id": "binary_sensor.garage_g4_pro_person_detected", "device_id": "g4",
                     "original_name": "Person detected", "original_device_class": "occupancy"},
                ]}}), encoding="utf-8")
            output_path = config_directory / "presence_groups.yaml"
            _changed, groups = SERVER.PresenceGroupManager(output_path, config_directory).sync()
            content = output_path.read_text(encoding="utf-8")
        self.assertEqual(len(groups), 1)
        self.assertIn("binary_sensor.garage_presence_2_occupancy", content)
        self.assertNotIn("g4_pro", content)

    def test_groups_separately_numbered_presence_devices(self) -> None:
        """Combine Presence 1 and Presence 2 into one room presence helper."""
        with tempfile.TemporaryDirectory() as directory:
            config_directory = Path(directory)
            storage_directory = config_directory / ".storage"
            storage_directory.mkdir()
            storage_directory.joinpath("core.area_registry").write_text(
                json.dumps({"data": {"areas": [{
                    "area_id": "bathroom_1",
                    "name": "Bathroom 1",
                }]}}),
                encoding="utf-8",
            )
            storage_directory.joinpath("core.device_registry").write_text(
                json.dumps({"data": {"devices": [
                    {
                        "id": "presence-1",
                        "name_by_user": "Bathroom 1 Presence 1",
                        "area_id": "bathroom_1",
                    },
                    {
                        "id": "presence-2",
                        "name_by_user": "Bathroom 1 Presence 2",
                        "area_id": "bathroom_1",
                    },
                ]}}),
                encoding="utf-8",
            )
            storage_directory.joinpath("core.entity_registry").write_text(
                json.dumps({"data": {"entities": [
                    {
                        "entity_id": "binary_sensor.bathroom_1_presence_1_occupancy_2",
                        "device_id": "presence-1",
                        "original_name": "Occupancy (2)",
                        "original_device_class": "occupancy",
                    },
                    {
                        "entity_id": "binary_sensor.bathroom_1_presence_2_occupancy_2",
                        "device_id": "presence-2",
                        "original_name": "Occupancy (2)",
                        "original_device_class": "occupancy",
                    },
                ]}}),
                encoding="utf-8",
            )
            manager = SERVER.PresenceGroupManager(
                config_directory / "presence_groups.yaml",
                config_directory,
            )

            _changed, groups = manager.sync()

        self.assertEqual(len(groups), 1)
        self.assertEqual(
            groups[0]["entity_id"],
            "binary_sensor.fht_bathroom_1_presence_group",
        )
        self.assertEqual(
            groups[0]["friendly_name"],
            "FHT - Bathroom 1 Presence Group",
        )
        self.assertEqual(len(groups[0]["members"]), 2)


class PresenceModeSettingsTests(unittest.TestCase):
    """Verify mode-aware presence configuration and automation output."""

    def test_defaults_match_day_night_sleep_behavior(self) -> None:
        """Default to no daytime action, 80 percent at night, and 25 in Sleep."""
        setting = SERVER.PresenceModeSettings.normalize({})

        self.assertFalse(setting["day"]["enabled"])
        self.assertEqual(setting["day"]["brightness"], 100)
        self.assertTrue(setting["night"]["enabled"])
        self.assertEqual(setting["night"]["brightness"], 80)
        self.assertTrue(setting["sleep"]["enabled"])
        self.assertEqual(setting["sleep"]["brightness"], 25)
        with self.assertRaisesRegex(ValueError, "between 1 and 100"):
            SERVER.PresenceModeSettings.normalize(
                {"night": {"brightness": 0}}
            )

    def test_tone_defaults_to_current_and_validates(self) -> None:
        """Every rule keeps the lights' current colour until a tone is chosen."""
        setting = SERVER.PresenceModeSettings.normalize({"night": {"brightness": 40}})
        for mode in ("day", "night", "sleep"):
            self.assertEqual(setting[mode]["color_mode"], "current")
            self.assertEqual(setting[mode]["color_kelvin"], 4000)
        chosen = SERVER.PresenceModeSettings.normalize({
            "night": {"color_mode": "kelvin", "color_kelvin": 2700},
            "sleep": {"color_mode": "Adaptive"},
        })
        self.assertEqual(chosen["night"]["color_mode"], "kelvin")
        self.assertEqual(chosen["night"]["color_kelvin"], 2700)
        self.assertEqual(chosen["sleep"]["color_mode"], "adaptive")
        with self.assertRaisesRegex(ValueError, "current, kelvin, or adaptive"):
            SERVER.PresenceModeSettings.normalize({"night": {"color_mode": "rgb"}})
        with self.assertRaisesRegex(ValueError, "2000 and 6500"):
            SERVER.PresenceModeSettings.normalize({"night": {"color_mode": "kelvin", "color_kelvin": 1500}})
        with self.assertRaisesRegex(ValueError, "whole Kelvin"):
            SERVER.PresenceModeSettings.normalize({"night": {"color_kelvin": "warm"}})

    def test_saved_rules_without_a_tone_read_back_as_current(self) -> None:
        """Rules saved before tones existed keep behaving exactly as before."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "presence_mode_settings.json"
            path.write_text(json.dumps({"binary_sensor.hall": {"night": {"enabled": True, "brightness": 60}}}), encoding="utf-8")
            settings = SERVER.PresenceModeSettings(path).read()
        self.assertEqual(
            settings["binary_sensor.hall"]["night"],
            {"enabled": True, "brightness": 60, "color_mode": "current", "color_kelvin": 4000},
        )

    def test_light_supports_tone_follows_inventory_colour_modes(self) -> None:
        """Tones reach colour lights, FHT groups, and lights the inventory cannot describe."""
        by_id = {entity["entity_id"]: entity for entity in [
            {"entity_id": "light.strip", "supported_color_modes": ["color_temp"]},
            {"entity_id": "light.rgb", "supported_color_modes": ["hs"]},
            {"entity_id": "light.plain", "supported_color_modes": ["brightness"]},
            {"entity_id": "light.onoff", "supported_color_modes": ["onoff"]},
            {"entity_id": "light.unavailable", "supported_color_modes": []},
            {"entity_id": "light.ranged", "supported_color_modes": ["brightness"], "min_color_temp_kelvin": 2000},
            {"entity_id": "light.mixed_group", "supported_color_modes": ["brightness"], "members": ["light.plain", "light.strip"]},
            {"entity_id": "light.plain_group", "supported_color_modes": ["brightness"], "members": ["light.plain", "light.onoff"]},
            {"entity_id": "light.loop", "supported_color_modes": ["brightness"], "members": ["light.loop"]},
        ]}
        for entity_id in ("light.strip", "light.rgb", "light.unavailable", "light.unknown", "light.ranged",
                          "light.fht_hall_all_lights", "light.mixed_group"):
            self.assertTrue(SERVER.light_supports_tone(entity_id, by_id), entity_id)
        for entity_id in ("light.plain", "light.onoff", "light.plain_group", "light.loop"):
            self.assertFalse(SERVER.light_supports_tone(entity_id, by_id), entity_id)
        setting = {"brightness_pct": 50, "color_mode": "kelvin", "color_kelvin": 2700}
        self.assertEqual(SERVER.tone_aware_light_setting(setting, "light.strip", by_id), setting)
        self.assertEqual(SERVER.tone_aware_light_setting(setting, "light.plain", by_id)["color_mode"], "current")

    def test_presence_tone_reaches_only_lights_that_can_show_it(self) -> None:
        """Apply the mode's Kelvin or daylight tone with each turn_on, only to colour lights."""
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "presence.yaml"
            SERVER.PresenceAutomationManager(output).sync(
                {"binary_sensor.kitchen_presence": [
                    "light.kitchen_strip", "light.kitchen_plain", "light.fht_kitchen_all_lights", "switch.kitchen_fan",
                ]},
                [
                    {"entity_id": "binary_sensor.kitchen_presence", "friendly_name": "Kitchen Presence"},
                    {"entity_id": "light.kitchen_strip", "friendly_name": "Strip", "supported_color_modes": ["color_temp", "hs"]},
                    {"entity_id": "light.kitchen_plain", "friendly_name": "Plain", "supported_color_modes": ["brightness"]},
                    {"entity_id": "switch.kitchen_fan", "friendly_name": "Fan"},
                ],
                mode_settings={"binary_sensor.kitchen_presence": {
                    "night": {"enabled": True, "brightness": 80, "color_mode": "kelvin", "color_kelvin": 2700},
                    "sleep": {"enabled": True, "brightness": 25, "color_mode": "adaptive"},
                }},
                reload_automations=False,
            )
            content = output.read_text(encoding="utf-8")

        def block(name: str) -> str:
            return next(part for part in content.split("\n  - id: ") if f"\\u2192 {name}\"" in part)

        strip, plain, group, fan = (block(name) for name in ("Strip", "Plain", "light.fht_kitchen_all_lights", "Fan"))
        self.assertIn('fht_tone: "{% set tone = {\\"night\\": 2700, \\"sleep\\": \\"adaptive\\"}.get(fht_mode) %}', strip)
        self.assertIn("state_attr('sun.sun', 'elevation')", strip)
        # Detected, mode changed, and the saved-settings re-apply all carry the tone.
        self.assertEqual(strip.count("dict(data, color_temp_kelvin=fht_tone | int)"), 3)
        self.assertEqual(group.count("dict(data, color_temp_kelvin=fht_tone | int)"), 3)
        for untouched in (plain, fan):
            self.assertNotIn("fht_tone", untouched)
            self.assertNotIn("color_temp_kelvin", untouched)
        self.assertEqual(plain.count('brightness_pct: "{{ fht_brightness | int }}"'), 3)
        try:
            import jinja2
            import yaml
        except ImportError:
            self.skipTest("PyYAML and Jinja2 are needed to render the templates")
        automation = next(item for item in yaml.safe_load(content)["automation"] if item["alias"].endswith("Strip"))
        environment = jinja2.Environment()
        environment.globals["state_attr"] = lambda entity_id, attribute: 20.0
        tone_template = automation["actions"][0]["variables"]["fht_tone"]
        data_template = automation["actions"][1]["choose"][1]["sequence"][-1]["data"]
        self.assertEqual(environment.from_string(tone_template).render(fht_mode="night"), "2700")
        self.assertEqual(environment.from_string(tone_template).render(fht_mode="day"), "")
        self.assertEqual(environment.from_string(tone_template).render(fht_mode="sleep"), "4392.0")
        self.assertEqual(
            environment.from_string(data_template).render(fht_brightness=80, fht_tone=2700),
            "{'brightness_pct': 80, 'color_temp_kelvin': 2700}",
        )
        self.assertEqual(
            environment.from_string(data_template).render(fht_brightness=100, fht_tone=""),
            "{'brightness_pct': 100}",
        )

    def test_presence_without_a_tone_keeps_the_previous_automation(self) -> None:
        """Rules left at Current generate the same automation as before."""
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "presence.yaml"
            SERVER.PresenceAutomationManager(output).sync(
                {"binary_sensor.hall_presence": "light.hall_strip"},
                [
                    {"entity_id": "binary_sensor.hall_presence", "friendly_name": "Hall Presence"},
                    {"entity_id": "light.hall_strip", "friendly_name": "Hall Strip", "supported_color_modes": ["color_temp"]},
                ],
                mode_settings={"binary_sensor.hall_presence": {"night": {"enabled": True, "brightness": 50, "color_mode": "current", "color_kelvin": 2700}}},
                reload_automations=False,
            )
            content = output.read_text(encoding="utf-8")
        self.assertNotIn("fht_tone", content)
        self.assertNotIn("color_temp_kelvin", content)
        self.assertEqual(content.count('brightness_pct: "{{ fht_brightness | int }}"'), 3)

    def test_generates_house_mode_aware_presence_automation(self) -> None:
        """Apply the active house mode brightness and react to mode changes."""
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "presence.yaml"
            manager = SERVER.PresenceAutomationManager(output)
            automations = manager.sync(
                {"binary_sensor.kitchen_presence": "light.fht_kitchen_lights"},
                [
                    {
                        "entity_id": "binary_sensor.kitchen_presence",
                        "friendly_name": "Kitchen Presence",
                    },
                    {
                        "entity_id": "light.fht_kitchen_lights",
                        "friendly_name": "Kitchen Lights",
                    },
                ],
                {
                    "binary_sensor.kitchen_presence": {
                        "activation_delay": 2,
                        "clear_delay": 30,
                    }
                },
                {
                    "binary_sensor.kitchen_presence": {
                        "day": {"enabled": False, "brightness": 100},
                        "night": {"enabled": True, "brightness": 80},
                        "sleep": {"enabled": True, "brightness": 25},
                    }
                },
            )
            content = output.read_text(encoding="utf-8")

        self.assertEqual(len(automations), 1)
        self.assertIn(SERVER.HOUSE_MODE_HELPER, content)
        self.assertIn('\\"night\\": 80', content)
        self.assertIn('\\"sleep\\": 25', content)
        self.assertIn("id: mode_changed", content)
        self.assertIn("brightness_pct: \"{{ fht_brightness | int }}\"", content)
        self.assertIn("- delay: 2", content)
        self.assertIn("- delay: 30", content)

    def test_child_presence_holds_parent_group_lights_only(self) -> None:
        """A child keeps its parent group's lights on but controls its own light freely."""
        toilet = "binary_sensor.bathroom_toilet_presence"
        group = "binary_sensor.fht_bathroom_presence_group"
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "presence.yaml"
            manager = SERVER.PresenceAutomationManager(output)
            manager.sync(
                {toilet: "light.bathroom_toilet", group: "light.bathroom"},
                [
                    {"entity_id": toilet, "friendly_name": "Bathroom Toilet Presence", "area": "Bathroom"},
                    {"entity_id": group, "friendly_name": "Bathroom Presence Group", "area": "Bathroom",
                     "members": ["binary_sensor.bathroom_presence_1"]},
                    {"entity_id": "light.bathroom_toilet", "friendly_name": "Bathroom Toilet Lights"},
                    {"entity_id": "light.bathroom", "friendly_name": "Bathroom Lights"},
                ],
                {
                    toilet: {"activation_delay": 0, "clear_delay": 0, "parent_groups": [group]},
                    group: {"activation_delay": 0, "clear_delay": 60, "parent_groups": []},
                },
                reload_automations=False,
            )
            content = output.read_text(encoding="utf-8")

        automations = content.split("\n  - id: ")
        toilet_automation = next(block for block in automations if "Bathroom Toilet Presence \\u2192" in block or "Bathroom Toilet Presence →" in block)
        group_automation = next(block for block in automations if "Bathroom Presence Group" in block and "child presence hold" not in block)
        hold_automation = next(block for block in automations if "child presence hold" in block)
        # The toilet turns its own light off without waiting for the bathroom.
        self.assertNotIn(group, toilet_automation)
        # The bathroom waits for the toilet before turning its lights off...
        self.assertIn(f"entity_id: {toilet}\n                state: \"off\"", group_automation)
        # ...but the toilet never turns the bathroom lights on.
        self.assertNotIn(f"entity_id: {toilet}\n        to: \"on\"", group_automation)
        # When the toilet clears last, the bathroom lights still turn off.
        self.assertIn(f'entity_id: ["{toilet}"]\n        to: "off"', hold_automation)
        self.assertIn("- delay: 60", hold_automation)
        self.assertIn(f'entity_id: ["{group}", "{toilet}"]\n        state: "off"', hold_automation)
        self.assertIn("action: light.turn_off\n        target:\n          entity_id: light.bathroom", hold_automation)

    def test_sleep_number_beds_are_not_presence(self) -> None:
        """Skip Sleep Number bed sensors even when a saved choice exists."""
        self.assertTrue(SERVER.is_sleep_number_entity("binary_sensor.sleepnumber_bed_carl_is_in_bed"))
        self.assertTrue(SERVER.is_sleep_number_entity("binary_sensor.master_bed", "SleepIQ Master Bed"))
        self.assertFalse(SERVER.is_sleep_number_entity("binary_sensor.master_bedroom_presence_1", "Sleep Mode"))
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "presence.yaml"
            automations = SERVER.PresenceAutomationManager(output).sync(
                {"binary_sensor.sleepnumber_bed_carl_is_in_bed": "light.master"},
                [{"entity_id": "binary_sensor.sleepnumber_bed_carl_is_in_bed", "friendly_name": "SleepNumber Bed Carl Is In Bed"},
                 {"entity_id": "light.master", "friendly_name": "Master Lights"}],
                reload_automations=False,
            )
        self.assertEqual(automations, [])

    def test_camera_motion_is_not_presence(self) -> None:
        """Skip camera sensors, found by device or name, even when a saved choice exists."""
        cameras = {"cam-1"}
        self.assertTrue(SERVER.is_camera_entity({"entity_id": "binary_sensor.garage_g4_motion", "device_id": "cam-1"}, cameras))
        self.assertTrue(SERVER.is_camera_entity({"entity_id": "binary_sensor.front_door_doorbell_motion"}, set()))
        self.assertTrue(SERVER.is_camera_entity({"entity_id": "binary_sensor.x", "device_name": "Driveway Camera"}, set()))
        # UniFi Protect's UP-Sense and ordinary presence sensors have no camera.
        self.assertFalse(SERVER.is_camera_entity({"entity_id": "binary_sensor.hall_sense_motion", "device_id": "sense"}, cameras))
        self.assertFalse(SERVER.is_camera_entity({"entity_id": "binary_sensor.camden_room_presence", "friendly_name": "Camden Room Presence"}, cameras))
        self.assertEqual(SERVER.camera_device_ids([
            {"entity_id": "camera.garage_g4", "device_id": "cam-1"},
            {"entity_id": "binary_sensor.garage_g4_motion", "device_id": "cam-1"},
            {"entity_id": "binary_sensor.hall_presence", "device_id": "presence"},
        ]), {"cam-1"})
        with tempfile.TemporaryDirectory() as directory:
            automations = SERVER.PresenceAutomationManager(Path(directory) / "presence.yaml").sync(
                {"binary_sensor.garage_g4_motion": "light.garage", "binary_sensor.garage_presence": "light.garage"},
                [{"entity_id": "camera.garage_g4", "device_id": "cam-1"},
                 {"entity_id": "binary_sensor.garage_g4_motion", "device_id": "cam-1", "friendly_name": "Garage G4 Motion"},
                 {"entity_id": "binary_sensor.garage_presence", "device_id": "presence", "friendly_name": "Garage Presence"},
                 {"entity_id": "light.garage", "friendly_name": "Garage Lights"}],
                reload_automations=False,
            )
        self.assertTrue(automations)
        self.assertFalse(any("garage_g4" in str(automation) for automation in automations))

    def test_presence_room_controls_leave_out_cameras(self) -> None:
        handler = object.__new__(SERVER.FutureHomesTechRequestHandler)
        entities = [
            {"entity_id": "camera.garage_g4", "domain": "camera", "device_id": "cam-1", "area": "Garage"},
            {"entity_id": "binary_sensor.garage_g4_motion", "domain": "binary_sensor", "device_id": "cam-1", "area": "Garage", "device_class": "motion"},
            {"entity_id": "binary_sensor.front_doorbell_person", "domain": "binary_sensor", "device_id": "", "area": "Garage", "device_class": "occupancy"},
            {"entity_id": "binary_sensor.garage_presence", "domain": "binary_sensor", "device_id": "presence", "area": "Garage", "device_class": "occupancy"},
        ]
        handler.inventory = Mock()
        handler.inventory.fetch.side_effect = lambda include_all=False, predicate=None, fields=None, **_: {
            "entities": [entity for entity in entities if predicate is None or predicate(entity)]}
        handler.room_aliases = Mock()
        handler.room_aliases.read.return_value = {}
        self._stub_room_control_settings(handler)
        payload = handler._room_controls("presence")
        self.assertEqual([entity["entity_id"] for entity in payload["entities"]], ["binary_sensor.garage_presence"])
        self.assertTrue(payload["rooms_ready"])
        self.assertEqual(payload["enabled_room_modes_by_room"], {"Garage": []})
        self.assertEqual(payload["presence"]["assignments"], {})

    @staticmethod
    def _stub_room_control_settings(handler, action_assignments=None, room_modes=None) -> None:
        for name, value in (
            ("switch_assignments", {}),
            ("switch_control_settings", {"action_assignments": action_assignments or {}, "action_settings": {}}),
            ("room_modes", room_modes or {}),
            ("presence_assignments", {}), ("presence_timings", {}), ("presence_mode_settings", {}),
        ):
            store = Mock()
            store.read.return_value = value
            setattr(handler, name, store)
        handler._catalog_revision = lambda: 7

    def test_doors_snapshot_carries_every_room(self) -> None:
        """One Doors request returns what every room card needs; no per-room requests."""
        handler = object.__new__(SERVER.FutureHomesTechRequestHandler)
        entities = [
            {"entity_id": "binary_sensor.pantry_door", "domain": "binary_sensor", "device_class": "door", "area": "Pantry"},
            {"entity_id": "binary_sensor.closet_door", "domain": "binary_sensor", "device_class": "door", "area": "Bedroom 6"},
            {"entity_id": "light.closet", "domain": "light", "area": "Bedroom 6"},
        ]
        aliases = {"Bedroom 6": "Chloe's Bedroom"}

        def fetch(include_all=False, predicate=None, fields=None, **_):
            # Like the real projection: the predicate sees the Home Assistant area name,
            # and the returned copies carry the display name in "area".
            chosen = [dict(entity) for entity in entities if predicate is None or predicate(entity)]
            for entity in chosen:
                if entity["area"] in aliases:
                    entity["original_area"], entity["area"] = entity["area"], aliases[entity["area"]]
            return {"entities": chosen}
        handler.inventory = Mock()
        handler.inventory.fetch.side_effect = fetch
        handler.room_aliases = Mock()
        handler.room_aliases.read.return_value = aliases
        self._stub_room_control_settings(
            handler, {"door:binary_sensor.closet_door": ["light.closet"]}, {"Bedroom 6": ["sleep", "quiet"]})
        with tempfile.TemporaryDirectory() as directory:
            handler.inventory._config_directory = Path(directory)
            payload = handler._room_controls("doors")
            room_payload = handler._room_controls("doors", "Bedroom 6")
        self.assertTrue(payload["rooms_ready"])
        self.assertEqual([entity["entity_id"] for entity in payload["entities"]],
                         ["binary_sensor.pantry_door", "binary_sensor.closet_door"])
        self.assertEqual(payload["enabled_room_modes_by_room"], {"Bedroom 6": ["sleep", "quiet"], "Pantry": []})
        self.assertEqual([option["id"] for option in payload["door_mode_options_by_room"]["Bedroom 6"]],
                         ["day", "night", "sleep", "room:bedroom_6:sleep", "room:bedroom_6:quiet"])
        self.assertEqual([option["id"] for option in payload["door_mode_options_by_room"]["Pantry"]], ["day", "night", "sleep"])
        self.assertEqual(payload["control_settings"]["action_assignments"], {"door:binary_sensor.closet_door": ["light.closet"]})
        self.assertEqual(payload["catalog_revision"], 7)
        # The per-room path still answers the same way for a single room.
        self.assertNotIn("rooms_ready", room_payload)
        self.assertEqual(room_payload["door_mode_options"], payload["door_mode_options_by_room"]["Bedroom 6"])
        self.assertEqual([entity["entity_id"] for entity in room_payload["door_sensors"]], ["binary_sensor.closet_door"])

    def test_saved_presence_settings_reapply_while_occupied(self) -> None:
        """Re-apply brightness right after a save instead of on the next detection."""
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "presence.yaml"
            publisher = Mock()
            manager = SERVER.PresenceAutomationManager(output, publisher)
            manager.sync(
                {"binary_sensor.bath_presence": "light.bath"},
                [{"entity_id": "binary_sensor.bath_presence", "friendly_name": "Bath"},
                 {"entity_id": "light.bath", "friendly_name": "Bath Lights"}],
                reload_automations=False,
            )
            content = output.read_text(encoding="utf-8")
            manager.apply_saved_settings("binary_sensor.bath_presence")

        self.assertIn(
            "      - trigger: event\n        event_type: fht_presence_settings_saved\n"
            "        event_data:\n          presence_entity_id: binary_sensor.bath_presence\n"
            "        id: settings_saved\n",
            content,
        )
        publisher.fire_event.assert_called_once_with(
            "fht_presence_settings_saved",
            {"presence_entity_id": "binary_sensor.bath_presence", "previous": {"night": 80, "sleep": 25}},
        )
        self.assertIn("state_attr('light.bath', 'brightness')", content)

    @patch.object(SERVER, "urlopen")
    def test_publisher_fires_events_on_the_core_api(self, mock_urlopen: Mock) -> None:
        publisher = SERVER.HomeAssistantHelperPublisher("token", "http://supervisor/core/api/services")
        publisher.fire_event("fht_presence_settings_saved", {"presence_entity_id": "binary_sensor.x"})
        request = mock_urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "http://supervisor/core/api/events/fht_presence_settings_saved")
        self.assertEqual(json.loads(request.data), {"presence_entity_id": "binary_sensor.x"})

    def test_presence_timings_persist_parent_groups(self) -> None:
        """Persist parent groups alongside the existing delay settings."""
        with tempfile.TemporaryDirectory() as directory:
            settings = SERVER.PresenceTimingSettings(
                Path(directory) / "presence-timings.json"
            )
            saved = settings.save(
                "binary_sensor.bathroom_toilet_presence",
                60,
                120,
                ["binary_sensor.fht_bathroom_presence_group"],
            )

        self.assertEqual(
            saved["binary_sensor.bathroom_toilet_presence"]["parent_groups"],
            ["binary_sensor.fht_bathroom_presence_group"],
        )

    def test_presence_assignments_accept_lights_groups_and_actual_loads(self) -> None:
        """Persist every supported presence action target."""
        with tempfile.TemporaryDirectory() as directory:
            assignments = SERVER.PresenceLightGroupAssignments(
                Path(directory) / "presence.json"
            )
            presence_id = "binary_sensor.bathroom_presence"

            targets = [
                "light.bathroom_vanity",
                "light.fht_bathroom_all_lights",
                "switch.bathroom_exhaust_fan",
            ]
            assignments.save(presence_id, targets)
            self.assertEqual(
                assignments.read()[presence_id],
                targets,
            )

    def test_generates_one_presence_automation_per_selected_action(self) -> None:
        """Run every action selected from one presence dropdown."""
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "presence.yaml"
            manager = SERVER.PresenceAutomationManager(output)
            automations = manager.sync(
                {
                    "binary_sensor.bathroom_presence": [
                        "light.fht_bathroom_all_lights",
                        "switch.bathroom_exhaust_fan",
                    ]
                },
                [
                    {
                        "entity_id": "binary_sensor.bathroom_presence",
                        "friendly_name": "Bathroom Presence",
                    },
                    {
                        "entity_id": "light.fht_bathroom_all_lights",
                        "friendly_name": "Bathroom All Lights",
                    },
                    {
                        "entity_id": "switch.bathroom_exhaust_fan",
                        "friendly_name": "Bathroom Exhaust Fan",
                    },
                ],
            )
            content = output.read_text(encoding="utf-8")

        self.assertEqual(len(automations), 2)
        self.assertIn("action: light.turn_on", content)
        self.assertIn("action: switch.turn_on", content)

    def test_generates_actual_load_presence_automation(self) -> None:
        """Use switch services and omit brightness for an actual load."""
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "presence.yaml"
            manager = SERVER.PresenceAutomationManager(output)
            manager.sync(
                {
                    "binary_sensor.bathroom_presence":
                    "switch.bathroom_exhaust_fan"
                },
                [
                    {
                        "entity_id": "binary_sensor.bathroom_presence",
                        "friendly_name": "Bathroom Presence",
                    },
                    {
                        "entity_id": "switch.bathroom_exhaust_fan",
                        "friendly_name": "Bathroom Exhaust Fan",
                    },
                ],
            )
            content = output.read_text(encoding="utf-8")

        self.assertIn("action: switch.turn_on", content)
        self.assertIn("action: switch.turn_off", content)

    def test_mode_specific_door_action_requires_matching_house_mode(self) -> None:
        """Run Pantry Day and Night door actions only in their configured mode."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "controls.yaml"
            door_id = "binary_sensor.pantry_door"
            SERVER.ControlAutomationManager(path).sync(
                {},
                [
                    {"entity_id": door_id, "friendly_name": "Pantry Door"},
                    {"entity_id": "light.fht_pantry_all_lights", "friendly_name": "Pantry All Lights"},
                ],
                action_assignments={
                    f"door:{door_id}|night": ["light_group:light.fht_pantry_all_lights"],
                },
                reload_automations=False,
            )
            content = path.read_text(encoding="utf-8")

        self.assertIn(SERVER.HOUSE_MODE_HELPER, content)
        self.assertIn("'Night'", content)
        self.assertIn("brightness_pct: 100", content)
        self.assertIn("      - condition: or\n", content)
        self.assertIn("          - condition: trigger\n            id: turn_off\n", content)


class RoomModeSettingsTests(unittest.TestCase):
    """Verify room-specific mode recommendations and persistence."""

    def test_catalog_includes_requested_room_mode_sets(self) -> None:
        """Expose only the approved room modes for every supported room type."""
        catalog = SERVER.RoomModeSettings.catalog()
        expected = [
            {"id": "sleep", "label": "Sleep"},
            {"id": "quiet", "label": "Quiet"},
            {"id": "wake_up", "label": "Wake Up"},
            {"id": "game", "label": "Game"},
            {"id": "relax", "label": "Relax"},
            {"id": "movie", "label": "Movie"},
            {"id": "study", "label": "Study"},
            {"id": "chill", "label": "Chill"},
            {"id": "infant", "label": "Infant"},
            {"id": "toddler", "label": "Toddler"},
            {"id": "baby", "label": "Baby"},
            {"id": "armed_away", "label": "Armed Away"},
            {"id": "armed_stay_kids", "label": "Armed Stay Kids"},
            {"id": "armed_stay_adult", "label": "Armed Stay Adult"},
            {"id": "disarmed", "label": "Disarmed"},
        ]
        self.assertEqual(set(catalog), {"bedroom"})
        for modes in catalog.values():
            self.assertEqual(modes, expected)

    def test_current_mode_is_visible_only_for_enabled_bedroom_modes(self) -> None:
        """Hide placeholders, inactive modes, and modes for non-bedroom rooms."""
        visible = SERVER.FutureHomesTechRequestHandler._visible_room_mode

        self.assertEqual(visible("bedroom", "Sleep", ["sleep"]), "Sleep")
        self.assertEqual(visible("bedroom", "Sleep", []), "")
        self.assertEqual(visible("bedroom", "Not Set", ["sleep"]), "")
        self.assertEqual(visible("kitchen", "Sleep", ["sleep"]), "")

    def test_room_modes_persist_and_reject_unknown_modes(self) -> None:
        """Store enabled modes by room and reject unsupported values."""
        with tempfile.TemporaryDirectory() as directory:
            settings = SERVER.RoomModeSettings(Path(directory) / "room_modes.json")
            saved = settings.save(
                "Bedroom 1",
                ["sleep", "wake_up", "movie", "armed_away"],
            )

            self.assertEqual(
                saved["Bedroom 1"],
                ["armed_away", "movie", "sleep", "wake_up"],
            )
            self.assertEqual(settings.read(), saved)
            with self.assertRaisesRegex(ValueError, "not supported"):
                settings.save("Bedroom 1", ["sleep", "spaceship"])


class BedroomModeSettingsTests(unittest.TestCase):
    def test_global_house_offsets_persist_and_validate(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bedrooms.yaml"
            manager = SERVER.BedroomModeAutomationManager(path)
            manager.save_house_settings({"day_offset": 60, "night_offset": -30})
            self.assertEqual(
                SERVER.BedroomModeAutomationManager(path).house_settings(),
                {
                    "day_offset": 60,
                    "night_offset": -30,
                    "sleep_mode_sources": ["*"],
                },
            )
            for invalid in (121, -121, True, 1.5):
                with self.assertRaises(ValueError):
                    manager.save_house_settings({"day_offset": invalid, "night_offset": 0})
            manager.sync({}, [], [])
            generated = path.read_text()
            self.assertIn('offset: "01:00:00"', generated)
            self.assertIn('offset: "-00:30:00"', generated)

    def test_house_solar_mode_uses_actual_transition_boundaries(self) -> None:
        """Do not approximate the prior solar event as exactly one day ago."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bedrooms.yaml"
            manager = SERVER.BedroomModeAutomationManager(path)
            manager.save_house_settings({"day_offset": 60, "night_offset": -30})
            sun = {
                "state": "above_horizon",
                "last_changed": "2026-09-04T06:00:00+00:00",
                "attributes": {
                    "next_rising": "2026-09-05T06:01:00+00:00",
                    "next_setting": "2026-09-04T18:00:00+00:00",
                },
            }

            self.assertTrue(
                manager.solar_day(
                    sun,
                    now=datetime(2026, 9, 4, 7, 0, 30, tzinfo=timezone.utc),
                )
            )
            self.assertFalse(
                manager.solar_day(
                    sun,
                    now=datetime(2026, 9, 4, 17, 30, 30, tzinfo=timezone.utc),
                )
            )

    def test_house_solar_mode_handles_offsets_and_unavailable_state(self) -> None:
        """Honor both sides of each solar boundary and expose unknown data."""
        with tempfile.TemporaryDirectory() as directory:
            manager = SERVER.BedroomModeAutomationManager(
                Path(directory) / "bedrooms.yaml"
            )
            manager.save_house_settings(
                {"day_offset": -120, "night_offset": 120}
            )
            before_sunrise = {
                "state": "below_horizon",
                "last_changed": "2026-09-03T18:00:00+00:00",
                "attributes": {
                    "next_rising": "2026-09-04T06:00:00+00:00",
                    "next_setting": "2026-09-04T18:00:00+00:00",
                },
            }
            after_sunset = {
                "state": "below_horizon",
                "last_changed": "2026-09-04T18:00:00+00:00",
                "attributes": {
                    "next_rising": "2026-09-05T06:00:00+00:00",
                    "next_setting": "2026-09-05T18:00:00+00:00",
                },
            }

            self.assertTrue(
                manager.solar_day(
                    before_sunrise,
                    now=datetime(2026, 9, 4, 4, 30, tzinfo=timezone.utc),
                )
            )
            self.assertTrue(
                manager.solar_day(
                    after_sunset,
                    now=datetime(2026, 9, 4, 19, 30, tzinfo=timezone.utc),
                )
            )
            self.assertFalse(
                manager.solar_day(
                    after_sunset,
                    now=datetime(2026, 9, 4, 20, 0, tzinfo=timezone.utc),
                )
            )
            self.assertIsNone(
                manager.solar_day(
                    {"state": "unavailable", "attributes": {}},
                    now=datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc),
                )
            )

    def test_house_mode_keeps_sleep_and_falls_back_when_sun_is_unknown(self) -> None:
        """Keep Sleep precedence and never invent solar truth from unavailable data."""
        with tempfile.TemporaryDirectory() as directory:
            publisher = Mock()
            manager = SERVER.BedroomModeAutomationManager(
                Path(directory) / "bedrooms.yaml",
                publisher,
            )
            inventory = Mock()
            inventory.fetch.return_value = {
                "entities": [
                    {
                        "entity_id": "input_select.fht_baileys_bedroom_mode",
                        "state": "Sleep",
                    },
                    {
                        "entity_id": SERVER.HOUSE_MODE_HELPER,
                        "state": "Day",
                    },
                    {
                        "entity_id": "sun.sun",
                        "state": "unavailable",
                        "attributes": {},
                    },
                ]
            }

            self.assertEqual(
                manager.refresh_house_mode(
                    {"Baileys Bedroom": {}},
                    inventory,
                ),
                "Sleep",
            )
            inventory.fetch.return_value["entities"][0]["state"] = "Day"
            self.assertEqual(
                manager.refresh_house_mode(
                    {"Baileys Bedroom": {}},
                    inventory,
                ),
                "Day",
            )

    def test_house_sleep_uses_only_selected_bedroom_modes(self) -> None:
        """Activate Whole Home Sleep only from explicitly selected bedrooms."""
        with tempfile.TemporaryDirectory() as directory:
            publisher = Mock()
            manager = SERVER.BedroomModeAutomationManager(
                Path(directory) / "bedrooms.yaml",
                publisher,
            )
            manager.save_house_settings({
                "day_offset": 0,
                "night_offset": 0,
                "sleep_mode_sources": [
                    "input_select.fht_baileys_bedroom_mode"
                ],
            })
            inventory = Mock()
            inventory.fetch.return_value = {"entities": [
                {
                    "entity_id": "input_select.fht_baileys_bedroom_mode",
                    "state": "Day",
                },
                {
                    "entity_id": "input_select.fht_chloes_bedroom_mode",
                    "state": "Sleep",
                },
                {"entity_id": SERVER.HOUSE_MODE_HELPER, "state": "Day"},
                {"entity_id": "sun.sun", "state": "unavailable", "attributes": {}},
            ]}

            self.assertEqual(
                manager.refresh_house_mode(
                    {"Baileys Bedroom": {}, "Chloes Bedroom": {}},
                    inventory,
                ),
                "Day",
            )
            inventory.fetch.return_value["entities"][0]["state"] = "Quiet"
            self.assertEqual(manager.refresh_house_mode(
                {"Baileys Bedroom": {}, "Chloes Bedroom": {}}, inventory), "Day")
            inventory.fetch.return_value["entities"][0]["state"] = "Sleep"
            self.assertEqual(
                manager.refresh_house_mode(
                    {"Baileys Bedroom": {}, "Chloes Bedroom": {}},
                    inventory,
                ),
                "Sleep",
            )

    """Verify functional bedroom mode persistence and generation."""

    def test_defaults_and_solar_limits(self) -> None:
        """Use requested solar defaults and restrict offsets to two hours."""
        setting = SERVER.BedroomModeSettings.normalize({})

        self.assertEqual(setting["random_start_event"], "sunset")
        self.assertEqual(setting["random_start_offset"], -30)
        self.assertEqual(setting["random_end_event"], "sunrise")
        self.assertEqual(setting["random_end_offset"], 30)
        self.assertEqual(setting["day_event"], "sunrise")
        self.assertEqual(setting["day_offset"], 0)
        self.assertEqual(setting["night_event"], "sunset")
        self.assertEqual(setting["night_offset"], -15)
        with self.assertRaisesRegex(ValueError, "between -120 and 120"):
            SERVER.BedroomModeSettings.normalize({"day_offset": 121})

    def test_persists_selected_kids_doors(self) -> None:
        """Store only current Home Assistant door sensors for Kids mode."""
        with tempfile.TemporaryDirectory() as directory:
            settings = SERVER.BedroomModeSettings(
                Path(directory) / "bedroom_modes.json"
            )
            saved = settings.save(
                "Bedroom 1",
                {
                    "armed_away_enabled": True,
                    "armed_stay_kids_enabled": True,
                    "kids_door_sensors": ["binary_sensor.hall_door"],
                },
                {"binary_sensor.hall_door"},
            )

            self.assertTrue(saved["Bedroom 1"]["armed_away_enabled"])
            self.assertEqual(
                saved["Bedroom 1"]["kids_door_sensors"],
                ["binary_sensor.hall_door"],
            )
            with self.assertRaisesRegex(ValueError, "unavailable"):
                settings.save(
                    "Bedroom 1",
                    {"kids_door_sensors": ["binary_sensor.missing"]},
                    {"binary_sensor.hall_door"},
                )

    def test_generates_bedroom_security_and_random_light_automations(self) -> None:
        """Generate mode helper, door webhooks, and light randomization."""
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "bedroom_modes.yaml"
            manager = SERVER.BedroomModeAutomationManager(
                output,
                armed_away_webhook_configured=True,
                armed_stay_kids_webhook_configured=True,
            )
            settings = {
                "Bedroom 1": SERVER.BedroomModeSettings.normalize({
                    "armed_away_enabled": True,
                    "random_lights_enabled": True,
                    "armed_stay_kids_enabled": True,
                    "kids_door_sensors": ["binary_sensor.hall_door"],
                })
            }
            entities = [
                {
                    "entity_id": "light.fht_bedroom_1_fan_lights",
                    "friendly_name": "Bedroom 1 Fan Lights",
                    "original_area": "Bedroom 1",
                },
            ]
            doors = [
                {
                    "entity_id": "binary_sensor.bedroom_1_door",
                    "friendly_name": "Bedroom 1 Door",
                    "original_area": "Bedroom 1",
                },
                {
                    "entity_id": "binary_sensor.hall_door",
                    "friendly_name": "Hall Door",
                    "original_area": "Hallway",
                },
            ]

            automations = manager.sync(settings, entities, doors)
            content = output.read_text(encoding="utf-8")

            self.assertEqual(len(automations), 5)
            self.assertIn("fht_house_mode:", content)
            self.assertIn("Future Homes Tech House Mode", content)
            self.assertIn("FHT - House Mode Status", content)
            self.assertNotIn('minutes: "/1"', content, "House Mode Status does not run every minute")
            self.assertIn("fht_bedroom_1_mode:", content)
            self.assertIn("      - Sleep", content)
            self.assertIn("Armed Stay Adult", content)
            self.assertIn("binary_sensor.bedroom_1_door", content)
            self.assertNotIn("binary_sensor.hall_door", content)
            self.assertIn(
                "rest_command.future_homes_tech_bedroom_armed_away",
                content,
            )
            self.assertIn(
                "rest_command.future_homes_tech_bedroom_armed_stay_kids",
                content,
            )
            self.assertIn("minutes: \"/10\"", content)
            self.assertIn("after_offset: \"-00:30:00\"", content)
            self.assertIn("before_offset: \"00:30:00\"", content)

    def test_refreshes_house_mode_immediately(self) -> None:
        """Reconcile Night and Sleep without waiting for a solar event."""
        with tempfile.TemporaryDirectory() as directory:
            publisher = Mock()
            inventory = Mock()
            manager = SERVER.BedroomModeAutomationManager(
                Path(directory) / "bedroom_modes.yaml",
                publisher=publisher,
            )
            settings = {"Bedroom 1": SERVER.BedroomModeSettings.normalize({})}
            inventory.fetch.side_effect = [
                {
                    "entities": [
                        {
                            "entity_id": "input_select.fht_bedroom_1_mode",
                            "state": "Day",
                        },
                        {
                            "entity_id": "sun.sun",
                            "state": "below_horizon",
                            "attributes": {},
                        },
                    ]
                },
                {
                    "entities": [
                        {
                            "entity_id": "input_select.fht_bedroom_1_mode",
                            "state": "Sleep",
                        },
                        {
                            "entity_id": "sun.sun",
                            "state": "below_horizon",
                            "attributes": {},
                        },
                    ]
                },
            ]

            self.assertEqual(
                manager.refresh_house_mode(settings, inventory),
                "Night",
            )
            self.assertEqual(
                manager.refresh_house_mode(settings, inventory),
                "Sleep",
            )
            self.assertEqual(
                publisher.climate_action.call_args_list,
                [
                    unittest.mock.call(
                        "set_option",
                        SERVER.HOUSE_MODE_HELPER,
                        "Night",
                    ),
                    unittest.mock.call(
                        "set_option",
                        SERVER.HOUSE_MODE_HELPER,
                        "Sleep",
                    ),
                ],
            )

    def test_bedroom_sync_reloads_only_its_generated_domains(self) -> None:
        """Avoid reloading unrelated helpers after a bedroom-mode save."""
        with tempfile.TemporaryDirectory() as directory:
            publisher = Mock()
            manager = SERVER.BedroomModeAutomationManager(
                Path(directory) / "bedroom_modes.yaml",
                publisher=publisher,
            )

            manager.sync({}, [], [])

        publisher.reload_domains.assert_called_once_with(
            ("input_select", "input_boolean", "timer", "automation")
        )

    def test_wake_sync_reloads_only_its_generated_domains(self) -> None:
        """Avoid a full managed-domain reload after a wake-routine save."""
        with tempfile.TemporaryDirectory() as directory:
            publisher = Mock()
            manager = SERVER.WakeRoutineAutomationManager(
                Path(directory) / "wake.yaml",
                publisher=publisher,
            )

            manager.sync({}, [])

        publisher.reload_domains.assert_called_once_with(
            (
                "input_datetime",
                "input_boolean",
                "input_button",
                "input_select",
                "automation",
            )
        )

    def test_validates_and_generates_toddler_mode(self) -> None:
        """Persist capability selections and generate one coordinated state machine."""
        with tempfile.TemporaryDirectory() as directory:
            settings_store = SERVER.BedroomModeSettings(
                Path(directory) / "bedroom_modes.json"
            )
            setting = settings_store.save(
                "Bedroom 1",
                {
                    "toddler_enabled": True,
                    "toddler_door_sensor": "binary_sensor.bedroom_1_door",
                    "toddler_light_entities": ["light.bedroom_1_rgb"],
                    "toddler_brightness": 42,
                    "toddler_color": "#123456",
                    "toddler_chime_entities": ["button.hall_chime_play"],
                    "toddler_chime_repeats": 3,
                    "toddler_timeout_minutes": 20,
                    "toddler_indicator_effect_entity": "select.bedroom_1_led_effect",
                    "toddler_indicator_effect": "Pulse",
                    "toddler_indicator_off_effect": "Off",
                },
                {"binary_sensor.bedroom_1_door"},
                {
                    "binary_sensor.bedroom_1_door",
                    "light.bedroom_1_rgb",
                    "button.hall_chime_play",
                    "select.bedroom_1_led_effect",
                },
            )["Bedroom 1"]
            output = Path(directory) / "bedroom_modes.yaml"
            automations = SERVER.BedroomModeAutomationManager(output).sync(
                {"Bedroom 1": setting},
                [{"entity_id": "light.bedroom_1_rgb", "original_area": "Bedroom 1"}],
                [{"entity_id": "binary_sensor.bedroom_1_door", "original_area": "Bedroom 1"}],
            )
            content = output.read_text(encoding="utf-8")

        self.assertTrue(setting["toddler_enabled"])
        self.assertIn("Toddler", content)
        self.assertIn("fht_bedroom_1_toddler_door_armed", content)
        self.assertIn("fht_bedroom_1_toddler_timeout", content)
        self.assertIn("id: door_closed", content)
        self.assertIn("id: door_opened", content)
        self.assertIn("brightness_pct: 42", content)
        self.assertIn("rgb_color: [18, 52, 86]", content)
        self.assertIn("action: button.press", content)
        self.assertIn("count: 3", content)
        self.assertIn('option: "Pulse"', content)
        self.assertTrue(any(item["mode"] == "Toddler" for item in automations))

    def test_rejects_unavailable_toddler_entities(self) -> None:
        """Do not persist stale lights, doors, chimes, or LED controls."""
        with self.assertRaisesRegex(ValueError, "unavailable"):
            SERVER.BedroomModeSettings.normalize(
                {
                    "toddler_enabled": True,
                    "toddler_light_entities": ["light.missing"],
                },
                set(),
                {"light.available"},
            )


class HomeKitBridgeTests(unittest.TestCase):
    """Verify selected HomeKit bridges remain independently pairable."""

    def test_uses_separate_ports_for_all_homekit_bridges(self) -> None:
        """Assign every configured HomeKit bridge its own port."""
        with tempfile.TemporaryDirectory() as directory:
            data_directory = Path(directory)
            selection = SERVER.HomeKitLightGroupSelection(
                data_directory / "lights.json",
                data_directory / "climate.json",
                data_directory / "homekit.yaml",
            )
            names = {
                "light.fht_kitchen_lights": "Kitchen Lights",
                "climate.kitchen": "Kitchen Thermostat",
                "binary_sensor.entry_door": "Entry Door Sensor",
            }
            selection.save("light.fht_kitchen_lights", True, names)
            selection.save_climate("climate.kitchen", True, names)
            selection.save_security("binary_sensor.entry_door", True, names)
            package = (data_directory / "homekit.yaml").read_text(
                encoding="utf-8"
            )

        self.assertIn("name: FHT HomeKit Lights\n    port: 21063", package)
        self.assertIn("name: FHT HomeKit Climate\n    port: 21064", package)
        self.assertIn("name: FHT HomeKit Security\n    port: 21065", package)
        self.assertIn('name: "Entry Door Sensor"', package)

    def test_homekit_replaces_retired_all_lights_with_fan_lights(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            selection = SERVER.HomeKitLightGroupSelection(root / "lights.json", root / "climate.json", root / "homekit.yaml")
            selection.save("light.fht_bedroom_6_all_lights", True, {"light.fht_bedroom_6_all_lights": "Chloe's Bedroom All Lights"})
            changed = selection.reconcile_generated_groups(
                {"light.fht_bedroom_6_fan_lights"},
                {"light.fht_bedroom_6_all_lights": "Chloe's Bedroom All Lights"},
            )
            self.assertTrue(changed)
            self.assertEqual(selection.read(), ["light.fht_bedroom_6_fan_lights"])
            self.assertIn("Chloe's Bedroom Fan Lights", (root / "homekit.yaml").read_text())
            self.assertFalse(selection.reconcile_generated_groups({"light.fht_bedroom_6_fan_lights"}, {}))

    def test_homekit_writers_take_the_activation_lock_first(self) -> None:
        """Hold the activation lock before the selection lock, as the POST lane does."""
        events: list[str] = []

        class RecordingLock:
            def __init__(self, name: str) -> None:
                self._name = name

            def __enter__(self) -> None:
                events.append(f"+{self._name}")

            def __exit__(self, *args: object) -> None:
                events.append(f"-{self._name}")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            selection = SERVER.HomeKitLightGroupSelection(root / "lights.json", root / "climate.json", root / "homekit.yaml")
            names = {"light.fht_bedroom_6_all_lights": "Chloe's Bedroom All Lights"}
            selection.save("light.fht_bedroom_6_all_lights", True, names)
            selection._lock = RecordingLock("selection")
            with patch.object(SERVER, "CONFIGURATION_ACTIVATION_LOCK", RecordingLock("activation")):
                self.assertTrue(selection.reconcile_generated_groups({"light.fht_bedroom_6_fan_lights"}, dict(names)))
                self.assertEqual(events[:2], ["+activation", "+selection"])
                events.clear()
                selection.save("light.fht_bedroom_6_fan_lights", False, names)
                self.assertEqual(events[:2], ["+activation", "+selection"])
                events.clear()
                selection.save_climate("climate.kitchen", True, {"climate.kitchen": "Kitchen"})
                self.assertEqual(events[:2], ["+activation", "+selection"])
                events.clear()
                selection.save_security("binary_sensor.entry_door", True, {"binary_sensor.entry_door": "Entry Door"})
                self.assertEqual(events[:2], ["+activation", "+selection"])

    def test_security_bridge_rejects_non_door_entities(self) -> None:
        """Only permit door sensors returned by the Security inventory."""
        with tempfile.TemporaryDirectory() as directory:
            data_directory = Path(directory)
            selection = SERVER.HomeKitLightGroupSelection(
                data_directory / "lights.json",
                data_directory / "climate.json",
                data_directory / "homekit.yaml",
            )
            with self.assertRaisesRegex(ValueError, "door sensor"):
                selection.save_security(
                    "binary_sensor.phone_battery",
                    True,
                    {"binary_sensor.entry_door": "Entry Door Sensor"},
                )


class LightScheduleTests(unittest.TestCase):
    """Verify persistent per-light schedule automation generation."""

    def test_persists_valid_solar_and_custom_schedule_fields(self) -> None:
        """Store enabled state, solar offsets, custom time, and brightness."""
        with tempfile.TemporaryDirectory() as directory:
            settings = SERVER.LightScheduleSettings(
                Path(directory) / "schedules.json"
            )
            saved = settings.save(
                "light.fht_outside_all_lights",
                {
                    "enabled": True,
                    "on_type": "sunset",
                    "on_offset": -15,
                    "on_time": "18:00",
                    "off_type": "time",
                    "off_offset": 0,
                    "off_time": "23:30",
                    "brightness": 65,
                    "color_mode": "kelvin",
                    "color_kelvin": 5000,
                    "color_hex": "#ffffff",
                },
            )

        self.assertEqual(
            saved["light.fht_outside_all_lights"]["on_offset"],
            -15,
        )
        self.assertEqual(
            saved["light.fht_outside_all_lights"]["off_time"],
            "23:30",
        )
        self.assertEqual(
            saved["light.fht_outside_all_lights"]["brightness"],
            65,
        )
        self.assertEqual(
            saved["light.fht_outside_all_lights"]["color_kelvin"],
            5000,
        )

    def test_rejects_invalid_schedule_values(self) -> None:
        """Reject unsupported triggers, malformed times, and unsafe ranges."""
        with self.assertRaisesRegex(ValueError, "sunrise, sunset, or time"):
            SERVER.LightScheduleSettings.normalize({"on_type": "midnight"})
        with self.assertRaisesRegex(ValueError, "HH:MM"):
            SERVER.LightScheduleSettings.normalize({"on_time": "6 PM"})
        with self.assertRaisesRegex(ValueError, "between -360 and 360"):
            SERVER.LightScheduleSettings.normalize({"on_offset": 500})
        with self.assertRaisesRegex(ValueError, "between 1 and 100"):
            SERVER.LightScheduleSettings.normalize({"brightness": 0})
        with self.assertRaisesRegex(ValueError, "current, adaptive, kelvin, or rgb"):
            SERVER.LightScheduleSettings.normalize({"color_mode": "rainbow"})
        with self.assertRaisesRegex(ValueError, "between 2000 and 6500"):
            SERVER.LightScheduleSettings.normalize({"color_kelvin": 7000})
        with self.assertRaisesRegex(ValueError, "six-digit hex"):
            SERVER.LightScheduleSettings.normalize({"color_hex": "red"})

    def test_generates_solar_and_custom_time_automation(self) -> None:
        """Write one native automation with ON brightness and OFF action."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "light_schedules.yaml"
            manager = SERVER.LightScheduleAutomationManager(path)
            automations = manager.sync(
                {
                    "light.fht_outside_all_lights": {
                        "enabled": True,
                        "on_type": "sunset",
                        "on_offset": -15,
                        "on_time": "18:00",
                        "off_type": "time",
                        "off_offset": 0,
                        "off_time": "23:30",
                        "brightness": 65,
                        "color_mode": "kelvin",
                        "color_kelvin": 5000,
                        "color_hex": "#ffffff",
                    }
                },
                [
                    {
                        "entity_id": "light.fht_outside_all_lights",
                        "friendly_name": "Outside All Lights",
                    }
                ],
            )
            content = path.read_text(encoding="utf-8")

        self.assertEqual(len(automations), 1)
        self.assertIn("event: sunset", content)
        self.assertIn('offset: "-00:15:00"', content)
        self.assertIn('at: "23:30:00"', content)
        self.assertIn("brightness_pct: 65", content)
        self.assertIn("color_temp_kelvin: 5000", content)
        self.assertIn("action: light.turn_off", content)

    def test_generates_adaptive_color_refresh_for_lights_that_are_on(self) -> None:
        """Refresh adaptive color every fifteen minutes without turning off lights on."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "light_schedules.yaml"
            manager = SERVER.LightScheduleAutomationManager(path)
            manager.sync(
                {
                    "light.fht_bedroom_all_lights": {
                        "enabled": True,
                        "color_mode": "adaptive",
                    }
                },
                [{"entity_id": "light.fht_bedroom_all_lights", "friendly_name": "Bedroom All Lights"}],
            )
            content = path.read_text(encoding="utf-8")

        self.assertIn('minutes: "/15"', content)
        self.assertIn("id: adaptive_refresh", content)
        self.assertIn("state_attr('sun.sun', 'elevation')", content)
        self.assertIn("transition: 900", content)
        self.assertIn("entity_id: light.fht_bedroom_all_lights", content)


class ClimateActionTests(unittest.TestCase):
    """Verify the Climate Settings page uses only expected services."""

    def test_sets_a_climate_target(self) -> None:
        """Route a thermostat target through climate.set_temperature."""
        publisher = SERVER.HomeAssistantHelperPublisher("token", "http://example/services")
        with patch.object(publisher, "_call_service") as call_service:
            publisher.climate_action("set_temperature", "climate.office", 72)
        call_service.assert_called_once_with(
            "climate",
            "set_temperature",
            {"entity_id": "climate.office", "temperature": 72.0},
        )

    def test_sets_a_climate_schedule_time(self) -> None:
        """Route the AM/PM picker result to the native time helper."""
        publisher = SERVER.HomeAssistantHelperPublisher(
            "token", "http://example/services"
        )
        with patch.object(publisher, "_call_service") as call_service:
            publisher.climate_action(
                "set_time",
                "input_datetime.fht_on_peak_start",
                "17:30:00",
            )
        call_service.assert_called_once_with(
            "input_datetime",
            "set_datetime",
            {
                "entity_id": "input_datetime.fht_on_peak_start",
                "time": "17:30:00",
            },
        )


class ProtectNvrTests(unittest.TestCase):
    """Verify Protect NVR arm-mode state."""

    def test_returns_raw_nvr_object_with_arm_mode(self) -> None:
        """Expose NVR arm-mode values for the dashboard summary."""
        protect_api = SERVER.ProtectAPI(
            api_key="api-key",
            webhook_url=(
                "https://unifi.fht.internal/proxy/protect/integration/v1/"
                "alarm-manager/webhook/device_offline"
            ),
        )
        payload = [{
            "id": "nvr-1",
            "modelKey": "nvr",
            "name": "Main NVR",
            "armMode": {
                "status": "armed",
                "armProfileId": "away",
                "breachEventCount": 0,
            },
        }]
        with patch.object(protect_api, "_fetch_json", return_value=payload):
            result = protect_api.fetch_nvr_object()
        self.assertEqual(result["nvr_object"], payload)
        self.assertEqual(result["arm_mode"]["status"], "armed")
        self.assertEqual(result["arm_mode"]["arm_profile_id"], "away")


class ServerTests(unittest.TestCase):
    """Verify entity inventory behavior."""

    def test_app_requests_supervisor_api_access(self) -> None:
        """Allow the App to query its installed and latest versions."""
        config = CONFIG_PATH.read_text(encoding="utf-8")
        self.assertIn("hassio_api: true", config)

    def test_uses_interior_door_webhook_configuration_names(self) -> None:
        """Expose clear names while retaining legacy saved-value fallbacks."""
        config = CONFIG_PATH.read_text(encoding="utf-8")
        launcher = CONFIG_PATH.with_name("run.sh").read_text(encoding="utf-8")

        self.assertIn("armed_away_interior_door_webhook", config)
        self.assertIn("armed_stay_kids_interior_door_webhook", config)
        self.assertNotIn("  bedroom_armed_away_webhook:", config)
        self.assertNotIn("  bedroom_armed_stay_kids_webhook:", config)
        self.assertIn(".bedroom_armed_away_webhook", launcher)
        self.assertIn(".bedroom_armed_stay_kids_webhook", launcher)

    @patch.object(SERVER, "urlopen")
    def test_fetches_one_weather_state_for_toolbar_temperature(
        self,
        mock_urlopen: Mock,
    ) -> None:
        """Avoid loading all entities to display the toolbar temperature."""
        mock_urlopen.return_value = MockResponse(
            {
                "entity_id": "weather.forecast_home",
                "state": "sunny",
                "attributes": {"temperature": 111, "temperature_unit": "°F"},
            }
        )
        inventory = SERVER.EntityInventory(
            token="token",
            states_url="http://supervisor/core/api/states",
            websocket_url="ws://supervisor/core/websocket",
        )

        weather = inventory.fetch_state("weather.forecast_home")

        self.assertEqual(weather["attributes"]["temperature"], 111)
        request = mock_urlopen.call_args.args[0]
        self.assertEqual(
            request.full_url,
            "http://supervisor/core/api/states/weather.forecast_home",
        )

    def test_persists_switch_light_group_assignments(self) -> None:
        """Save, read, and remove switch-to-FHT-group selections."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "assignments.json"
            assignments = SERVER.SwitchLightGroupAssignments(path)

            saved = assignments.save(
                "switch.kitchen_2g",
                "light.fht_kitchen_all_lights",
            )
            self.assertEqual(
                saved["switch.kitchen_2g"],
                "light.fht_kitchen_all_lights",
            )
            self.assertEqual(saved, assignments.read())
            self.assertEqual(
                assignments.save("switch.kitchen_2g", ""),
                {},
            )

    def test_persists_switch_mode_and_actual_load_settings(self) -> None:
        """Persist named switch loads and reusable control targets."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            settings = SERVER.SwitchControlSettings(
                Path(temporary_directory) / "control_settings.json"
            )
            switch_id = "switch.bathroom_1_toilet_switch_2g_switch_2"
            source_switch_id = "switch.bathroom_1_toilet_switch_2g_switch_1"
            mode_entity_id = "input_select.fht_bedroom_2_mode"

            settings.save_mode(source_switch_id, mode_entity_id)
            settings.save_actual_load(switch_id, "Exhaust Fan")
            saved = settings.save_load_target(source_switch_id, switch_id)

            self.assertEqual(
                saved["mode_assignments"][source_switch_id],
                mode_entity_id,
            )
            self.assertEqual(
                saved["actual_loads"][switch_id],
                "Exhaust Fan",
            )
            self.assertEqual(
                saved["load_target_assignments"][source_switch_id],
                switch_id,
            )
            self.assertEqual(saved, settings.read())
            settings.save_mode(source_switch_id, "")
            self.assertNotIn(
                source_switch_id,
                settings.read()["mode_assignments"],
            )
            settings.save_actual_load(switch_id, "")
            self.assertNotIn(switch_id, settings.read()["actual_loads"])
            self.assertNotIn(
                source_switch_id,
                settings.read()["load_target_assignments"],
            )

    def test_persists_multiple_actions_for_one_control(self) -> None:
        """Keep every selected action under one control assignment."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            settings = SERVER.SwitchControlSettings(
                Path(temporary_directory) / "control_settings.json"
            )
            assignment_id = "switch.kitchen_switch_3g_switch_1"
            actions = [
                "light_group:light.fht_kitchen_all_lights",
                "actual_load:switch.kitchen_speaker",
                "room_mode:input_select.fht_kitchen_mode|Sleep",
            ]

            saved = settings.save_actions(assignment_id, actions)

            normalized_actions = [
                "light_group:light.fht_kitchen_all_lights",
                "entity_target:switch.kitchen_speaker",
                "room_mode:input_select.fht_kitchen_mode|Sleep",
            ]
            self.assertEqual(
                saved["action_assignments"][assignment_id],
                normalized_actions,
            )
            self.assertEqual(
                settings.read()["action_assignments"][assignment_id],
                normalized_actions,
            )

    def test_multi_action_save_clears_internal_legacy_targets_atomically(self) -> None:
        """Do not leave competing mode or load targets in the same store."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            settings = SERVER.SwitchControlSettings(
                Path(temporary_directory) / "control_settings.json"
            )
            assignment_id = "switch.kitchen_switch_3g_switch_1"
            target_id = "switch.kitchen_speaker"
            settings.save_actual_load(target_id, "Kitchen Speaker")
            settings.save_mode(
                assignment_id,
                "input_select.fht_kitchen_mode",
            )
            settings.save_load_target(assignment_id, target_id)

            saved = settings.save_actions(
                assignment_id,
                ["entity_target:switch.kitchen_speaker"],
            )

        self.assertNotIn(assignment_id, saved["mode_assignments"])
        self.assertNotIn(assignment_id, saved["load_target_assignments"])
        self.assertEqual(
            saved["action_assignments"][assignment_id],
            ["entity_target:switch.kitchen_speaker"],
        )

    def test_completed_legacy_migration_does_not_restore_cleared_door_action(self) -> None:
        """Never resurrect a retired door assignment after it is cleared."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            settings = SERVER.SwitchControlSettings(
                Path(temporary_directory) / "control_settings.json"
            )
            door_id = "binary_sensor.baileys_bedroom_door"
            assignment_id = f"door:{door_id}"
            legacy = {door_id: "light.fht_baileys_bedroom_all_lights"}

            migrated = settings.migrate_legacy({}, legacy)
            self.assertEqual(migrated["schema_version"], 2)
            self.assertIn(assignment_id, migrated["action_assignments"])

            settings.save_actions(assignment_id, [])
            remigrated = settings.migrate_legacy({}, legacy)

        self.assertNotIn(assignment_id, remigrated["action_assignments"])

    def test_repair_play_room_door_target_only_when_replacement_is_available(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            settings = SERVER.SwitchControlSettings(Path(temporary_directory) / "control_settings.json")
            assignment_id = "door:binary_sensor.bedroom_5_door_sensor|day"
            retired_action = "light_group:light.bedroom_5_fan_lights"
            replacement_action = "light_group:light.fht_bedroom_5_all_lights"
            settings.save_actions(assignment_id, [retired_action, "light_group:light.other"])
            settings.save_actions("door:binary_sensor.other|day", [retired_action])
            settings.save_actions("switch.bedroom_6_switch_1", ["light_group:light.bedroom_6_fan_lights"])
            settings.save_actions("door:binary_sensor.bedroom_6_door|day", ["light_group:light.fht_bedroom_6_all_lights"])
            unavailable = [
                {"entity_id": "light.bedroom_5_fan_lights", "state": "unavailable"},
                {"entity_id": "light.fht_bedroom_5_all_lights", "state": "unavailable"},
            ]
            expected = {"light.fht_bedroom_5_fan_lights", "light.fht_bedroom_6_fan_lights"}
            self.assertEqual(settings.reconcile_retired_fan_light_groups(unavailable, expected)["action_assignments"][assignment_id][0], "light_group:light.fht_bedroom_5_fan_lights")
            unavailable[1]["state"] = "off"
            unavailable.extend([
                {"entity_id": "light.bedroom_6_fan_lights", "state": "unavailable"},
                {"entity_id": "light.fht_bedroom_6_all_lights", "state": "off"},
            ])
            repaired = settings.reconcile_retired_fan_light_groups(unavailable, expected)
            self.assertEqual(repaired["action_assignments"][assignment_id], ["light_group:light.fht_bedroom_5_fan_lights", "light_group:light.other"])
            self.assertEqual(repaired["action_assignments"]["door:binary_sensor.other|day"], ["light_group:light.fht_bedroom_5_fan_lights"])
            self.assertEqual(repaired["action_assignments"]["switch.bedroom_6_switch_1"], ["light_group:light.fht_bedroom_6_fan_lights"])
            self.assertEqual(repaired["action_assignments"]["door:binary_sensor.bedroom_6_door|day"], ["light_group:light.fht_bedroom_6_fan_lights"])
            self.assertEqual(settings.reconcile_retired_fan_light_groups(unavailable, expected), repaired)

    def test_rejects_actual_load_self_target(self) -> None:
        """Do not generate an automation that controls its own trigger."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            settings = SERVER.SwitchControlSettings(
                Path(temporary_directory) / "control_settings.json"
            )
            switch_id = "switch.bathroom_1_toilet_switch_2g_switch_2"
            settings.save_actual_load(switch_id, "Exhaust Fan")

            with self.assertRaises(ValueError):
                settings.save_load_target(switch_id, switch_id)

    def test_discovers_switch_target_as_reusable_load(self) -> None:
        """Persist a named plug selected directly from the Buttons page."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            settings = SERVER.SwitchControlSettings(
                Path(temporary_directory) / "control_settings.json"
            )
            assignment_id = (
                "button:device-123|zha|remote_button_short_press|button"
            )
            target_id = "switch.office_speaker"

            saved = settings.save_discovered_switch_target(
                assignment_id,
                target_id,
                [
                    {
                        "entity_id": target_id,
                        "domain": "switch",
                        "friendly_name": "Office Speaker",
                    }
                ],
            )

            self.assertEqual(
                saved["actual_loads"][target_id],
                "Office Speaker",
            )
            self.assertEqual(
                saved["load_target_assignments"][assignment_id],
                target_id,
            )
            self.assertEqual(saved, settings.read())

    def test_rejects_non_switch_discovered_load(self) -> None:
        """Only Home Assistant switch entities may become plug targets."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            settings = SERVER.SwitchControlSettings(
                Path(temporary_directory) / "control_settings.json"
            )
            with self.assertRaisesRegex(ValueError, "switch or plug"):
                settings.save_discovered_switch_target(
                    "button:device-123|zha|remote_button_short_press|button",
                    "light.office_lamp",
                    [
                        {
                            "entity_id": "light.office_lamp",
                            "domain": "light",
                            "friendly_name": "Office Lamp",
                        }
                    ],
                )

    def test_reconciles_actual_load_with_entity_friendly_name(self) -> None:
        """Treat Home Assistant's friendly name as the load label."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            settings = SERVER.SwitchControlSettings(
                Path(temporary_directory) / "control_settings.json"
            )
            switch_id = "switch.master_bathroom_toilet_switch_2g_switch_2"
            settings.save_actual_load(switch_id, "Old Load Name")

            saved = settings.reconcile_actual_load_names(
                [
                    {
                        "entity_id": switch_id,
                        "friendly_name": "Master Bathroom Toilet Exhaust Fan",
                    },
                ]
            )

            self.assertEqual(
                saved["actual_loads"][switch_id],
                "Master Bathroom Toilet Exhaust Fan",
            )
            self.assertEqual(saved, settings.read())

    def test_persists_inovelli_gesture_assignments(self) -> None:
        """Save each Matter button gesture independently."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            assignments = SERVER.SwitchLightGroupAssignments(
                Path(temporary_directory) / "assignments.json"
            )
            assignment_id = (
                "event.kitchen_switch_1g_button_up|multi_press_2"
            )
            saved = assignments.save(
                assignment_id,
                "light.fht_kitchen_all_lights",
            )
            self.assertEqual(
                saved[assignment_id],
                "light.fht_kitchen_all_lights",
            )

    def test_persists_named_matter_button_event_assignments(self) -> None:
        """Save each event gesture exposed by a named Matter button."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            assignments = SERVER.SwitchLightGroupAssignments(
                Path(temporary_directory) / "assignments.json"
            )
            assignment_id = (
                "event.office_desk_button_button_1|multi_press_1"
            )
            saved = assignments.save(
                assignment_id,
                "light.fht_office_all_lights",
            )
            self.assertEqual(saved, assignments.read())

    def test_discovers_named_buttons_and_excludes_switches(self) -> None:
        """Include event-backed buttons while excluding button switches."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_directory = Path(temporary_directory)
            storage_directory = config_directory / ".storage"
            storage_directory.mkdir()
            storage_directory.joinpath("core.area_registry").write_text(
                json.dumps(
                    {"data": {"areas": [{"area_id": "office", "name": "Office"}]}}
                ),
                encoding="utf-8",
            )
            storage_directory.joinpath("core.device_registry").write_text(
                json.dumps(
                    {
                        "data": {
                            "devices": [
                                {
                                    "id": "ikea-button",
                                    "area_id": "office",
                                    "name_by_user": "Office Desk Button",
                                    "identifiers": [["matter", "node-1"]],
                                },
                                {
                                    "id": "button-switch",
                                    "area_id": "office",
                                    "name_by_user": "Office Button Switch",
                                    "identifiers": [["matter", "node-2"]],
                                },
                            ]
                        }
                    }
                ),
                encoding="utf-8",
            )
            storage_directory.joinpath("core.entity_registry").write_text(
                json.dumps(
                    {
                        "data": {
                            "entities": [
                                {
                                    "entity_id": "event.office_desk_button_button_1",
                                    "device_id": "ikea-button",
                                    "platform": "matter",
                                },
                                {
                                    "entity_id": "event.office_button_switch_button_1",
                                    "device_id": "button-switch",
                                    "platform": "matter",
                                },
                            ]
                        }
                    }
                ),
                encoding="utf-8",
            )

            buttons = SERVER.button_devices_from_storage(config_directory)

        self.assertEqual(len(buttons), 1)
        self.assertEqual(buttons[0]["friendly_name"], "Office Desk Button")
        self.assertEqual(
            buttons[0]["event_entity_ids"],
            ["event.office_desk_button_button_1"],
        )

    def test_persists_native_button_trigger_assignments(self) -> None:
        """Keep each ZHA device trigger assignment across App restarts."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            assignments = SERVER.SwitchLightGroupAssignments(
                Path(temporary_directory) / "assignments.json"
            )
            assignment_id = (
                "button:device-123|zha|remote_button_short_press|button"
            )
            saved = assignments.save(
                assignment_id,
                "light.fht_dining_room_all_lights",
            )
            self.assertEqual(saved, assignments.read())
            self.assertEqual(
                assignments.read()[assignment_id],
                "light.fht_dining_room_all_lights",
            )

    def test_generates_native_button_trigger_automation(self) -> None:
        """Create a persistent device-trigger automation for a ZHA button."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "controls.yaml"
            manager = SERVER.ControlAutomationManager(path)
            automations = manager.sync(
                {
                    "button:device-123|zha|remote_button_short_press|button":
                        "light.fht_dining_room_all_lights",
                },
                [
                    {
                        "entity_id": "light.fht_dining_room_all_lights",
                        "friendly_name": "Dining Room All Lights",
                    },
                ],
                [
                    {
                        "device_id": "device-123",
                        "friendly_name": "Dining Room Button 1",
                    },
                ],
                reload_automations=False,
            )
            content = path.read_text(encoding="utf-8")

        self.assertEqual(len(automations), 1)
        self.assertIn("trigger: device", content)
        self.assertIn("domain: zha", content)
        self.assertIn("type: remote_button_short_press", content)
        self.assertIn("subtype: button", content)
        self.assertIn("wait_template:", content)
        self.assertIn('timeout: "00:05:00"', content)
        self.assertIn("continue_on_timeout: false", content)
        self.assertIn("action: light.toggle", content)

    def test_accepts_direct_control_entities_and_individual_lights(self) -> None:
        """Accept switch-device channels and any selectable light target."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            assignments = SERVER.SwitchLightGroupAssignments(
                Path(temporary_directory) / "assignments.json"
            )
            assignments.save("light.kitchen_load", "light.fht_kitchen")
            assignments.save("switch.kitchen_2g", "light.kitchen")
            assignments.save("fan.kitchen_exhaust", "light.kitchen")
            self.assertEqual(
                assignments.read(),
                {
                    "light.kitchen_load": "light.fht_kitchen",
                    "switch.kitchen_2g": "light.kitchen",
                    "fan.kitchen_exhaust": "light.kitchen",
                },
            )

    def test_generates_control_on_off_automation(self) -> None:
        """Mirror a mapped switch state to its selected FHT light group."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            publisher = Mock()
            path = Path(temporary_directory) / "controls.yaml"
            manager = SERVER.ControlAutomationManager(path, publisher)
            automations = manager.sync(
                {
                    "switch.bathroom_1_toilet_switch_2g_switch_1":
                        "light.fht_bathroom_1_toilet_lights",
                },
                [
                    {
                        "entity_id": "switch.bathroom_1_toilet_switch_2g_switch_1",
                        "friendly_name": "Bathroom 1 Toilet Switch 2G Switch 1",
                    },
                    {
                        "entity_id": "light.fht_bathroom_1_toilet_lights",
                        "friendly_name": "Bathroom 1 Toilet Lights",
                    },
                ],
            )
            content = path.read_text(encoding="utf-8")

            self.assertEqual(len(automations), 2)
            self.assertTrue(automations[0]["alias"].startswith("FHT - "))
            self.assertIn('to: "on"', content)
            self.assertIn('to: "off"', content)
            self.assertIn("action: light.turn_on", content)
            self.assertIn("action: light.turn_off", content)
            self.assertIn("brightness_pct: 100", content)
            self.assertIn(
                "not is_state('light.fht_bathroom_1_toilet_lights', 'on')",
                content,
            )
            self.assertIn(
                "not is_state('light.fht_bathroom_1_toilet_lights', 'off')",
                content,
            )
            self.assertIn(
                "entity_id: light.fht_bathroom_1_toilet_lights",
                content,
            )
            publisher.reload_automations.assert_called_once_with()

    def test_generates_named_actual_load_automation(self) -> None:
        """Mirror a source switch to a named switch-channel load."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "controls.yaml"
            manager = SERVER.ControlAutomationManager(path)
            source_switch = "switch.bathroom_1_toilet_switch_2g_switch_1"
            load_switch = "switch.bathroom_1_toilet_switch_2g_switch_2"
            automations = manager.sync(
                {},
                [
                    {"entity_id": source_switch, "friendly_name": "Toilet Switch"},
                    {"entity_id": load_switch, "friendly_name": "Toilet Load"},
                ],
                load_target_assignments={source_switch: load_switch},
                actual_loads={load_switch: "Exhaust Fan"},
                reload_automations=False,
            )
            content = path.read_text(encoding="utf-8")

        self.assertEqual(len(automations), 1)
        self.assertEqual(automations[0]["light_group_name"], "Exhaust Fan")
        self.assertIn("action: switch.turn_on", content)
        self.assertIn("action: switch.turn_off", content)
        self.assertIn(f"entity_id: {load_switch}", content)
        self.assertNotIn("brightness_pct", content)

    def test_generates_every_selected_control_action(self) -> None:
        """Generate one persistent automation for each selected dropdown item."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "controls.yaml"
            manager = SERVER.ControlAutomationManager(path)
            assignment_id = (
                "button:device-123|zha|remote_button_short_press|button"
            )
            automations = manager.sync(
                {},
                [
                    {
                        "entity_id": "light.fht_kitchen_all_lights",
                        "friendly_name": "Kitchen All Lights",
                    },
                    {
                        "entity_id": "switch.office_speaker",
                        "friendly_name": "Office Speaker",
                    },
                ],
                [{"device_id": "device-123", "friendly_name": "Kitchen Button"}],
                actual_loads={"switch.office_speaker": "Office Speaker"},
                action_assignments={
                    assignment_id: [
                        "light_group:light.fht_kitchen_all_lights",
                        "actual_load:switch.office_speaker",
                    ]
                },
                reload_automations=False,
            )
            content = path.read_text(encoding="utf-8")

        self.assertEqual(len(automations), 2)
        self.assertIn("action: light.toggle", content)
        self.assertIn("action: switch.toggle", content)

    def test_generates_button_and_inovelli_actual_load_actions(self) -> None:
        """Allow button and Inovelli gestures to control a named load."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "controls.yaml"
            manager = SERVER.ControlAutomationManager(path)
            load_switch = "switch.bathroom_1_toilet_switch_2g_switch_2"
            button_assignment = (
                "button:device-123|zha|remote_button_short_press|button"
            )
            inovelli_assignment = (
                "event.bathroom_switch_button_up|multi_press_1"
            )
            automations = manager.sync(
                {},
                [
                    {"entity_id": load_switch, "friendly_name": "Toilet Load"},
                    {
                        "entity_id": "event.bathroom_switch_button_up",
                        "friendly_name": "Bathroom Switch Button Up",
                    },
                ],
                [{"device_id": "device-123", "friendly_name": "Wall Button"}],
                load_target_assignments={
                    button_assignment: load_switch,
                    inovelli_assignment: load_switch,
                },
                actual_loads={load_switch: "Exhaust Fan"},
                reload_automations=False,
            )
            content = path.read_text(encoding="utf-8")

        self.assertEqual(len(automations), 2)
        self.assertIn("action: switch.toggle", content)
        self.assertIn("action: switch.turn_on", content)
        self.assertNotIn("brightness_pct", content)

    def test_generates_bedroom_sleep_mode_switch_automation(self) -> None:
        """Set Sleep on switch ON and restore the active solar mode on OFF."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "controls.yaml"
            manager = SERVER.ControlAutomationManager(path)
            switch_id = "switch.bedroom_2_switch_3g_switch_3"
            mode_entity_id = "input_select.fht_bedroom_2_mode"
            automations = manager.sync(
                {},
                [
                    {
                        "entity_id": switch_id,
                        "friendly_name": "Bailey's Bedroom Switch 3G Switch 3",
                    },
                ],
                mode_assignments={switch_id: mode_entity_id},
                reload_automations=False,
            )
            content = path.read_text(encoding="utf-8")

        self.assertEqual(len(automations), 1)
        self.assertEqual(automations[0]["action"], "room_mode")
        self.assertIn("Set Sleep / Restore Solar Mode", automations[0]["action_label"])
        self.assertIn(f"entity_id: {switch_id}", content)
        self.assertIn(f"entity_id: {mode_entity_id}", content)
        self.assertIn("option: Sleep", content)
        self.assertIn("option: Day", content)
        self.assertIn("option: Night", content)
        self.assertIn("option: Armed Away", content)
        self.assertIn("option: Armed Stay Kids", content)

    def test_generates_toddler_mode_button_automation(self) -> None:
        """Allow a stateless device press to activate one bedroom's Toddler mode."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "controls.yaml"
            manager = SERVER.ControlAutomationManager(path)
            assignment_id = "button:device-1|zha|remote_button_short_press|button"
            mode_entity_id = "input_select.fht_bedroom_1_mode"
            automations = manager.sync(
                {},
                [],
                [{"device_id": "device-1", "friendly_name": "Bedroom 1 Button"}],
                mode_assignments={assignment_id: f"{mode_entity_id}|Toddler"},
                reload_automations=False,
            )
            content = path.read_text(encoding="utf-8")

        self.assertEqual(len(automations), 1)
        self.assertEqual(automations[0]["mode_option"], "Toddler")
        self.assertIn("trigger: device", content)
        self.assertIn("type: remote_button_short_press", content)
        self.assertIn("data: {option: Toddler}", content)
        self.assertNotIn("id: restore", content)

    def test_generates_door_open_close_automation(self) -> None:
        """Map an assigned door sensor to light-group on/off actions."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "doors.yaml"
            manager = SERVER.DoorAutomationManager(path)
            automations = manager.sync(
                {"binary_sensor.bathroom_1_door": "light.fht_bathroom_1_all_lights"},
                [
                    {"entity_id": "binary_sensor.bathroom_1_door", "friendly_name": "Bathroom 1 Door"},
                    {"entity_id": "light.fht_bathroom_1_all_lights", "friendly_name": "Bathroom 1 All Lights"},
                ],
            )
            content = path.read_text(encoding="utf-8")

        self.assertEqual(len(automations), 1)
        self.assertTrue(automations[0]["id"].startswith("fht_door_"))
        self.assertIn('to: "on"', content)
        self.assertIn('to: "off"', content)
        self.assertIn("action: light.turn_on", content)
        self.assertIn("action: light.turn_off", content)

    def test_generic_door_actions_generate_persistent_automations(self) -> None:
        """Compile every Door Actions selection through the shared action model."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "controls.yaml"
            manager = SERVER.ControlAutomationManager(path)
            door_id = "binary_sensor.pantry_door"
            automations = manager.sync(
                {},
                [
                    {"entity_id": door_id, "friendly_name": "Pantry Door"},
                    {
                        "entity_id": "light.fht_pantry_all_lights",
                        "friendly_name": "Pantry All Lights",
                    },
                    {
                        "entity_id": "switch.pantry_exhaust",
                        "friendly_name": "Pantry Exhaust",
                    },
                ],
                action_assignments={
                    f"door:{door_id}": [
                        "light_group:light.fht_pantry_all_lights",
                        "switch_target:switch.pantry_exhaust",
                    ]
                },
                reload_automations=False,
            )
            content = path.read_text(encoding="utf-8")

        self.assertEqual(len(automations), 2)
        self.assertTrue(all(item["trigger_kind"] == "door" for item in automations))
        self.assertIn(f"entity_id: {door_id}", content)
        self.assertIn('to: "on"', content)
        self.assertIn('to: "off"', content)
        self.assertIn("action: light.turn_on", content)
        self.assertIn("action: light.turn_off", content)
        self.assertIn("action: switch.turn_on", content)
        self.assertIn("action: switch.turn_off", content)

    def test_mode_door_action_persists_brightness_and_color(self) -> None:
        """Apply saved light behavior only during the selected house mode."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            settings = SERVER.SwitchControlSettings(
                Path(temporary_directory) / "settings.json"
            )
            assignment_id = "door:binary_sensor.pantry_door|sleep"
            action_setting = {
                "enabled": True,
                "brightness_pct": 25,
                "color_mode": "kelvin",
                "color_kelvin": 2700,
                "color_rgb": [255, 128, 64],
            }
            saved = settings.save_actions(
                assignment_id,
                ["light_group:light.fht_pantry_all_lights"],
                action_setting,
            )
            path = Path(temporary_directory) / "controls.yaml"
            automations = SERVER.ControlAutomationManager(path).sync(
                {},
                [
                    {"entity_id": "binary_sensor.pantry_door", "friendly_name": "Pantry Door"},
                    {"entity_id": "light.fht_pantry_all_lights", "friendly_name": "Pantry All Lights"},
                ],
                action_assignments=saved["action_assignments"],
                action_settings=saved["action_settings"],
                reload_automations=False,
            )
            content = path.read_text(encoding="utf-8")

        self.assertEqual(saved["action_settings"][assignment_id], action_setting)
        self.assertEqual(len(automations), 1)
        self.assertIn("'Sleep'", content)
        self.assertIn("brightness_pct: 25", content)
        self.assertIn("color_temp_kelvin: 2700", content)

    def test_door_timeout_survives_sensor_dropouts_restarts_and_reloads(self) -> None:
        """A door left open turns its lights off after the timeout even if the sensor drops out or Home Assistant restarts."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            settings = SERVER.SwitchControlSettings(Path(temporary_directory) / "settings.json")
            door = "binary_sensor.bedroom_2_closet_door"
            saved = settings.save_door_card(
                f"door:{door}",
                ["light_group:light.fht_bedroom_2_closet_lights"],
                {"day": {"enabled": True, "brightness_pct": 100}, "night": {"enabled": True, "brightness_pct": 30}},
                5,
            )
            path = Path(temporary_directory) / "controls.yaml"
            SERVER.ControlAutomationManager(path).sync(
                {},
                [
                    {"entity_id": door, "friendly_name": "Bedroom 2 Closet Door"},
                    {"entity_id": "light.fht_bedroom_2_closet_lights", "friendly_name": "Bedroom 2 Closet Lights"},
                ],
                action_assignments=saved["action_assignments"],
                action_settings=saved["action_settings"],
                reload_automations=False,
            )
            content = path.read_text(encoding="utf-8")
        automations = [part for part in content.split("\n  - id: ")[1:] if f"entity_id: {door}\n" in part]
        self.assertTrue(automations)
        for block in automations:
            # Coming back from unavailable is not a new opening.
            self.assertIn('to: "on"\n        not_from: [unavailable, unknown]\n        id: turn_on', block)
            # The in-run delay, plus a backup that a restart or reload cannot cancel.
            self.assertIn("- delay:\n                  minutes: 5\n", block)
            self.assertIn("trigger: template", block)
            self.assertIn(f"(now() - states.{door}.last_changed).total_seconds() >= 300", block)
            self.assertIn("id: door_timeout\n", block)
            self.assertIn("                id: door_timeout\n            sequence:", block)

    def test_door_rule_tone_reaches_only_lights_that_can_show_it(self) -> None:
        """Door cards save a tone per mode; automations apply it to colour lights only."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            settings = SERVER.SwitchControlSettings(Path(temporary_directory) / "settings.json")
            saved = settings.save_door_card(
                "door:binary_sensor.hall_door",
                ["light_group:light.hall_strip", "light_group:light.hall_plain", "light_group:light.fht_hall_all_lights"],
                {
                    "day": {"enabled": True, "brightness_pct": 70, "color_mode": "kelvin", "color_kelvin": 5500},
                    "night": {"enabled": True, "brightness_pct": 30, "color_mode": "adaptive"},
                },
                5,
            )
            self.assertEqual(saved["action_settings"]["door:binary_sensor.hall_door|day"]["color_kelvin"], 5500)
            self.assertEqual(saved["action_settings"]["door:binary_sensor.hall_door|night"]["color_mode"], "adaptive")
            path = Path(temporary_directory) / "controls.yaml"
            SERVER.ControlAutomationManager(path).sync(
                {},
                [
                    {"entity_id": "binary_sensor.hall_door", "friendly_name": "Hall Door"},
                    {"entity_id": "light.hall_strip", "friendly_name": "Hall Strip", "supported_color_modes": ["color_temp"]},
                    {"entity_id": "light.hall_plain", "friendly_name": "Hall Plain", "supported_color_modes": ["brightness"]},
                ],
                action_assignments=saved["action_assignments"],
                action_settings=saved["action_settings"],
                reload_automations=False,
            )
            content = path.read_text(encoding="utf-8")

        def blocks(target: str) -> list[str]:
            return [part for part in content.split("\n  - id: ") if f"entity_id: {target}\n" in part]

        strip, plain, group = (blocks(target) for target in ("light.hall_strip", "light.hall_plain", "light.fht_hall_all_lights"))
        self.assertEqual(len(strip), 2)
        self.assertEqual(sum("color_temp_kelvin: 5500" in part for part in strip), 1)
        self.assertEqual(sum("state_attr('sun.sun', 'elevation')" in part for part in strip), 1)
        self.assertEqual(len(plain), 2)
        self.assertFalse(any("color_temp_kelvin" in part for part in plain))
        self.assertTrue(all("brightness_pct: " in part for part in plain))
        self.assertEqual(sum("color_temp_kelvin: 5500" in part for part in group), 1)

    def test_disabled_mode_door_action_does_not_generate(self) -> None:
        """Keep configured actions dormant while their mode checkbox is off."""
        automations = SERVER.ControlAutomationManager.describe(
            {},
            [],
            action_assignments={
                "door:binary_sensor.pantry_door|day": [
                    "light_group:light.fht_pantry_all_lights"
                ]
            },
            action_settings={
                "door:binary_sensor.pantry_door|day": {"enabled": False}
            },
        )

        self.assertEqual(automations, [])

    def test_syncs_shared_controls_to_their_light_group(self) -> None:
        """Bring every assigned switch back in line with one group state."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "controls.yaml"
            manager = SERVER.ControlAutomationManager(path)
            automations = manager.sync(
                {
                    "switch.bedroom_1_switch_1": "light.fht_bedroom_1_fan_lights",
                    "switch.bedroom_1_switch_2": "light.fht_bedroom_1_fan_lights",
                },
                [
                    {
                        "entity_id": "switch.bedroom_1_switch_1",
                        "friendly_name": "Bedroom 1 Switch 1",
                    },
                    {
                        "entity_id": "switch.bedroom_1_switch_2",
                        "friendly_name": "Bedroom 1 Switch 2",
                    },
                    {
                        "entity_id": "light.fht_bedroom_1_fan_lights",
                        "friendly_name": "Bedroom 1 Fan Lights",
                    },
                ],
            )
            content = path.read_text(encoding="utf-8")

        self.assertEqual(len(automations), 3)
        self.assertIn(
            "Sync Assigned Controls",
            {item["action_label"] for item in automations},
        )
        self.assertIn('entity_id: light.fht_bedroom_1_fan_lights', content)
        self.assertIn("action: switch.turn_on", content)
        self.assertIn("action: switch.turn_off", content)
        self.assertIn('entity_id: switch.bedroom_1_switch_1', content)
        self.assertIn('entity_id: switch.bedroom_1_switch_2', content)

    def test_generates_inovelli_gesture_automations(self) -> None:
        """Map Up to ON, Down to OFF, and Config to toggle."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "controls.yaml"
            manager = SERVER.ControlAutomationManager(
                path
            )
            automations = manager.sync(
                {
                    "event.kitchen_switch_1g_button_up|multi_press_1":
                        "light.fht_kitchen_all_lights",
                    "event.kitchen_switch_1g_button_down|multi_press_2":
                        "light.fht_kitchen_all_lights",
                    "event.kitchen_switch_1g_button_config|long_press":
                        "light.fht_kitchen_all_lights",
                },
                [
                    {
                        "entity_id": "event.kitchen_switch_1g_button_up",
                        "friendly_name": "Kitchen Switch 1G Button (Up)",
                    },
                    {
                        "entity_id": "event.kitchen_switch_1g_button_down",
                        "friendly_name": "Kitchen Switch 1G Button (Down)",
                    },
                    {
                        "entity_id": "event.kitchen_switch_1g_button_config",
                        "friendly_name": "Kitchen Switch 1G Button (Config)",
                    },
                    {
                        "entity_id": "light.fht_kitchen_all_lights",
                        "friendly_name": "Kitchen All Lights",
                    },
                ],
                reload_automations=False,
            )
            content = path.read_text(encoding="utf-8")
            self.assertEqual(len(automations), 3)
            self.assertEqual(
                {automation["action"] for automation in automations},
                {"turn_on", "turn_off", "toggle"},
            )
            self.assertIn("action: light.turn_on", content)
            self.assertIn("action: light.turn_off", content)
            self.assertIn("action: light.toggle", content)
            self.assertEqual(content.count("wait_template:"), 3)
            self.assertEqual(content.count('timeout: "00:05:00"'), 3)
            self.assertIn("brightness_pct: 100", content)
            self.assertIn("attributes.event_type == 'multi_press_1' }}", content)
            self.assertIn("attributes.event_type == 'multi_press_2' }}", content)
            self.assertIn("attributes.event_type == 'long_press' }}", content)

    def test_generates_named_matter_button_toggle_automation(self) -> None:
        """Map an IKEA Matter button event to a persistent light toggle."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "controls.yaml"
            manager = SERVER.ControlAutomationManager(path)
            automations = manager.sync(
                {
                    "event.office_desk_button_button_1|multi_press_1":
                        "light.fht_office_all_lights",
                },
                [
                    {
                        "entity_id": "event.office_desk_button_button_1",
                        "friendly_name": "Office Desk Button Button (1)",
                    },
                    {
                        "entity_id": "light.fht_office_all_lights",
                        "friendly_name": "Office All Lights",
                    },
                ],
                reload_automations=False,
            )
            content = path.read_text(encoding="utf-8")

        self.assertEqual(len(automations), 1)
        self.assertEqual(automations[0]["action"], "toggle")
        self.assertIn("wait_template:", content)
        self.assertIn('timeout: "00:05:00"', content)
        self.assertIn("continue_on_timeout: false", content)
        self.assertIn("action: light.toggle", content)
        self.assertIn("attributes.event_type == 'multi_press_1' }}", content)

    @patch.object(SERVER, "urlopen")
    def test_reads_supervisor_app_update_status(
        self,
        mock_urlopen: Mock,
    ) -> None:
        """Expose installed and latest App versions to the interface."""
        mock_urlopen.return_value = MockResponse(
            {
                "result": "ok",
                "data": {
                    "version": "0.2.42",
                    "version_latest": "0.2.43",
                    "update_available": True,
                },
            }
        )

        status = SERVER.SupervisorAppInfo(
            token="token",
            info_url="http://supervisor/addons/self/info",
        ).fetch()

        self.assertEqual(status["installed_version"], "0.2.42")
        self.assertEqual(status["available_version"], "0.2.43")
        self.assertTrue(status["update_available"])

    def test_beta_mode_follows_app_option_environment(self) -> None:
        """Enable Beta mode only when the startup script exports it."""
        with patch.dict(SERVER.os.environ, {"FHT_BETA_MODE": "1"}):
            self.assertTrue(SERVER.beta_mode_enabled())
        with patch.dict(SERVER.os.environ, {"FHT_BETA_MODE": "0"}):
            self.assertFalse(SERVER.beta_mode_enabled())
        with patch.dict(SERVER.os.environ, {}, clear=True):
            self.assertFalse(SERVER.beta_mode_enabled())

    def test_beta_mode_option_defaults_off(self) -> None:
        """Keep Beta mode disabled for installations that do not opt in."""
        config = CONFIG_PATH.read_text(encoding="utf-8")
        launcher = CONFIG_PATH.with_name("run.sh").read_text(encoding="utf-8")
        self.assertIn("  beta_mode: false\n", config)
        self.assertIn("  beta_mode: bool\n", config)
        self.assertIn("bashio::config.true 'beta_mode'", launcher)
        self.assertIn("export FHT_BETA_MODE", launcher)

    def test_groups_are_renamed_to_fht_ids_and_settings_follow(self) -> None:
        """Rename App groups to fht_ IDs and update saved actions to match."""
        registry = [
            {"entity_id": "light.bedroom_5_fan_lights", "unique_id": "fht_bedroom_5_fan_lights", "platform": "group"},
            {"entity_id": "light.fht_kitchen_all_lights", "unique_id": "fht_kitchen_all_lights", "platform": "group"},
            {"entity_id": "binary_sensor.bath_group", "unique_id": "fht_presence_group_abc", "platform": "template"},
            {"entity_id": "light.user_lamp_group", "unique_id": "fht_user", "platform": "group", "config_entry_id": "ui"},
        ]
        organizer = SERVER.HomeAssistantRegistryOrganizer("token", "ws://test")
        sent = []
        def commands(batch):
            sent.append(batch)
            return [registry] if batch[0]["type"] == "config/entity_registry/list" else [None] * len(batch)
        with patch.object(organizer, "_commands", side_effect=commands):
            renames = organizer.normalize_group_entity_ids(
                {"fht_presence_group_abc": "binary_sensor.fht_bath_group_presence"})
        self.assertEqual(renames, {
            "light.bedroom_5_fan_lights": "light.fht_bedroom_5_fan_lights",
            "binary_sensor.bath_group": "binary_sensor.fht_bath_group_presence",
        })
        self.assertEqual(sent[-1][0], {"type": "config/entity_registry/update",
                                       "entity_id": "light.bedroom_5_fan_lights",
                                       "new_entity_id": "light.fht_bedroom_5_fan_lights"})
        with tempfile.TemporaryDirectory() as directory:
            settings = Path(directory)
            (settings / "switch_control_settings.json").write_text(json.dumps({
                "action_assignments": {"switch.a": ["light_group:light.bedroom_5_fan_lights",
                                                    "light_group:light.bedroom_5_fan_lights_extra"]}}))
            (settings / "presence_light_group_timings.json").write_text(json.dumps({
                "binary_sensor.toilet": {"parent_groups": ["binary_sensor.bath_group"]}}))
            (settings / "untouched.json").write_text("{}")
            self.assertEqual(SERVER.rename_entity_ids_in_settings(settings, renames), 2)
            actions = json.loads((settings / "switch_control_settings.json").read_text())["action_assignments"]["switch.a"]
            parents = json.loads((settings / "presence_light_group_timings.json").read_text())["binary_sensor.toilet"]["parent_groups"]
        self.assertEqual(actions, ["light_group:light.fht_bedroom_5_fan_lights", "light_group:light.bedroom_5_fan_lights_extra"])
        self.assertEqual(parents, ["binary_sensor.fht_bath_group_presence"])

    def test_retired_all_lights_actions_keep_the_same_lights(self) -> None:
        """Move saved All Lights actions to the room's group plus lights outside it."""
        with tempfile.TemporaryDirectory() as directory:
            settings = Path(directory)
            package = settings / "groups.yaml"
            package.write_text(
                "# fht_replaced_group: light.fht_bedroom_4_all_lights -> light.fht_bedroom_4_fan_lights, light.bedroom_4_lamp\n")
            replacements = SERVER.generated_light_group_replacements(package)
            (settings / "switch_control_settings.json").write_text(json.dumps({
                "action_assignments": {"switch.a": ["light_group:light.fht_bedroom_4_all_lights", "light_group:light.other"]},
                "default": "light.fht_bedroom_4_all_lights"}))
            (settings / "presence_light_group_assignments.json").write_text(json.dumps({
                "binary_sensor.bedroom_4": ["light.fht_bedroom_4_all_lights"]}))
            self.assertEqual(SERVER.replace_entity_ids_in_settings(settings, replacements), 2)
            control = json.loads((settings / "switch_control_settings.json").read_text())
            presence = json.loads((settings / "presence_light_group_assignments.json").read_text())
        self.assertEqual(control["action_assignments"]["switch.a"], [
            "light_group:light.fht_bedroom_4_fan_lights", "light_group:light.bedroom_4_lamp", "light_group:light.other"])
        self.assertEqual(control["default"], "light.fht_bedroom_4_fan_lights")
        self.assertEqual(presence["binary_sensor.bedroom_4"], ["light.fht_bedroom_4_fan_lights", "light.bedroom_4_lamp"])

    def test_light_group_cleanup_matches_by_unique_id(self) -> None:
        """Keep a renamed current group; remove an old group with another entity ID."""
        registry = [
            {"entity_id": "light.kids_fan", "unique_id": "fht_bedroom_5_fan_lights", "platform": "group", "categories": {}},
            {"entity_id": "light.bedroom_5_all_lights", "unique_id": "fht_bedroom_5_all_lights", "platform": "group"},
        ]
        organizer = SERVER.HomeAssistantRegistryOrganizer("token", "ws://test")
        sent = []
        def commands(batch):
            sent.append(batch)
            return [registry] if batch[0]["type"] == "config/entity_registry/list" else [None] * len(batch)
        with patch.object(organizer, "_commands", side_effect=commands), \
                patch.object(organizer, "_light_group_category_id", return_value="cat"):
            count = organizer.categorize_light_groups(
                attempts=1, expected_entity_ids={"light.fht_bedroom_5_fan_lights"})
        self.assertEqual(count, 1)
        removals = [command["entity_id"] for command in sent[-1] if command["type"] == "config/entity_registry/remove"]
        self.assertEqual(removals, ["light.bedroom_5_all_lights"])

    def test_cleanup_removes_only_unprovided_unavailable_app_entities(self) -> None:
        """Delete old App entities, keeping anything still configured or not the App's."""
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory)
            (config / "packages").mkdir()
            (config / "configuration.yaml").write_text("homeassistant:\n  packages: !include_dir_named packages\n")
            (config / "packages" / "future_homes_tech_light_groups.yaml").write_text(
                "# fht_replaced_group: light.fht_bedroom_6_desk_lights -> light.bedroom_6_desk_light\n"
                "light:\n  - platform: group\n    unique_id: fht_bedroom_5_fan_lights\n")
            (config / "packages" / "future_homes_tech_presence_automations.yaml").write_text(
                'automation:\n  - id: "fht_presence_current"\n')
            registry = [
                {"entity_id": "light.bedroom_5_all_lights", "unique_id": "fht_bedroom_5_all_lights", "platform": "group"},
                {"entity_id": "light.fht_bedroom_5_fan_lights", "unique_id": "fht_bedroom_5_fan_lights", "platform": "group"},
                {"entity_id": "automation.old", "unique_id": "fht_presence_old", "platform": "automation"},
                {"entity_id": "automation.current", "unique_id": "fht_presence_current", "platform": "automation"},
                {"entity_id": "automation.still_on", "unique_id": "fht_presence_live", "platform": "automation"},
                {"entity_id": "light.user_group", "unique_id": "abc123", "platform": "group"},
                {"entity_id": "light.bedroom_4_all_lights", "unique_id": "bedroom_4_all_lights", "platform": "group"},
                {"entity_id": "light.bedroom_6_desk_lights", "unique_id": "fht_bedroom_6_desk_lights", "platform": "group"},
                {"entity_id": "light.bedroom_6_lamp_light", "unique_id": "bedroom_6_lamp_light", "platform": "group"},
                {"entity_id": "binary_sensor.ui_template", "unique_id": "fht_ui", "platform": "template", "config_entry_id": "x"},
            ]
            states = [
                {"entity_id": "light.bedroom_5_all_lights", "state": "unavailable"},
                {"entity_id": "light.fht_bedroom_5_fan_lights", "state": "off"},
                {"entity_id": "automation.old", "state": "unavailable"},
                {"entity_id": "automation.current", "state": "unavailable"},
                {"entity_id": "automation.still_on", "state": "on"},
                {"entity_id": "light.user_group", "state": "unavailable"},
                {"entity_id": "light.bedroom_4_all_lights", "state": "unavailable"},
                {"entity_id": "light.bedroom_6_desk_lights", "state": "unavailable"},
                {"entity_id": "light.bedroom_6_lamp_light", "state": "unavailable"},
                {"entity_id": "binary_sensor.ui_template", "state": "unavailable"},
            ]
            organizer = SERVER.HomeAssistantRegistryOrganizer("token", "ws://test")
            sent = []
            def commands(batch):
                sent.append(batch)
                return [registry] if batch[0]["type"] == "config/entity_registry/list" else [None] * len(batch)
            with patch.object(organizer, "_commands", side_effect=commands):
                removed = organizer.cleanup_retired_managed_entities(states, config)

        self.assertEqual(removed, ["light.bedroom_5_all_lights", "automation.old", "light.bedroom_4_all_lights",
                                   "light.bedroom_6_desk_lights", "light.bedroom_6_lamp_light"])
        self.assertEqual(sent[-1], [
            {"type": "config/entity_registry/remove", "entity_id": "light.bedroom_5_all_lights"},
            {"type": "config/entity_registry/remove", "entity_id": "automation.old"},
            {"type": "config/entity_registry/remove", "entity_id": "light.bedroom_4_all_lights"},
            {"type": "config/entity_registry/remove", "entity_id": "light.bedroom_6_desk_lights"},
            {"type": "config/entity_registry/remove", "entity_id": "light.bedroom_6_lamp_light"},
        ])

    def test_websocket_commands_share_one_connection(self) -> None:
        """Reuse one authenticated connection; reopen once if it went stale."""
        opened = []
        replies = {}

        def open_socket(url):
            connection = Mock(name=f"socket{len(opened)}")
            connection.stale = False
            opened.append(connection)
            replies[connection] = [{"type": "auth_required"}, {"type": "auth_ok"}]
            return connection, bytearray()

        def send(connection, message):
            if "id" in message:
                if connection.stale:
                    raise BrokenPipeError("closed")
                replies[connection].append({"id": message["id"], "type": "result", "success": True, "result": message["type"]})

        def receive(connection, buffered):
            return replies[connection].pop(0)

        SERVER._WEBSOCKET_POOL.close()
        with patch.object(SERVER, "_open_websocket", side_effect=open_socket), \
                patch.object(SERVER, "_send_websocket_json", side_effect=send), \
                patch.object(SERVER, "_receive_websocket_json", side_effect=receive), \
                patch.object(SERVER, "_send_websocket_frame"):
            self.assertEqual(SERVER.execute_websocket_commands("t", "ws://ha", [{"type": "a"}]), ["a"])
            self.assertEqual(SERVER.execute_websocket_commands("t", "ws://ha", [{"type": "b"}, {"type": "c"}]), ["b", "c"])
            self.assertEqual(len(opened), 1)
            opened[0].stale = True
            self.assertEqual(SERVER.execute_websocket_commands("t", "ws://ha", [{"type": "d"}]), ["d"])
            self.assertEqual(len(opened), 2)
        SERVER._WEBSOCKET_POOL.close()

    def test_retired_entities_wait_for_approval(self) -> None:
        """List retired App entities; delete only approved ones that still qualify."""
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            handler = object.__new__(SERVER.FutureHomesTechRequestHandler)
            handler.retired_approvals = SERVER.RetiredEntityApprovals(data)
            handler.headers = {}
            handler.access_admin = Mock()
            handler.inventory = Mock()
            handler.inventory.fetch.return_value = {"entities": [
                {"entity_id": "light.old_a", "friendly_name": "Old A"}, {"entity_id": "light.old_b"}]}
            found = [{"entity_id": "light.old_a", "platform": "group", "unique_id": "fht_a"},
                     {"entity_id": "light.old_b", "platform": "group", "unique_id": "fht_b"}]
            handler.registry_organizer = Mock()
            handler.registry_organizer.find_retired_managed_entities.return_value = found
            handler.registry_organizer.cleanup_retired_managed_entities.side_effect = (
                lambda entities, config, approved: sorted(approved))

            listed = handler._retired_entities(None, None)
            self.assertEqual([item["entity_id"] for item in listed["items"]], ["light.old_a", "light.old_b"])
            self.assertEqual(listed["items"][0]["name"], "Old A")
            handler.registry_organizer.cleanup_retired_managed_entities.assert_not_called()

            result = handler._retired_entities({"entities": ["light.old_a", "light.not_retired"], "auto_remove": True}, {})
            self.assertEqual(result["removed"], ["light.old_a"])
            self.assertEqual([item["entity_id"] for item in result["items"]], ["light.old_b"])
            self.assertTrue(result["auto_remove"])
            handler.access_admin.check_csrf.assert_called_once()
            journals = list((data / "maintenance/removed").glob("*.json"))
            self.assertEqual(json.loads(journals[0].read_text())["entries"], [found[0]])

    def test_room_devices_group_entities_by_room(self) -> None:
        handler = object.__new__(SERVER.FutureHomesTechRequestHandler)
        handler.inventory = Mock()
        handler.inventory.fetch.return_value = {"entities": [
            {"entity_id": "light.b", "friendly_name": "Bravo", "area": "Bedroom 6"},
            {"entity_id": "switch.a", "friendly_name": "Alpha", "area": "Bedroom 6"},
            {"entity_id": "sensor.loose", "friendly_name": "Loose", "area": ""},
            {"entity_id": "light.kitchen", "friendly_name": "Kitchen", "area": "Kitchen", "state": "on"},
            {"entity_id": "sensor.kitchen_battery", "friendly_name": "Kitchen Battery", "area": "Kitchen", "state": "87", "unit_of_measurement": "%"},
            *({"entity_id": f"sensor.kitchen_bulb_{suffix}", "friendly_name": f"Kitchen Bulb {label}", "area": "Kitchen"}
              for suffix, label in (("firmware", "Firmware"), ("lqi", "LQI"), ("rssi", "RSSI"), ("identify", "Identify"),
                                    ("on_level", "On level"), ("on_off_transition_time", "On/Off transition time"),
                                    ("power_on_behavior", "Power-on behavior"), ("start_up_on_off", "Power on level"))),
            {"entity_id": "number.kitchen_bulb_off_transition_time", "friendly_name": "Kitchen Bulb Off transition time", "area": "Kitchen"},
            {"entity_id": "select.kitchen_pendant_power_on_behavior_2", "friendly_name": "Kitchen Pendant Power-on behavior 2", "area": "Kitchen"},
            {"entity_id": "select.kitchen_bulb_behaviour", "friendly_name": "Kitchen Bulb Power On Behaviour (startup)", "area": "Kitchen"},
            {"entity_id": "sensor.kitchen_bulb_battery_type", "friendly_name": "Kitchen Bulb Battery type", "area": "Kitchen"},
            {"entity_id": "sensor.kitchen_bulb_voltage", "friendly_name": "Kitchen Bulb Battery Voltage", "area": "Kitchen"},
            {"entity_id": "light.hue_bridge", "friendly_name": "Hue Bridge", "area": "Bridges"},
            {"entity_id": "sensor.kitchen_firmware_updates_count", "friendly_name": "Firmware updates count", "area": "Kitchen"},
        ]}
        handler.room_aliases = Mock()
        handler.room_aliases.read.return_value = {"Bedroom 6": "Chloe's Bedroom"}
        rooms = handler._room_devices()
        self.assertEqual([room["name"] for room in rooms], ["Chloe's Bedroom", "Kitchen", "Unassigned"])
        self.assertEqual([entity["entity_id"] for entity in rooms[0]["entities"]], ["switch.a", "light.b"])
        # Diagnostic and configuration entities are left out; only ones ending that way,
        # except power-on behavior, which is hidden wherever it appears.
        self.assertEqual([entity["entity_id"] for entity in rooms[1]["entities"]],
                         ["sensor.kitchen_firmware_updates_count", "light.kitchen", "sensor.kitchen_battery"])
        self.assertEqual([(entity["state"], entity["unit"]) for entity in rooms[1]["entities"]],
                         [("", ""), ("on", ""), ("87", "%")])

    def test_normalizes_and_sorts_entities(self) -> None:
        """Build a compact sorted inventory from Home Assistant states."""
        entities = SERVER.normalize_entities(
            [
                {
                    "entity_id": "switch.office",
                    "state": "on",
                    "attributes": {"friendly_name": "Office Switch"},
                },
                {
                    "entity_id": "light.kitchen",
                    "state": "off",
                    "last_changed": "2026-07-28T01:00:00+00:00",
                    "attributes": {
                        "friendly_name": "Kitchen Lights",
                        "device_class": "light",
                        "min": 50,
                        "max": 90,
                        "step": 1,
                    },
                },
            ]
        )

        self.assertEqual(
            [entity["entity_id"] for entity in entities],
            ["light.kitchen", "switch.office"],
        )
        self.assertEqual(entities[0]["domain"], "light")
        self.assertEqual(entities[0]["friendly_name"], "Kitchen Lights")
        self.assertEqual(entities[0]["device_class"], "light")
        self.assertEqual(entities[0]["minimum"], 50)
        self.assertEqual(entities[0]["maximum"], 90)
        self.assertEqual(entities[0]["step"], 1)

    def test_exposes_matter_button_event_types(self) -> None:
        """Include Matter gestures needed by Inovelli assignments."""
        entities = SERVER.normalize_entities(
            [
                {
                    "entity_id": "event.kitchen_switch_1g_button_up",
                    "state": "2026-08-01T12:00:00+00:00",
                    "attributes": {
                        "friendly_name": "Kitchen Switch 1G Button (Up)",
                        "event_types": [
                            "multi_press_1",
                            "multi_press_2",
                            "long_press",
                            "long_release",
                        ],
                    },
                }
            ]
        )
        self.assertEqual(
            entities[0]["event_types"],
            [
                "long_press",
                "long_release",
                "multi_press_1",
                "multi_press_2",
            ],
        )

    def test_exposes_group_area_and_members(self) -> None:
        """Include generated group metadata needed by the Groups UI."""
        entities = SERVER.normalize_entities(
            [
                {
                    "entity_id": "light.fht_kitchen_all_lights",
                    "state": "off",
                    "attributes": {
                        "friendly_name": "Kitchen All Lights",
                        "fht_area": "Kitchen",
                        "entity_id": [
                            "light.kitchen_can_light_1",
                            "light.kitchen_can_light_2",
                        ],
                    },
                }
            ]
        )

        self.assertEqual(entities[0]["area"], "Kitchen")
        self.assertEqual(
            entities[0]["members"],
            [
                "light.kitchen_can_light_1",
                "light.kitchen_can_light_2",
            ],
        )

    def test_filters_excluded_domains_and_input_helpers(self) -> None:
        """Remove excluded domains and every input helper domain."""
        entities = [
            {"entity_id": "light.kitchen", "domain": "light"},
            {
                "entity_id": "automation.good_morning",
                "domain": "automation",
            },
            {"entity_id": "calendar.family", "domain": "calendar"},
            {
                "entity_id": "conversation.home_assistant",
                "domain": "conversation",
            },
            {
                "entity_id": "device_tracker.phone",
                "domain": "device_tracker",
            },
            {
                "entity_id": "input_boolean.guest_mode",
                "domain": "input_boolean",
            },
            {"entity_id": "sun.sun", "domain": "sun"},
            {"entity_id": "todo.shopping", "domain": "todo"},
            {"entity_id": "update.core", "domain": "update"},
            {"entity_id": "weather.home", "domain": "weather"},
        ]

        filtered = SERVER.filter_entities(entities)

        self.assertEqual(
            [entity["entity_id"] for entity in filtered],
            ["light.kitchen"],
        )

    def test_filters_identify_and_calibrate_buttons(self) -> None:
        """Remove Identify and Calibrate buttons without hiding others."""
        entities = [
            {
                "entity_id": "button.camera_identify",
                "friendly_name": "Identify",
                "domain": "button",
            },
            {
                "entity_id": "button.thermostat_action",
                "friendly_name": "Calibrate Thermostat",
                "domain": "button",
            },
            {
                "entity_id": "button.router_restart",
                "friendly_name": "Restart Router",
                "domain": "button",
            },
            {
                "entity_id": "button.identification_mode",
                "friendly_name": "Identification Mode",
                "domain": "button",
            },
        ]

        filtered = SERVER.filter_entities(entities)

        self.assertEqual(
            [entity["entity_id"] for entity in filtered],
            [
                "button.router_restart",
                "button.identification_mode",
            ],
        )

    def test_fetches_inventory_without_logging(self) -> None:
        """Fetch enriched states without logging entity records."""
        payload = [
            {
                "entity_id": "sensor.temperature",
                "state": "72",
                "last_changed": "2026-07-28T01:00:00+00:00",
                "last_updated": "2026-07-28T01:01:00+00:00",
                "attributes": {
                    "friendly_name": "Temperature",
                    "device_class": "temperature",
                    "unit_of_measurement": "°F",
                },
            }
        ]

        inventory_service = SERVER.EntityInventory(
            token="test-token",
            states_url="http://homeassistant.test/api/states",
            websocket_url="ws://homeassistant.test/api/websocket",
        )

        with (
            patch.object(
                SERVER,
                "urlopen",
                return_value=MockResponse(payload),
            ),
            patch.object(
                SERVER,
                "fetch_entity_integrations",
                return_value={
                    "sensor.temperature": "matter",
                },
            ),
            patch("builtins.print") as mocked_print,
        ):
            inventory = inventory_service.fetch()

        self.assertEqual(inventory["count"], 1)
        self.assertEqual(
            inventory["entities"][0]["entity_id"],
            "sensor.temperature",
        )
        self.assertEqual(
            inventory["entities"][0]["integration"],
            "matter",
        )
        mocked_print.assert_not_called()

    def test_reuses_inventory_until_an_explicit_refresh(self) -> None:
        """Build the full entity cache once and refresh only when requested."""
        payload = [
            {
                "entity_id": "sensor.temperature",
                "state": "72",
                "attributes": {"friendly_name": "Temperature"},
            }
        ]
        inventory_service = SERVER.EntityInventory(
            token="test-token",
            states_url="http://homeassistant.test/api/states",
            websocket_url="ws://homeassistant.test/api/websocket",
        )
        with (
            patch.object(
                SERVER,
                "urlopen",
                side_effect=[MockResponse(payload), MockResponse(payload)],
            ) as mocked_urlopen,
            patch.object(SERVER, "fetch_entity_integrations", return_value={}),
        ):
            inventory_service.fetch(include_all=True)
            inventory_service.fetch(include_all=True)
            inventory_service.fetch(include_all=True, force=True)

        self.assertEqual(mocked_urlopen.call_count, 2)

    def test_live_revision_does_not_cancel_requested_full_refresh(self) -> None:
        """A state event must not masquerade as a completed full refresh."""
        inventory_service = SERVER.EntityInventory(
            token="test-token",
            states_url="http://homeassistant.test/api/states",
            websocket_url="ws://homeassistant.test/api/websocket",
        )
        inventory_service._cached_entities = {
            "light.kitchen": {
                "entity_id": "light.kitchen",
                "domain": "light",
                "state": "off",
                "friendly_name": "Kitchen",
            }
        }
        inventory_service._cached_generated_at = datetime.now(
            timezone.utc
        ).isoformat()
        inventory_service._cached_complete_at_monotonic = -1.0
        inventory_service._live_connected = True

        entered = threading.Event()
        release = threading.Event()

        class RefreshGate:
            def __enter__(self) -> None:
                entered.set()
                release.wait(timeout=2)

            def __exit__(self, *args: object) -> None:
                return None

        inventory_service._refresh_lock = RefreshGate()
        result: list[dict[str, object]] = []
        with patch.object(
            inventory_service,
            "_fetch_full_inventory",
        ) as full_refresh:
            worker = threading.Thread(
                target=lambda: result.append(
                    inventory_service.fetch(include_all=True, force=True)
                )
            )
            worker.start()
            self.assertTrue(entered.wait(timeout=1))
            inventory_service._apply_state_changed(
                "light.kitchen",
                {
                    "entity_id": "light.kitchen",
                    "state": "on",
                    "attributes": {"friendly_name": "Kitchen"},
                },
            )
            release.set()
            worker.join(timeout=2)

        self.assertFalse(worker.is_alive())
        full_refresh.assert_called_once_with()
        self.assertEqual(result[0]["entities"][0]["state"], "on")

    def test_shared_projections_use_one_home_assistant_state_snapshot(self) -> None:
        """Serve lighting and security from one REST snapshot."""
        payload = [
            {
                "entity_id": "light.fht_entry_all_lights",
                "state": "off",
                "attributes": {
                    "friendly_name": "Entry All Lights",
                    "fht_area": "Entry",
                },
            },
            {
                "entity_id": "binary_sensor.entry_door_sensor",
                "state": "off",
                "attributes": {
                    "friendly_name": "Entry Door Sensor",
                    "device_class": "door",
                    "fht_area": "Entry",
                },
            },
            {
                "entity_id": "sensor.entry_door_battery",
                "state": "84",
                "attributes": {
                    "friendly_name": "Entry Door Battery",
                    "device_class": "battery",
                    "fht_area": "Entry",
                },
            },
        ]
        with tempfile.TemporaryDirectory() as directory:
            inventory_service = SERVER.EntityInventory(
                token="test-token",
                states_url="http://homeassistant.test/api/states",
                websocket_url="ws://homeassistant.test/api/websocket",
                config_directory=Path(directory),
            )
            with (
                patch.object(
                    SERVER,
                    "urlopen",
                    return_value=MockResponse(payload),
                ) as mocked_urlopen,
                patch.object(SERVER, "fetch_entity_integrations", return_value={}),
            ):
                inventory_service.fetch_lighting()
                inventory_service.fetch_security()

        self.assertEqual(mocked_urlopen.call_count, 1)

    def test_state_change_event_updates_snapshot_and_revision(self) -> None:
        """Merge a live state event without another full-state request."""
        payload = [
            {
                "entity_id": "light.fht_kitchen_all_lights",
                "state": "off",
                "attributes": {
                    "friendly_name": "Kitchen All Lights",
                    "fht_area": "Kitchen",
                },
            }
        ]
        inventory_service = SERVER.EntityInventory(
            token="test-token",
            states_url="http://homeassistant.test/api/states",
            websocket_url="ws://homeassistant.test/api/websocket",
        )
        with (
            patch.object(
                SERVER,
                "urlopen",
                return_value=MockResponse(payload),
            ) as mocked_urlopen,
            patch.object(SERVER, "fetch_entity_integrations", return_value={}),
        ):
            initial = inventory_service.fetch_lighting()
            inventory_service._apply_state_changed(
                "light.fht_kitchen_all_lights",
                {
                    "entity_id": "light.fht_kitchen_all_lights",
                    "state": "on",
                    "attributes": {
                        "friendly_name": "Kitchen All Lights",
                        "brightness": 180,
                    },
                },
            )
            updated = inventory_service.fetch_lighting()

        self.assertEqual(mocked_urlopen.call_count, 1)
        self.assertGreater(updated["revision"], initial["revision"])
        self.assertEqual(updated["entities"][0]["state"], "on")
        self.assertEqual(updated["entities"][0]["area"], "Kitchen")
        live_update = inventory_service.wait_for_revision(
            initial["revision"],
            timeout=0,
        )
        self.assertIn("lighting", live_update["channels"])

    def test_inventory_resolves_physical_light_area_from_registry(self) -> None:
        """Resolve excluded light Areas without relying on custom state."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_directory = Path(temporary_directory)
            storage_directory = config_directory / ".storage"
            storage_directory.mkdir()
            storage_directory.joinpath("core.area_registry").write_text(
                json.dumps(
                    {
                        "data": {
                            "areas": [
                                {
                                    "area_id": "bathroom_1",
                                    "name": "Bathroom 1",
                                }
                            ]
                        }
                    }
                ),
                encoding="utf-8",
            )
            storage_directory.joinpath("core.device_registry").write_text(
                json.dumps(
                    {
                        "data": {
                            "devices": [
                                {
                                    "id": "toilet-light-device",
                                    "area_id": "bathroom_1",
                                }
                            ]
                        }
                    }
                ),
                encoding="utf-8",
            )
            storage_directory.joinpath("core.entity_registry").write_text(
                json.dumps(
                    {
                        "data": {
                            "entities": [
                                {
                                    "entity_id": (
                                        "light.bathroom_1_toilet_light_1"
                                    ),
                                    "device_id": "toilet-light-device",
                                }
                            ]
                        }
                    }
                ),
                encoding="utf-8",
            )
            inventory_service = SERVER.EntityInventory(
                token="test-token",
                states_url="http://homeassistant.test/api/states",
                websocket_url="ws://homeassistant.test/api/websocket",
                config_directory=config_directory,
            )
            payload = [
                {
                    "entity_id": "light.bathroom_1_toilet_light_1",
                    "state": "off",
                    "attributes": {
                        "friendly_name": "Bathroom 1 Toilet Light 1",
                    },
                }
            ]

            with (
                patch.object(
                    SERVER,
                    "urlopen",
                    return_value=MockResponse(payload),
                ),
                patch.object(
                    SERVER,
                    "fetch_entity_integrations",
                    return_value={
                        "light.bathroom_1_toilet_light_1": "hue",
                    },
                ),
            ):
                inventory = inventory_service.fetch()

        self.assertEqual(
            inventory["entities"][0]["area"],
            "Bathroom 1",
        )

    def test_security_inventory_returns_only_door_sensors(self) -> None:
        """Return current door sensors without unrelated binary sensors."""
        payload = [
            {
                "entity_id": "binary_sensor.entry_door",
                "state": "on",
                "attributes": {
                    "friendly_name": "Entry Door",
                    "device_class": "door",
                    "fht_area": "Entry",
                },
            },
            {
                "entity_id": "binary_sensor.hall_motion",
                "state": "off",
                "attributes": {
                    "friendly_name": "Hall Motion",
                    "device_class": "motion",
                    "fht_area": "Hallway",
                },
            },
            {
                "entity_id": "binary_sensor.front_doorbell_person_detected",
                "state": "off",
                "attributes": {
                    "friendly_name": "Front Doorbell Person Detected",
                    "device_class": "occupancy",
                    "fht_area": "Entry",
                },
            },
            {
                "entity_id": "binary_sensor.pantry_door_sensor",
                "state": "off",
                "attributes": {
                    "friendly_name": "Pantry Door Sensor",
                    "fht_area": "Pantry",
                },
            },
            {
                "entity_id": "binary_sensor.front_door_sensor_battery",
                "state": "off",
                "attributes": {
                    "friendly_name": "Front Door Sensor Battery",
                    "device_class": "battery",
                    "fht_area": "Entry",
                },
            },
            {
                "entity_id": "binary_sensor.front_door_sensor_moisture",
                "state": "off",
                "attributes": {
                    "friendly_name": "Front Door Sensor Moisture",
                    "device_class": "moisture",
                    "fht_area": "Entry",
                },
            },
            {
                "entity_id": "binary_sensor.front_door_sensor_tamper",
                "state": "off",
                "attributes": {
                    "friendly_name": "Front Door Sensor Tamper",
                    "device_class": "problem",
                    "fht_area": "Entry",
                },
            },
        ]
        with tempfile.TemporaryDirectory() as directory:
            inventory_service = SERVER.EntityInventory(
                token="test-token",
                states_url="http://homeassistant.test/api/states",
                websocket_url="ws://homeassistant.test/api/websocket",
                config_directory=Path(directory),
            )
            with patch.object(
                SERVER,
                "urlopen",
                return_value=MockResponse(payload),
            ):
                inventory = inventory_service.fetch_security()

        self.assertEqual(inventory["count"], 2)
        self.assertEqual(
            inventory["entities"][0]["entity_id"],
            "binary_sensor.entry_door",
        )
        self.assertEqual(inventory["entities"][0]["area"], "Entry")
        self.assertEqual(
            inventory["entities"][1]["entity_id"],
            "binary_sensor.pantry_door_sensor",
        )

    def test_lighting_inventory_excludes_retired_room_sensor_status(self) -> None:
        """Transfer lighting groups without unrelated sensor summaries."""
        payload = [
            {
                "entity_id": "light.fht_office_all_lights",
                "state": "on",
                "attributes": {
                    "friendly_name": "Office All Lights",
                    "fht_area": "Office",
                    "brightness": 180,
                },
            },
            {
                "entity_id": "binary_sensor.office_presence_occupancy",
                "state": "on",
                "attributes": {
                    "friendly_name": "Office Presence Occupancy",
                    "device_class": "occupancy",
                    "fht_area": "Office",
                },
            },
            {
                "entity_id": "sensor.office_temperature",
                "state": "72.4",
                "attributes": {
                    "friendly_name": "Office Temperature",
                    "device_class": "temperature",
                    "unit_of_measurement": "°F",
                    "fht_area": "Office",
                },
            },
            {
                "entity_id": "sensor.office_humidity",
                "state": "41.7",
                "attributes": {
                    "friendly_name": "Office Humidity",
                    "device_class": "humidity",
                    "unit_of_measurement": "%",
                    "fht_area": "Office",
                },
            },
            {
                "entity_id": "sensor.office_illuminance",
                "state": "184.6",
                "attributes": {
                    "friendly_name": "Office Illuminance",
                    "device_class": "illuminance",
                    "unit_of_measurement": "lx",
                    "fht_area": "Office",
                },
            },
            {
                "entity_id": "binary_sensor.office_door_sensor",
                "state": "on",
                "attributes": {
                    "friendly_name": "Office Door Sensor Opening",
                    "device_class": "occupancy",
                    "fht_area": "Office",
                },
            },
            {
                "entity_id": "binary_sensor.entry_front_door_sensor",
                "state": "on",
                "attributes": {
                    "friendly_name": "Entry Front Door Sensor",
                    "device_class": "door",
                    "fht_area": "Entry",
                },
            },
            {
                "entity_id": "binary_sensor.office_closet_window_sensor",
                "state": "off",
                "attributes": {
                    "friendly_name": "Office Closet Window Sensor",
                    "device_class": "window",
                    "fht_area": "Office",
                },
            },
            {
                "entity_id": "binary_sensor.office_fridge_door_sensor",
                "state": "on",
                "attributes": {
                    "friendly_name": "Office Fridge Door Sensor",
                    "device_class": "door",
                    "fht_area": "Office",
                },
            },
        ]
        with tempfile.TemporaryDirectory() as directory:
            inventory_service = SERVER.EntityInventory(
                token="test-token",
                states_url="http://homeassistant.test/api/states",
                websocket_url="ws://homeassistant.test/api/websocket",
                config_directory=Path(directory),
            )
            with patch.object(
                SERVER,
                "urlopen",
                return_value=MockResponse(payload),
            ):
                inventory = inventory_service.fetch_lighting()
        self.assertEqual(inventory["count"], 1)
        self.assertEqual(inventory["entities"][0]["entity_id"], "light.fht_office_all_lights")
        self.assertNotIn("room_status", inventory)

    def test_requires_supervisor_token(self) -> None:
        """Reject entity requests when App API access is unavailable."""
        inventory_service = SERVER.EntityInventory(
            token="",
            states_url="http://homeassistant.test/api/states",
            websocket_url="ws://homeassistant.test/api/websocket",
        )

        with self.assertRaises(SERVER.HomeAssistantAPIError):
            inventory_service.fetch()

    def test_formats_protect_status_for_helper(self) -> None:
        """Format statuses and armed profiles as sensor values."""
        self.assertEqual(
            SERVER.arm_mode_state_value({"status": "disarmed"}),
            "Disarmed",
        )
        self.assertEqual(
            SERVER.arm_mode_state_value({"status": "arming"}),
            "Arming",
        )
        self.assertEqual(
            SERVER.arm_mode_state_value(
                {
                    "status": "armed",
                    "arm_profile_name": "Arm Away",
                }
            ),
            "Arm Away",
        )

    def test_caches_protect_arm_profiles(self) -> None:
        """Load arm profiles once and reuse them for status polling."""
        protect_api = SERVER.ProtectAPI(
            api_key="test-protect-key",
            webhook_url=(
                "https://unifi.fht.internal/proxy/protect/"
                "integration/v1/alarm-manager/webhook/device_offline"
            ),
        )
        responses = [
            MockResponse(
                [
                    {
                        "id": "profile-1",
                        "name": "Arm Away",
                        "activationDelay": 0,
                    }
                ]
            ),
            MockResponse(
                {
                    "id": "nvr-1",
                    "name": "Main NVR",
                    "armMode": {
                        "status": "armed",
                        "armProfileId": "profile-1",
                    },
                }
            ),
            MockResponse(
                {
                    "id": "nvr-1",
                    "name": "Main NVR",
                    "armMode": {
                        "status": "disabled",
                        "armProfileId": "profile-1",
                    },
                }
            ),
        ]

        with patch.object(
            SERVER,
            "urlopen",
            side_effect=responses,
        ) as mocked_urlopen:
            profiles = protect_api.refresh_arm_profiles()
            armed = protect_api.fetch_arm_mode()
            disarmed = protect_api.fetch_arm_mode(force=True)

        self.assertEqual(profiles[0]["name"], "Arm Away")
        self.assertEqual(armed["arm_profile_name"], "Arm Away")
        self.assertEqual(disarmed["status"], "disarmed")
        self.assertEqual(mocked_urlopen.call_count, 3)
        self.assertEqual(
            mocked_urlopen.call_args_list[0].args[0].full_url,
            "https://unifi.fht.internal/proxy/protect/"
            "integration/v1/arm-profiles",
        )

    def test_publishes_protect_status_to_input_text_helper(self) -> None:
        """Update the managed Home Assistant helper through its service."""
        publisher = SERVER.HomeAssistantHelperPublisher(
            token="test-token",
            services_url="http://homeassistant.test/api/services",
        )

        with patch.object(
            SERVER,
            "urlopen",
            return_value=MockResponse([]),
        ) as mocked_urlopen:
            publisher.publish("Armed")

        request = mocked_urlopen.call_args.args[0]
        self.assertEqual(
            request.full_url,
            "http://homeassistant.test/api/services/"
            "input_text/set_value",
        )
        self.assertEqual(request.method, "POST")
        self.assertEqual(
            json.loads(request.data),
            {
                "entity_id": (
                    "input_text.future_homes_tech_protect_arm_mode"
                ),
                "value": "Armed",
            },
        )
        self.assertEqual(
            request.get_header("Authorization"),
            "Bearer test-token",
        )

    def test_reloads_every_managed_yaml_domain(self) -> None:
        """Reload helpers, commands, timers, and automations in order."""
        publisher = SERVER.HomeAssistantHelperPublisher(
            token="test-token",
            services_url="http://homeassistant.test/api/services",
        )

        with patch.object(
            SERVER,
            "urlopen",
            return_value=MockResponse([]),
        ) as mocked_urlopen:
            publisher.reload_managed_entities()

        self.assertEqual(mocked_urlopen.call_count, 10)
        self.assertEqual(
            [
                call.args[0].full_url
                for call in mocked_urlopen.call_args_list
            ],
            [
                "http://homeassistant.test/api/services/"
                "input_boolean/reload",
                "http://homeassistant.test/api/services/"
                "input_button/reload",
                "http://homeassistant.test/api/services/"
                "input_datetime/reload",
                "http://homeassistant.test/api/services/"
                "input_number/reload",
                "http://homeassistant.test/api/services/"
                "input_select/reload",
                "http://homeassistant.test/api/services/"
                "input_text/reload",
                "http://homeassistant.test/api/services/"
                "template/reload",
                "http://homeassistant.test/api/services/"
                "rest_command/reload",
                "http://homeassistant.test/api/services/"
                "timer/reload",
                "http://homeassistant.test/api/services/"
                "automation/reload",
            ],
        )

    def test_reloads_all_yaml_after_light_group_change(self) -> None:
        """Reload all reloadable YAML after generator output changes."""
        publisher = SERVER.HomeAssistantHelperPublisher(
            token="test-token",
            services_url="http://homeassistant.test/api/services",
        )

        with patch.object(
            SERVER,
            "urlopen",
            return_value=MockResponse([]),
        ) as mocked_urlopen:
            publisher.reload_all()

        request = mocked_urlopen.call_args.args[0]
        self.assertEqual(
            request.full_url,
            "http://homeassistant.test/api/services/"
            "homeassistant/reload_all",
        )

    def test_categorizes_generated_light_group_helpers(self) -> None:
        """Assign only managed light groups to the Helpers category."""
        organizer = SERVER.HomeAssistantRegistryOrganizer(
            token="test-token",
            websocket_url="ws://homeassistant.test/api/websocket",
        )
        category_id = "category-light-groups"
        entities = [
            {
                "entity_id": "light.fht_kitchen_all_lights",
                "unique_id": "fht_kitchen_all_lights",
                "platform": "group",
                "categories": {},
            },
            {
                "entity_id": "light.fht_hall_all_lights",
                "unique_id": "fht_hall_all_lights",
                "platform": "group",
                "categories": {"helpers": category_id},
            },
            {
                "entity_id": "light.local_group",
                "unique_id": "local_group",
                "platform": "group",
                "categories": {},
            },
            {
                "entity_id": "light.fht_pantry_all_lights",
                "unique_id": "fht_pantry_all_lights",
                "platform": "group",
                "categories": {"helpers": category_id},
            },
        ]

        with patch.object(
            organizer,
            "_commands",
            side_effect=[
                [
                    [
                        {
                            "category_id": category_id,
                            "name": "Future Homes Tech Light Groups",
                        }
                    ]
                ],
                [entities],
                [{"entity_entry": entities[0]}],
            ],
        ) as mocked_commands:
            count = organizer.categorize_light_groups(
                attempts=1,
                retry_delay=0,
                expected_entity_ids={
                    "light.fht_kitchen_all_lights",
                    "light.fht_hall_all_lights",
                },
            )

        self.assertEqual(count, 2)
        self.assertEqual(mocked_commands.call_count, 3)
        self.assertEqual(
            mocked_commands.call_args_list[2].args[0],
            [
                {
                    "type": "config/entity_registry/update",
                    "entity_id": "light.fht_kitchen_all_lights",
                    "categories": {
                        "helpers": category_id,
                    },
                },
                {
                    "type": "config/entity_registry/remove",
                    "entity_id": "light.fht_pantry_all_lights",
                },
            ],
        )

    def test_retired_group_cleanup_waits_for_active_replacement_and_no_references(self) -> None:
        organizer = SERVER.HomeAssistantRegistryOrganizer(token="", websocket_url="")
        old = "light.bedroom_6_fan_lights"
        new = "light.fht_bedroom_6_fan_lights"
        registry = [
            {"entity_id": old, "platform": "group", "unique_id": "bedroom_6_fan_lights"},
            {"entity_id": new, "platform": "group", "unique_id": "fht_bedroom_6_fan_lights"},
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "packages").mkdir()
            (root / "configuration.yaml").write_text("homeassistant: {}\n")
            settings = root / "settings"
            settings.mkdir()
            reference = root / "packages" / "other.yaml"
            reference.write_text(f"target: {old}\n")
            with patch.object(organizer, "_commands", side_effect=lambda commands: [registry] if commands[0]["type"].endswith("/list") else [None]) as commands:
                states = [{"entity_id": old, "state": "unavailable"}, {"entity_id": new, "state": "off"}]
                self.assertEqual(organizer.cleanup_retired_fan_groups({new}, states, root, settings), 0)
                reference.unlink()
                self.assertEqual(organizer.cleanup_retired_fan_groups({new}, states, root, settings), 1)
                self.assertEqual(commands.call_args.args[0], [{"type": "config/entity_registry/remove", "entity_id": old}])
                self.assertEqual(organizer.cleanup_retired_fan_groups({new}, [{"entity_id": new, "state": "unavailable"}], root, settings), 0)

    def test_reads_expected_light_groups_from_package(self) -> None:
        """Read managed entity IDs used for stale-helper cleanup."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            package_path = (
                Path(temporary_directory)
                / "future_homes_tech_light_groups.yaml"
            )
            package_path.write_text(
                "light:\n"
                "  - platform: group\n"
                "    unique_id: fht_pantry_lights\n"
                "  - platform: group\n"
                "    unique_id: fht_stairway_lights\n",
                encoding="utf-8",
            )

            entity_ids = SERVER.generated_light_group_entity_ids(
                package_path
            )

        self.assertEqual(
            entity_ids,
            {
                "light.fht_pantry_lights",
                "light.fht_stairway_lights",
            },
        )

    def test_creates_light_groups_category_when_missing(self) -> None:
        """Create the native Helpers category once when absent."""
        organizer = SERVER.HomeAssistantRegistryOrganizer(
            token="test-token",
            websocket_url="ws://homeassistant.test/api/websocket",
        )

        with patch.object(
            organizer,
            "_commands",
            side_effect=[
                [[]],
                [
                    {
                        "category_id": "new-category",
                            "name": "Future Homes Tech Light Groups",
                    }
                ],
            ],
        ) as mocked_commands:
            category_id = organizer._light_group_category_id()

        self.assertEqual(category_id, "new-category")
        self.assertEqual(
            mocked_commands.call_args_list[1].args[0],
            [
                {
                    "type": "config/category_registry/create",
                    "scope": "helpers",
                    "name": "Future Homes Tech Light Groups",
                    "icon": "mdi:lightbulb-group",
                }
            ],
        )

    def test_renames_legacy_light_groups_category(self) -> None:
        """Preserve the existing category while updating its display name."""
        organizer = SERVER.HomeAssistantRegistryOrganizer(
            token="test-token",
            websocket_url="ws://homeassistant.test/api/websocket",
        )

        with patch.object(
            organizer,
            "_commands",
            side_effect=[
                [
                    [
                        {
                            "category_id": "legacy-light-groups",
                            "name": "Light Groups",
                        }
                    ]
                ],
                [{}],
            ],
        ) as mocked_commands:
            category_id = organizer._light_group_category_id()

        self.assertEqual(category_id, "legacy-light-groups")
        self.assertEqual(
            mocked_commands.call_args_list[1].args[0],
            [
                {
                    "type": "config/category_registry/update",
                    "category_id": "legacy-light-groups",
                    "name": "Future Homes Tech Light Groups",
                    "icon": "mdi:lightbulb-group",
                }
            ],
        )

    def test_categorizes_only_managed_climate_helpers(self) -> None:
        """Keep unrelated FHT helpers out of the Climate category."""
        organizer = SERVER.HomeAssistantRegistryOrganizer(
            token="test-token",
            websocket_url="ws://homeassistant.test/api/websocket",
        )
        category_id = "future-homes-tech-climate"
        entities = [
            {
                "entity_id": "input_boolean.fht_vacation_mode",
                "categories": {},
            },
            {
                "entity_id": "input_number.fht_on_peak_target_cool",
                "categories": {"helpers": category_id},
            },
            {
                "entity_id": "input_text.fht_weather_entity",
                "categories": {},
            },
            {
                "entity_id": "input_text.fht_room_config_note",
                "categories": {},
            },
            {
                "entity_id": "input_number.local_target_cool",
                "categories": {},
            },
        ]

        with patch.object(
            organizer,
            "_climate_category_id",
            return_value=category_id,
        ), patch.object(
            organizer,
            "_commands",
            side_effect=[[entities], [{}]],
        ) as mocked_commands:
            count = organizer.categorize_climate_helpers(
                attempts=1,
                retry_delay=0,
            )

        self.assertEqual(count, 3)
        self.assertEqual(
            mocked_commands.call_args_list[1].args[0],
            [
                {
                    "type": "config/entity_registry/update",
                    "entity_id": "input_boolean.fht_vacation_mode",
                    "categories": {"helpers": category_id},
                },
                {
                    "type": "config/entity_registry/update",
                    "entity_id": "input_text.fht_weather_entity",
                    "categories": {"helpers": category_id},
                },
            ],
        )

    def test_categorizes_door_time_input_text_helpers(self) -> None:
        """Assign every door-time input text to the Door Timers category."""
        organizer = SERVER.HomeAssistantRegistryOrganizer(
            token="test-token",
            websocket_url="ws://homeassistant.test/api/websocket",
        )
        category_id = "future-homes-tech-door-timers"
        entities = [
            {
                "entity_id": "input_text.bedroom_2_closet_door_time",
                "categories": {},
            },
            {
                "entity_id": "input_text.pantry_door_time",
                "categories": {"helpers": category_id},
            },
            {
                "entity_id": "input_text.bedroom_2_custom_name",
                "categories": {},
            },
            {
                "entity_id": "input_number.entry_door_time",
                "categories": {},
            },
        ]

        with patch.object(
            organizer,
            "_door_timer_category_id",
            return_value=category_id,
        ), patch.object(
            organizer,
            "_commands",
            side_effect=[[entities], [{}]],
        ) as mocked_commands:
            count = organizer.categorize_door_timer_helpers(
                attempts=1,
                retry_delay=0,
            )

        self.assertEqual(
            SERVER.DOOR_TIMER_CATEGORY_NAME,
            "Future Homes Tech Door Timers",
        )
        self.assertEqual(count, 2)
        self.assertEqual(
            mocked_commands.call_args_list[1].args[0],
            [
                {
                    "type": "config/entity_registry/update",
                    "entity_id": "input_text.bedroom_2_closet_door_time",
                    "categories": {"helpers": category_id},
                }
            ],
        )

    def test_categorizes_managed_automations(self) -> None:
        """Assign App-managed automations to their purpose categories."""
        organizer = SERVER.HomeAssistantRegistryOrganizer(
            token="test-token",
            websocket_url="ws://homeassistant.test/api/websocket",
        )
        entities = [
            {
                "entity_id": "automation.fht_control_bedroom",
                "unique_id": "fht_control_1234567890abcdef",
                "categories": {},
            },
            {
                "entity_id": "automation.fht_control_sync_bedroom",
                "unique_id": "fht_control_sync_1234567890abcdef",
                "categories": {},
            },
            {
                "entity_id": "automation.future_homes_tech_alarm_exterior_door_entry_delay",
                "unique_id": "future_homes_tech_alarm_exterior_door_entry_delay",
                "categories": {},
            },
            {
                "entity_id": "automation.fht_climate_verify_rate_mode_targets",
                "unique_id": "fht_climate_verify_rate_mode_targets",
                "categories": {},
            },
            {
                "entity_id": "automation.fht_scene_light_schedule_outside",
                "unique_id": "fht_scene_light_schedule_1234567890abcdef",
                "categories": {},
            },
            {
                "entity_id": "automation.local_automation",
                "unique_id": "local_automation",
                "categories": {},
            },
        ]

        category_ids = {
            SERVER.DOOR_AUTOMATION_CATEGORY_NAME: "door-category",
            SERVER.SWITCH_AUTOMATION_CATEGORY_NAME: "switch-category",
            SERVER.SWITCH_ACTIVATION_CATEGORY_NAME: "activation-category",
            SERVER.LIGHT_SYNC_CATEGORY_NAME: "sync-category",
            SERVER.CLIMATE_AUTOMATION_CATEGORY_NAME: "climate-category",
            SERVER.PRESENCE_AUTOMATION_CATEGORY_NAME: "presence-category",
            SERVER.MOTION_AUTOMATION_CATEGORY_NAME: "motion-category",
            SERVER.SCENE_AUTOMATION_CATEGORY_NAME: "scene-category",
            SERVER.DEVICE_ALARM_AUTOMATION_CATEGORY_NAME: "device-alarm-category",
        }
        with patch.object(
            organizer,
            "_automation_category_id",
            side_effect=lambda name: category_ids[name],
        ), patch.object(
            organizer,
            "_commands",
            side_effect=[[entities], [{"entity_entry": entities[0]}]],
        ) as mocked_commands:
            count = organizer.categorize_automations(
                attempts=1,
                retry_delay=0,
            )

        self.assertEqual(count, 5)
        self.assertEqual(
            mocked_commands.call_args_list[1].args[0],
            [
                {
                    "type": "config/entity_registry/update",
                    "entity_id": "automation.fht_control_bedroom",
                    "categories": {"automation": "activation-category"},
                },
                {
                    "type": "config/entity_registry/update",
                    "entity_id": "automation.fht_control_sync_bedroom",
                    "categories": {"automation": "sync-category"},
                },
                {
                    "type": "config/entity_registry/update",
                    "entity_id": (
                        "automation.future_homes_tech_alarm_exterior_door_entry_delay"
                    ),
                    "categories": {"automation": "door-category"},
                },
                {
                    "type": "config/entity_registry/update",
                    "entity_id": (
                        "automation.fht_climate_verify_rate_mode_targets"
                    ),
                    "categories": {"automation": "climate-category"},
                },
                {
                    "type": "config/entity_registry/update",
                    "entity_id": (
                        "automation.fht_scene_light_schedule_outside"
                    ),
                    "categories": {"automation": "scene-category"},
                },
            ],
        )

    def test_serves_logo_with_png_content_type(self) -> None:
        """Serve the logo bytes instead of the single-page HTML."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            logo_content = b"\x89PNG\r\n\x1a\nlogo"
            Path(
                temporary_directory,
                "future-homes-tech-logo.png",
            ).write_bytes(logo_content)

            handler = object.__new__(
                SERVER.FutureHomesTechRequestHandler
            )
            handler.web_root = Path(temporary_directory)
            handler.wfile = io.BytesIO()
            handler.send_response = Mock()
            handler.send_header = Mock()
            handler.end_headers = Mock()

            handler._serve_asset(
                "future-homes-tech-logo.png",
                "image/png",
            )

            self.assertEqual(handler.wfile.getvalue(), logo_content)
            handler.send_header.assert_any_call(
                "Content-Type",
                "image/png",
            )
            handler.send_header.assert_any_call(
                "Cache-Control",
                "public, max-age=3600, must-revalidate",
            )

    def test_approves_groups_background_asset(self) -> None:
        """Expose the selected Groups background through Ingress."""
        self.assertEqual(
            SERVER.INTERFACE_ASSETS[
                "/fht-infinite-vertical-warp-4da39efb.webp"
            ],
            ("fht-infinite-vertical-warp-4da39efb.webp", "image/webp"),
        )

    def test_extracts_integrations_from_registry_display_data(self) -> None:
        """Decode compact entity-registry platform properties."""
        integrations = SERVER.integrations_from_registry_result(
            {
                "entities": [
                    {
                        "ei": "light.kitchen",
                        "pl": "hue",
                    },
                    {
                        "ei": "sensor.temperature",
                        "pl": "matter",
                    },
                    {
                        "ei": "sensor.no_platform",
                    },
                ]
            }
        )

        self.assertEqual(
            integrations,
            {
                "light.kitchen": "hue",
                "sensor.temperature": "matter",
            },
        )

    def test_websocket_json_frame_round_trip(self) -> None:
        """Encode and decode masked WebSocket JSON frames."""
        sending_socket, receiving_socket = socket.socketpair()
        self.addCleanup(sending_socket.close)
        self.addCleanup(receiving_socket.close)

        payload = {
            "id": 1,
            "type": "config/entity_registry/list_for_display",
        }
        SERVER._send_websocket_json(sending_socket, payload)
        received = SERVER._receive_websocket_json(
            receiving_socket,
            bytearray(),
        )

        self.assertEqual(received, payload)

    def test_derives_protect_nvr_url_from_webhook(self) -> None:
        """Reuse the configured Protect integration API base."""
        nvr_url = SERVER.protect_api_url(
            "https://unifi.fht.internal/proxy/protect/integration/v1/"
            "alarm-manager/webhook/device_offline",
            "nvrs",
        )

        self.assertEqual(
            nvr_url,
            "https://unifi.fht.internal/proxy/protect/"
            "integration/v1/nvrs",
        )

    def test_derives_protect_arm_profiles_url(self) -> None:
        """Reuse the configured Protect API base for arm profiles."""
        profiles_url = SERVER.protect_api_url(
            "https://unifi.fht.internal/proxy/protect/integration/v1/"
            "alarm-manager/webhook/device_offline",
            "arm-profiles",
        )

        self.assertEqual(
            profiles_url,
            "https://unifi.fht.internal/proxy/protect/"
            "integration/v1/arm-profiles",
        )

    def test_indexes_protect_arm_profiles(self) -> None:
        """Read arm profile names without returning unrelated fields."""
        profiles = SERVER.arm_profiles_from_payload(
            [
                {
                    "id": "profile-1",
                    "name": "Away",
                    "activationDelay": 60000,
                    "automations": ["automation-1"],
                }
            ]
        )

        self.assertEqual(
            profiles["profile-1"],
            {
                "id": "profile-1",
                "name": "Away",
                "activation_delay": 60000,
            },
        )

    def test_extracts_protect_arm_mode(self) -> None:
        """Read current status and related Protect arm-mode details."""
        arm_modes = SERVER.arm_modes_from_nvr_payload(
            {
                "id": "nvr-1",
                "name": "Main NVR",
                "armMode": {
                    "status": "armed",
                    "armProfileId": "profile-1",
                    "armedAt": 1000,
                    "willBeArmedAt": None,
                    "breachDetectedAt": None,
                    "breachEventCount": 0,
                },
            }
        )

        self.assertEqual(len(arm_modes), 1)
        self.assertEqual(arm_modes[0]["status"], "armed")
        self.assertEqual(
            arm_modes[0]["arm_profile_id"],
            "profile-1",
        )
        self.assertEqual(arm_modes[0]["nvr_name"], "Main NVR")

    def test_fetches_protect_arm_mode_with_api_key(self) -> None:
        """Query Protect without exposing the configured API key."""
        protect_api = SERVER.ProtectAPI(
            api_key="test-protect-key",
            webhook_url=(
                "https://unifi.fht.internal/proxy/protect/"
                "integration/v1/alarm-manager/webhook/device_offline"
            ),
        )
        payload = {
            "id": "nvr-1",
            "name": "Main NVR",
            "armMode": {
                "status": "disarmed",
                "armProfileId": "profile-1",
            },
        }

        responses = [
            MockResponse(payload),
            MockResponse(
                [
                    {
                        "id": "profile-1",
                        "name": "Away",
                        "activationDelay": 0,
                    }
                ]
            ),
        ]
        with patch.object(
            SERVER,
            "urlopen",
            side_effect=responses,
        ) as mocked_urlopen:
            arm_mode = protect_api.fetch_arm_mode()

        request = mocked_urlopen.call_args_list[0].args[0]
        self.assertEqual(arm_mode["status"], "disarmed")
        self.assertEqual(arm_mode["raw_status"], "disarmed")
        self.assertEqual(arm_mode["arm_profile_name"], "Away")
        self.assertEqual(
            request.full_url,
            "https://unifi.fht.internal/proxy/protect/"
            "integration/v1/nvrs",
        )
        self.assertEqual(
            request.get_header("X-api-key"),
            "test-protect-key",
        )
        profile_request = mocked_urlopen.call_args_list[1].args[0]
        self.assertEqual(
            profile_request.full_url,
            "https://unifi.fht.internal/proxy/protect/"
            "integration/v1/arm-profiles",
        )

    def test_maps_disabled_protect_status_to_disarmed(self) -> None:
        """Translate Protect's disabled status to a disarmed UI state."""
        protect_api = SERVER.ProtectAPI(
            api_key="test-protect-key",
            webhook_url=(
                "https://unifi.fht.internal/proxy/protect/"
                "integration/v1/alarm-manager/webhook/device_offline"
            ),
        )
        responses = [
            MockResponse(
                {
                    "id": "nvr-1",
                    "name": "Main NVR",
                    "armMode": {
                        "status": "disabled",
                        "armProfileId": "profile-1",
                    },
                }
            ),
            MockResponse([]),
        ]

        with patch.object(SERVER, "urlopen", side_effect=responses):
            arm_mode = protect_api.fetch_arm_mode()

        self.assertEqual(arm_mode["status"], "disarmed")
        self.assertEqual(arm_mode["raw_status"], "disabled")


class HttpReleaseGateTests(unittest.TestCase):
    """Verify request isolation and browser-facing security controls."""

    def test_configuration_posts_are_serialized(self) -> None:
        """Keep generated files and reloads in one ordered mutation lane."""
        events: list[str] = []

        class RecordingLock:
            def __enter__(self) -> None:
                events.append("lock")

            def __exit__(self, *args: object) -> None:
                events.append("unlock")

        handler = object.__new__(SERVER.FutureHomesTechRequestHandler)
        handler.path = "/api/room-modes"
        handler._request_is_allowed = Mock(return_value=True)
        handler._dispatch_POST = lambda: events.append("dispatch")

        with patch.object(
            SERVER,
            "CONFIGURATION_ACTIVATION_LOCK",
            RecordingLock(),
        ):
            handler.do_POST()

        self.assertEqual(events, ["lock", "dispatch", "unlock"])

    def test_control_posts_do_not_wait_for_configuration_lock(self) -> None:
        """Keep interactive device controls outside the save/reload lane."""
        events: list[str] = []

        class RecordingLock:
            def __enter__(self) -> None:
                events.append("lock")

            def __exit__(self, *args: object) -> None:
                events.append("unlock")

        handler = object.__new__(SERVER.FutureHomesTechRequestHandler)
        handler.path = "/api/controls/toggle"
        handler._request_is_allowed = Mock(return_value=True)
        handler._dispatch_POST = lambda: events.append("dispatch")

        with patch.object(
            SERVER,
            "CONFIGURATION_ACTIVATION_LOCK",
            RecordingLock(),
        ):
            handler.do_POST()

        self.assertEqual(events, ["dispatch"])

    def test_rejects_oversized_or_non_object_json(self) -> None:
        """Bound request memory and require one JSON object."""
        handler = object.__new__(SERVER.FutureHomesTechRequestHandler)
        handler.headers = {
            "Content-Length": str(SERVER.MAX_JSON_BODY_BYTES + 1)
        }
        handler.rfile = io.BytesIO()
        with self.assertRaises(SERVER.RequestBodyTooLarge):
            handler._read_json_object()

        body = b"[]"
        handler.headers = {"Content-Length": str(len(body))}
        handler.rfile = io.BytesIO(body)
        with self.assertRaisesRegex(ValueError, "must be an object"):
            handler._read_json_object()

    def test_index_uses_strict_nonce_csp_and_revalidation(self) -> None:
        """Serve the shell without unsafe inline-script or style permission."""
        handler = object.__new__(SERVER.FutureHomesTechRequestHandler)
        handler.web_root = MODULE_PATH.with_name("web")
        handler.headers = {}
        handler.wfile = io.BytesIO()
        handler.send_response = Mock()
        handler.send_header = Mock()
        handler.end_headers = Mock()

        handler._serve_index()

        headers = {
            call.args[0]: call.args[1]
            for call in handler.send_header.call_args_list
            if len(call.args) == 2
        }
        csp = headers["Content-Security-Policy"]
        self.assertIn("script-src 'self' 'nonce-", csp)
        self.assertIn("style-src 'self' 'nonce-", csp)
        self.assertNotIn("unsafe-inline", csp)
        self.assertEqual(
            headers["Cache-Control"],
            "no-cache, must-revalidate",
        )


if __name__ == "__main__":
    unittest.main()
