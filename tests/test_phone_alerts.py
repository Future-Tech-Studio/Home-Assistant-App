"""Tests for phone push alerts sent through the Home Assistant Companion app."""

from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

try:
    import yaml
except ImportError:  # pragma: no cover - PyYAML is optional for the suite
    yaml = None

MODULE_PATH = Path(__file__).parents[1] / "future_homes_tech_app" / "server.py"
WEB_INDEX = MODULE_PATH.parent / "web" / "index.html"
SPEC = importlib.util.spec_from_file_location("server_phone_alerts", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
SERVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SERVER)

PHONE = "notify.mobile_app_austins_iphone"
PIXEL = "notify.mobile_app_chloes_pixel_8"
SERVICES_PAYLOAD = [
    {"domain": "light", "services": {"turn_on": {}}},
    {
        "domain": "notify",
        "services": {
            "persistent_notification": {"name": "Send a persistent notification"},
            "mobile_app_austins_iphone": {
                "name": "Send a notification via mobile_app_austins_iphone"
            },
            "mobile_app_chloes_pixel_8": {},
            "send_message": {},
        },
    },
]
PHONE_ENTITIES = [
    {
        "entity_id": "sensor.austins_iphone_battery_level",
        "integration": "mobile_app",
        "device_name": "Austin's iPhone",
    },
    {
        "entity_id": "sensor.living_room_temperature",
        "integration": "zha",
        "device_name": "Living Room Sensor",
    },
]


class MockResponse:
    """Provide a context-managed JSON API response."""

    def __init__(self, payload: object) -> None:
        self._content = io.BytesIO(json.dumps(payload).encode("utf-8"))

    def __enter__(self) -> MockResponse:
        return self

    def __exit__(self, *args: object) -> None:
        """Exit the response context."""

    def read(self, size: int = -1) -> bytes:
        return self._content.read(size)


class PhoneNotifyHelperTests(unittest.TestCase):
    """Validate phone targets, naming, and the generated notify actions."""

    def test_service_ids_and_target_lists_are_validated(self) -> None:
        self.assertEqual(
            SERVER.phone_notify_service_id(" Notify.Mobile_App_Austins_iPhone "),
            PHONE,
        )
        for bad in (
            "notify.persistent_notification",
            "mobile_app_austins_iphone",
            "notify.mobile_app_",
            "siren.hallway",
            "",
            None,
        ):
            with self.subTest(bad=bad):
                self.assertEqual(SERVER.phone_notify_service_id(bad), "")
        self.assertEqual(SERVER.phone_notify_targets(None), [])
        self.assertEqual(
            SERVER.phone_notify_targets([PHONE, PHONE, PIXEL]),
            [PHONE, PIXEL],
        )
        with self.assertRaisesRegex(ValueError, "Companion app"):
            SERVER.phone_notify_targets(["siren.hallway"])
        with self.assertRaisesRegex(ValueError, "list"):
            SERVER.phone_notify_targets(PHONE)

    def test_slug_matches_home_assistant_device_naming(self) -> None:
        self.assertEqual(SERVER.phone_notify_slug("Austin's iPhone"), "austins_iphone")
        self.assertEqual(SERVER.phone_notify_slug("Chloé’s Pixel 8"), "chloes_pixel_8")
        self.assertEqual(SERVER.phone_notify_slug("  SM-G998U  "), "sm_g998u")
        self.assertEqual(SERVER.phone_notify_slug(""), "")

    def test_catalog_names_phones_after_their_device(self) -> None:
        catalog = SERVER.phone_notify_catalog(
            [PIXEL, PHONE, PHONE, "notify.send_message", ""],
            PHONE_ENTITIES,
        )
        self.assertEqual(
            catalog,
            [
                {"service": PHONE, "name": "Austin's iPhone"},
                {"service": PIXEL, "name": "Chloes Pixel 8"},
            ],
        )

    def test_action_lines_push_and_clear_with_a_tag(self) -> None:
        pushed = "".join(
            SERVER.phone_notify_action_lines(
                [PHONE], "  ", "Title", 'Msg "quoted"', tag="fht_x"
            )
        )
        self.assertEqual(
            pushed,
            "  - action: notify.mobile_app_austins_iphone\n"
            "    continue_on_error: true\n"
            "    data:\n"
            '      title: "Title"\n'
            '      message: "Msg \\"quoted\\""\n'
            "      data:\n"
            "        tag: fht_x\n",
        )
        cleared = "".join(
            SERVER.phone_notify_action_lines([PHONE], "", tag="fht_x", clear=True)
        )
        self.assertIn("  message: clear_notification\n", cleared)
        self.assertIn("    tag: fht_x\n", cleared)
        self.assertNotIn("title:", cleared)
        self.assertEqual(SERVER.phone_notify_action_lines([], "", "t", "m"), [])


class PhoneNotifyServicesTests(unittest.TestCase):
    """Discover Companion app phones from the Home Assistant services list."""

    def test_fetch_lists_companion_phones_and_caches(self) -> None:
        services = SERVER.PhoneNotifyServices(
            "token", "http://supervisor/core/api/services/"
        )
        with patch.object(
            SERVER, "urlopen", return_value=MockResponse(SERVICES_PAYLOAD)
        ) as mocked:
            self.assertEqual(services.fetch(), [PHONE, PIXEL])
            self.assertEqual(services.fetch(), [PHONE, PIXEL])
            self.assertEqual(services.known(), {PHONE, PIXEL})
        self.assertEqual(mocked.call_count, 1)
        request = mocked.call_args.args[0]
        self.assertEqual(request.full_url, "http://supervisor/core/api/services")
        self.assertEqual(request.get_header("Authorization"), "Bearer token")

    def test_unreachable_home_assistant_is_reported_without_details(self) -> None:
        services = SERVER.PhoneNotifyServices(
            "token", "http://supervisor/core/api/services"
        )
        with patch.object(
            SERVER, "urlopen", side_effect=SERVER.URLError("boom secret")
        ):
            with self.assertRaises(SERVER.HomeAssistantAPIError) as raised:
                services.fetch()
            self.assertNotIn("secret", str(raised.exception))
            self.assertIsNone(services.known())
        self.assertIsNone(SERVER.PhoneNotifyServices("", "http://x").known())

    def test_send_posts_to_the_phone_notify_service(self) -> None:
        services = SERVER.PhoneNotifyServices(
            "token", "http://supervisor/core/api/services"
        )
        with patch.object(SERVER, "urlopen", return_value=MockResponse({})) as mocked:
            services.send(PHONE, "Future Homes Tech", "Test")
        request = mocked.call_args.args[0]
        self.assertEqual(
            request.full_url,
            "http://supervisor/core/api/services/notify/mobile_app_austins_iphone",
        )
        self.assertEqual(
            json.loads(request.data),
            {"title": "Future Homes Tech", "message": "Test"},
        )
        with self.assertRaises(ValueError):
            services.send("notify.persistent_notification", "t", "m")


class FridgeAlarmPhoneTests(unittest.TestCase):
    """Add phones to refrigerator door and temperature alerts."""

    ENTITIES = [
        {
            "entity_id": "binary_sensor.garage_fridge_door",
            "domain": "binary_sensor",
            "friendly_name": "Garage Fridge Door",
            "device_class": "door",
        },
        {
            "entity_id": "sensor.garage_fridge_temperature",
            "domain": "sensor",
            "friendly_name": "Garage Fridge Temperature",
            "device_class": "temperature",
            "unit_of_measurement": "°F",
        },
        {
            "entity_id": "siren.hallway_siren",
            "domain": "siren",
            "friendly_name": "Hallway Siren",
        },
    ]
    LEGACY = {
        "kind": "door",
        "enabled": True,
        "delay_minutes": 10,
        "alert_targets": ["siren.hallway_siren"],
        "alert_behavior": "until_clear",
        "unifi_webhook": False,
    }

    def test_saved_settings_without_phones_load_unchanged(self) -> None:
        setting = SERVER.FridgeAlarmSettings.normalize("door", self.LEGACY)
        self.assertEqual(setting["notify_targets"], [])
        self.assertEqual(
            {key: value for key, value in setting.items() if key != "notify_targets"},
            self.LEGACY,
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fridge.json"
            path.write_text(
                json.dumps({"binary_sensor.garage_fridge_door": self.LEGACY}),
                encoding="utf-8",
            )
            settings = SERVER.FridgeAlarmSettings(path)
            self.assertEqual(
                settings.read()["binary_sensor.garage_fridge_door"]["notify_targets"],
                [],
            )
            saved = settings.save(
                "binary_sensor.garage_fridge_door",
                "door",
                {**self.LEGACY, "notify_targets": [PHONE]},
            )
            self.assertEqual(
                saved["binary_sensor.garage_fridge_door"]["notify_targets"], [PHONE]
            )
            with self.assertRaisesRegex(ValueError, "Companion app"):
                settings.save(
                    "binary_sensor.garage_fridge_door",
                    "door",
                    {**self.LEGACY, "notify_targets": ["notify.persistent_notification"]},
                )

    def _sync(self, notify_services: set[str] | None) -> str:
        settings = {
            "binary_sensor.garage_fridge_door": {
                "kind": "door",
                "enabled": True,
                "delay_minutes": 10,
                "alert_targets": ["siren.hallway_siren"],
                "notify_targets": [PHONE],
            },
            "sensor.garage_fridge_temperature": {
                "kind": "temperature",
                "enabled": True,
                "threshold": 40,
                "delay_minutes": 5,
                "notify_targets": [PHONE, "notify.mobile_app_old_phone"],
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory) / "fridge.yaml"
            SERVER.FridgeAlarmAutomationManager(package).sync(
                settings, self.ENTITIES, notify_services=notify_services
            )
            return package.read_text(encoding="utf-8")

    def test_automations_push_and_clear_phone_notifications(self) -> None:
        content = self._sync({PHONE})
        self.assertIn(
            "              - action: notify.mobile_app_austins_iphone\n"
            "                continue_on_error: true\n"
            "                data:\n"
            '                  title: "Refrigerator Door Alert"\n'
            '                  message: "Garage Fridge Door has been open for 10 minutes."\n'
            "                  data:\n"
            "                    tag: fht_fridge_",
            content,
        )
        self.assertIn(
            '                  title: "Refrigerator Temperature Alert"\n'
            '                  message: "Garage Fridge Temperature is {{ states(\'sensor.garage_fridge_temperature\') }}\\u00b0F. The configured limit is 40\\u00b0F."\n',
            content,
        )
        self.assertEqual(content.count("message: clear_notification"), 2)
        self.assertEqual(content.count("continue_on_error: true"), 4)
        self.assertLess(
            content.index("notify.mobile_app_austins_iphone"),
            content.index("siren.turn_on"),
        )
        self.assertLess(
            content.index("persistent_notification.dismiss"),
            content.index("clear_notification"),
        )
        self.assertNotIn("old_phone", content)
        self.assertIn("old_phone", self._sync(None))

    @unittest.skipUnless(yaml, "PyYAML is not installed")
    def test_generated_package_is_valid_yaml(self) -> None:
        package = yaml.safe_load(self._sync(None))
        door = next(
            item for item in package["automation"]
            if item["alias"] == "FHT - Garage Fridge Door Alert"
        )
        alert = door["actions"][0]["choose"][0]["sequence"]
        self.assertEqual(alert[1]["action"], PHONE)
        self.assertTrue(alert[1]["continue_on_error"])
        self.assertEqual(alert[1]["data"]["data"]["tag"], alert[0]["data"]["notification_id"])
        clear = door["actions"][0]["choose"][1]["sequence"]
        self.assertEqual(clear[1]["data"]["message"], "clear_notification")

    def test_phones_are_optional_and_off_by_default(self) -> None:
        settings = {
            "binary_sensor.garage_fridge_door": {"kind": "door", "enabled": True}
        }
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory) / "fridge.yaml"
            automations = SERVER.FridgeAlarmAutomationManager(package).sync(
                settings, self.ENTITIES
            )
            content = package.read_text(encoding="utf-8")
        self.assertEqual(automations[0]["notify_targets"], [])
        self.assertNotIn("notify.", content)
        self.assertNotIn("continue_on_error", content)


class BedroomModePhoneTests(unittest.TestCase):
    """Add phones to the Armed Away and Armed Stay Kids door alerts."""

    DOORS = [
        {
            "entity_id": "binary_sensor.bedroom_1_door",
            "friendly_name": "Bedroom 1 Door",
            "original_area": "Bedroom 1",
        }
    ]

    def test_settings_default_to_no_phones_and_validate_them(self) -> None:
        setting = SERVER.BedroomModeSettings.normalize({"armed_away_enabled": True})
        self.assertEqual(setting["armed_away_notify_targets"], [])
        self.assertEqual(setting["armed_stay_kids_notify_targets"], [])
        setting = SERVER.BedroomModeSettings.normalize(
            {
                "armed_away_notify_targets": [PHONE, PHONE],
                "armed_stay_kids_notify_targets": [PIXEL],
            }
        )
        self.assertEqual(setting["armed_away_notify_targets"], [PHONE])
        self.assertEqual(setting["armed_stay_kids_notify_targets"], [PIXEL])
        with self.assertRaisesRegex(ValueError, "Companion app"):
            SERVER.BedroomModeSettings.normalize(
                {"armed_away_notify_targets": ["siren.hallway"]}
            )
        with tempfile.TemporaryDirectory() as directory:
            store = SERVER.BedroomModeSettings(Path(directory) / "bedroom_modes.json")
            saved = store.save(
                "Bedroom 1",
                {"armed_stay_kids_enabled": True, "armed_stay_kids_notify_targets": [PHONE]},
                set(),
            )
        self.assertEqual(saved["Bedroom 1"]["armed_stay_kids_notify_targets"], [PHONE])

    def test_door_alerts_notify_phones_with_or_without_webhooks(self) -> None:
        settings = {
            "Bedroom 1": SERVER.BedroomModeSettings.normalize(
                {
                    "armed_away_enabled": True,
                    "armed_away_notify_targets": [PHONE],
                    "armed_stay_kids_enabled": True,
                    "armed_stay_kids_notify_targets": [PHONE, "notify.mobile_app_old_phone"],
                }
            )
        }
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "bedroom_modes.yaml"
            automations = SERVER.BedroomModeAutomationManager(output).sync(
                settings, [], self.DOORS, notify_services={PHONE}
            )
            content = output.read_text(encoding="utf-8")
        self.assertEqual(
            [item["mode"] for item in automations if "Bedroom" not in item["mode"]],
            ["House Mode Status", "Armed Away", "Armed Stay Kids"],
        )
        self.assertIn(
            "    actions:\n"
            "      - action: notify.mobile_app_austins_iphone\n"
            "        continue_on_error: true\n"
            "        data:\n"
            '          title: "Armed Away Door Alert"\n'
            '          message: "Bedroom 1 door opened while Armed Away."\n',
            content,
        )
        self.assertIn(
            '          title: "Armed Stay Kids Door Alert"\n'
            '          message: "Bedroom 1 door opened while Armed Stay Kids."\n',
            content,
        )
        self.assertNotIn("rest_command.", content)
        self.assertNotIn("old_phone", content)

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "bedroom_modes.yaml"
            SERVER.BedroomModeAutomationManager(
                output,
                armed_away_webhook_configured=True,
                armed_stay_kids_webhook_configured=True,
            ).sync(settings, [], self.DOORS)
            content = output.read_text(encoding="utf-8")
        self.assertLess(
            content.index("rest_command.future_homes_tech_bedroom_armed_away"),
            content.index('title: "Armed Away Door Alert"'),
        )
        self.assertIn("rest_command.future_homes_tech_bedroom_armed_stay_kids", content)
        self.assertIn("old_phone", content)

    def test_door_alerts_still_need_a_webhook_or_a_phone(self) -> None:
        settings = {
            "Bedroom 1": SERVER.BedroomModeSettings.normalize(
                {"armed_away_enabled": True, "armed_stay_kids_enabled": True}
            )
        }
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "bedroom_modes.yaml"
            automations = SERVER.BedroomModeAutomationManager(output).sync(
                settings, [], self.DOORS
            )
            content = output.read_text(encoding="utf-8")
        self.assertNotIn("Door Alert", content)
        self.assertEqual(
            [item["mode"] for item in automations],
            ["House Mode Status", "Bedroom Status"],
        )


class PhoneAlertHandlerTests(unittest.TestCase):
    """Expose phones to the interface and validate chosen phones on save."""

    def test_phone_payload_and_validation(self) -> None:
        handler = object.__new__(SERVER.FutureHomesTechRequestHandler)
        handler.phone_notify_services = Mock()
        handler.phone_notify_services.fetch.return_value = [PHONE]
        self.assertEqual(
            handler._phone_notify_payload(PHONE_ENTITIES),
            {
                "phone_targets": [{"service": PHONE, "name": "Austin's iPhone"}],
                "phone_targets_error": None,
            },
        )
        handler.phone_notify_services.fetch.side_effect = SERVER.HomeAssistantAPIError(
            "Unable to list phones from Home Assistant."
        )
        self.assertEqual(
            handler._phone_notify_payload([]),
            {
                "phone_targets": [],
                "phone_targets_error": "Unable to list phones from Home Assistant.",
            },
        )
        self.assertEqual(handler._require_known_phones([PHONE], {PHONE}), [PHONE])
        self.assertEqual(handler._require_known_phones([PHONE], None), [PHONE])
        self.assertEqual(handler._require_known_phones(None, set()), [])
        with self.assertRaisesRegex(ValueError, "signed in"):
            handler._require_known_phones([PHONE], set())

    def test_interface_offers_phone_outputs(self) -> None:
        html = WEB_INDEX.read_text(encoding="utf-8")
        self.assertIn('data-fridge-field="notify_targets"', html)
        self.assertIn('bedroomPhoneAlertPicker("armed_away_notify_targets"', html)
        self.assertIn('bedroomPhoneAlertPicker("armed_stay_kids_notify_targets"', html)
        self.assertIn('armed_away_notify_targets: list("armed_away_notify_targets")', html)
        self.assertIn(
            'armed_stay_kids_notify_targets: list("armed_stay_kids_notify_targets")',
            html,
        )
        self.assertIn('saveJson("api/phone-alerts/test"', html)
        self.assertIn("Phone: ${escapeHtml(item.name)}", html)


if __name__ == "__main__":
    unittest.main()
