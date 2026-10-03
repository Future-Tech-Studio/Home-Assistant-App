"""Tests for the site profile: one file holds the values that differ between homes."""

from __future__ import annotations

import importlib.util
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from test_server import SERVER, MODULE_PATH

ROOT = Path(__file__).parents[1]
APP = ROOT / "future_homes_tech_app"
DOCS = ROOT / "docs" / "SITE_PROFILE.md"
PROTECT_BASE = "https://unifi.fht.internal/proxy/protect/integration/v1"
THIS_HOME = {
    "protect": {
        "base_url": PROTECT_BASE,
        "webhooks": {
            "device_offline": "device_offline",
            "armed_siren": "Armed%20Siren",
            "device_alarm": "DeviceAlarm",
        },
    },
    "timezone": "America/Phoenix",
    "weather_entity": "weather.forecast_home",
    "rooms": {
        "hidden_areas": ["adopting", "bridges", "unifi"],
        "device_alarm_room_names": ["bridges", "device alarms", "fridges"],
        "sleep_source_excluded_words": ["bathroom"],
    },
    "doors": {
        "exterior_area_words": ["entry", "exterior"],
        "exterior_door_name_words": [
            "back door", "entry door", "exterior door", "front door", "patio door", "side door",
        ],
    },
    "catalog": {
        "retired_unavailable_lights": [
            "light.kitchen_1g_lights",
            "light.kitchen_switch_1g_load_control_lights",
            "light.kitchen_switch_1g_rgb_indicator_lights",
        ],
        "indicator_light_pattern": r"\b(?:rgb indicator|switch(?: \d+g)? rgb)\b",
    },
}
OTHER_HOME = {
    "protect": {
        "base_url": "https://console.example.net/proxy/protect/integration/v1/",
        "webhooks": {"armed_siren": "Armed Siren", "device_alarm": "https://alerts.example.net/hook"},
    },
    "timezone": "America/Denver",
    "weather_entity": "weather.cabin",
    "rooms": {
        "hidden_areas": ["Garage"],
        "device_alarm_room_names": ["Appliance Alerts"],
        "sleep_source_excluded_words": ["ensuite"],
    },
    "doors": {"exterior_area_words": ["mudroom"], "exterior_door_name_words": ["deck door"]},
    "catalog": {"retired_unavailable_lights": ["light.old_switch"], "indicator_light_pattern": r"\bpilot\b"},
}


def load_module(name: str, filename: str, environment: dict[str, str] | None = None):
    """Load one App module fresh so it reads the profile the way a new process would."""
    with patch.dict(os.environ, environment or {}, clear=False):
        spec = importlib.util.spec_from_file_location(name, APP / filename)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


SITE = load_module("fht_site_under_test", "fht_site.py")


class SiteProfileLoaderTests(unittest.TestCase):
    """Merge, check, and describe the profile."""

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.override = Path(self.directory.name) / "site_profile.json"

    def tearDown(self) -> None:
        self.directory.cleanup()

    def load(self, override: object = None):
        if override is not None:
            self.override.write_text(
                override if isinstance(override, str) else json.dumps(override), encoding="utf-8"
            )
        return SITE.load_site_profile(override_path=self.override)

    def test_shipped_defaults_are_this_home_unchanged(self) -> None:
        profile = self.load()
        self.assertEqual(profile.values, THIS_HOME)
        self.assertFalse(profile.override_present)
        self.assertEqual(profile.problems, ())
        self.assertEqual(profile.overridden_keys, ())
        self.assertEqual(profile.timezone, "America/Phoenix")
        self.assertEqual(
            profile.protect_webhook_url("device_offline"),
            f"{PROTECT_BASE}/alarm-manager/webhook/device_offline",
        )
        self.assertEqual(
            profile.protect_webhook_url("armed_siren"),
            f"{PROTECT_BASE}/alarm-manager/webhook/Armed%20Siren",
        )
        self.assertEqual(
            profile.protect_webhook_url("device_alarm"),
            f"{PROTECT_BASE}/alarm-manager/webhook/DeviceAlarm",
        )
        self.assertIn("Built-in defaults", profile.summary())
        self.assertEqual(profile.defaults_path, APP / "site_profile.json")

    def test_shipped_file_has_exactly_the_documented_keys(self) -> None:
        shipped = json.loads((APP / "site_profile.json").read_text(encoding="utf-8"))
        self.assertEqual({key for key, _value in SITE._flatten(shipped)}, set(SITE.SCHEMA))
        documentation = DOCS.read_text(encoding="utf-8")
        for key in SITE.SCHEMA:
            with self.subTest(key=key):
                self.assertIn(f"`{key}`", documentation)

    def test_override_replaces_only_the_keys_it_names(self) -> None:
        profile = self.load(OTHER_HOME)
        self.assertTrue(profile.override_present)
        self.assertEqual(profile.problems, ())
        self.assertEqual(profile.timezone, "America/Denver")
        self.assertEqual(profile.get("weather_entity"), "weather.cabin")
        self.assertEqual(profile.get("rooms.hidden_areas"), ["garage"])
        self.assertEqual(profile.get("rooms.device_alarm_room_names"), ["appliance alerts"])
        self.assertEqual(profile.get("doors.exterior_door_name_words"), ["deck door"])
        self.assertEqual(profile.get("catalog.retired_unavailable_lights"), ["light.old_switch"])
        self.assertEqual(
            profile.get("protect.webhooks.device_offline"), "device_offline", "untouched keys keep defaults"
        )
        self.assertEqual(
            profile.protect_webhook_url("device_offline"),
            "https://console.example.net/proxy/protect/integration/v1/alarm-manager/webhook/device_offline",
        )
        self.assertEqual(
            profile.protect_webhook_url("armed_siren"),
            "https://console.example.net/proxy/protect/integration/v1/alarm-manager/webhook/Armed%20Siren",
        )
        self.assertEqual(profile.protect_webhook_url("device_alarm"), "https://alerts.example.net/hook")
        self.assertEqual(
            profile.overridden_keys,
            (
                "protect.base_url", "protect.webhooks.armed_siren", "protect.webhooks.device_alarm",
                "timezone", "weather_entity", "rooms.hidden_areas", "rooms.device_alarm_room_names",
                "rooms.sleep_source_excluded_words", "doors.exterior_area_words",
                "doors.exterior_door_name_words", "catalog.retired_unavailable_lights",
                "catalog.indicator_light_pattern",
            ),
        )
        self.assertIn("changes 12 values", profile.summary())
        self.assertNotIn("protect.webhooks.armed_siren", self.load({"protect": {"webhooks": {"armed_siren": "Armed%20Siren"}}}).overridden_keys)

    def test_bad_values_and_unknown_keys_are_reported_and_defaults_kept(self) -> None:
        profile = self.load({
            "timezone": "Mars/Olympus",
            "weather_entity": "sensor.outside",
            "catalog": {"indicator_light_pattern": "(", "retired_unavailable_lights": ["switch.x"]},
            "rooms": {"hidden_areas": "garage"},
            "doors": {"exterior_area_words": ["", "entry"]},
            "protect": {"base_url": "https://user:private-token@console.example.net/proxy/protect/integration/v1",
                        "webhooks": {"device_alarm": "a/b"}},
            "mystery": 1,
            "typo": {"nested": True},
        })
        self.assertEqual(profile.values, THIS_HOME)
        self.assertEqual(profile.overridden_keys, ())
        self.assertEqual(len(profile.problems), 10)
        for key in (
            "timezone", "weather_entity", "catalog.indicator_light_pattern",
            "catalog.retired_unavailable_lights", "rooms.hidden_areas", "doors.exterior_area_words",
            "protect.base_url", "protect.webhooks.device_alarm", "mystery", "typo",
        ):
            with self.subTest(key=key):
                self.assertTrue(any(key in problem for problem in profile.problems))
        self.assertFalse(any("private-token" in problem for problem in profile.problems))

    def test_unreadable_override_falls_back_to_defaults(self) -> None:
        profile = self.load("{not json")
        self.assertEqual(profile.values, THIS_HOME)
        self.assertEqual(len(profile.problems), 1)
        self.assertIn("not valid JSON", profile.problems[0])
        self.assertIn("shipped defaults are in use", profile.problems[0])
        profile = self.load([1, 2])
        self.assertEqual(len(profile.problems), 1)
        self.assertIn("JSON object", profile.problems[0])
        self.assertEqual(profile.values, THIS_HOME)

    def test_describe_is_json_safe_and_complete(self) -> None:
        profile = self.load({"timezone": "Europe/London"})
        payload = json.loads(json.dumps(profile.describe()))
        self.assertEqual(payload["values"]["timezone"], "Europe/London")
        self.assertEqual(payload["overridden_keys"], ["timezone"])
        self.assertEqual(payload["override_path"], str(self.override))
        self.assertTrue(payload["override_present"])
        self.assertEqual(payload["problems"], [])
        self.assertEqual(payload["protect_webhook_urls"]["device_alarm"], f"{PROTECT_BASE}/alarm-manager/webhook/DeviceAlarm")
        self.assertIn("changes 1 value:", payload["summary"])

    def test_get_returns_copies_and_defaults(self) -> None:
        profile = self.load()
        profile.get("rooms.hidden_areas").append("garage")
        self.assertEqual(profile.get("rooms.hidden_areas"), ["adopting", "bridges", "unifi"])
        self.assertIsNone(profile.get("rooms.missing"))
        self.assertEqual(profile.get("missing", "fallback"), "fallback")
        with self.assertRaises(KeyError):
            profile.protect_webhook_url("nope")

    def test_override_path_follows_data_directory_and_explicit_setting(self) -> None:
        with patch.dict(os.environ, {"FHT_DATA_DIR": "/private/data", "FHT_SITE_PROFILE_PATH": ""}):
            self.assertEqual(SITE.default_override_path(), Path("/private/data/site_profile.json"))
        with patch.dict(os.environ, {"FHT_SITE_PROFILE_PATH": str(self.override)}):
            self.assertEqual(SITE.default_override_path(), self.override)
            self.override.write_text(json.dumps({"timezone": "Europe/Paris"}), encoding="utf-8")
            self.assertEqual(SITE.load_site_profile().timezone, "Europe/Paris")

    def test_broken_shipped_defaults_fail_loudly(self) -> None:
        defaults = Path(self.directory.name) / "defaults.json"
        defaults.write_text(json.dumps({"timezone": "America/Phoenix"}), encoding="utf-8")
        with self.assertRaises(SITE.SiteProfileError):
            SITE.load_site_profile(override_path=self.override, defaults_path=defaults)
        defaults.write_text(json.dumps({**THIS_HOME, "extra": 1}), encoding="utf-8")
        with self.assertRaises(SITE.SiteProfileError):
            SITE.load_site_profile(override_path=self.override, defaults_path=defaults)

    def test_command_answers_run_sh_and_the_terminal(self) -> None:
        def run(*arguments: str) -> subprocess.CompletedProcess:
            return subprocess.run(
                [sys.executable, "-B", str(APP / "fht_site.py"), *arguments],
                capture_output=True, text=True, timeout=30,
                env={**os.environ, "FHT_SITE_PROFILE_PATH": str(self.override)},
            )

        result = run("protect-webhook", "device_alarm")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), f"{PROTECT_BASE}/alarm-manager/webhook/DeviceAlarm")
        self.assertEqual(run("get", "timezone").stdout.strip(), "America/Phoenix")
        self.assertEqual(json.loads(run("get", "rooms.hidden_areas").stdout), ["adopting", "bridges", "unifi"])
        self.assertEqual(run("check").returncode, 0)
        self.assertEqual(json.loads(run("show").stdout)["values"], THIS_HOME)
        self.override.write_text(json.dumps({"timezone": "Nowhere/Land", "weather_entity": "weather.cabin"}), encoding="utf-8")
        result = run("check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("WARNING timezone", result.stdout)
        self.assertIn("changes 1 value: weather_entity", result.stdout)
        self.assertEqual(run("protect-webhook", "nope").returncode, 1)
        self.assertEqual(run("bogus").returncode, 2)


class SiteProfileConsumerTests(unittest.TestCase):
    """Every module that held a this-home literal now reads the profile."""

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.override = Path(self.directory.name) / "site_profile.json"
        self.override.write_text(json.dumps(OTHER_HOME), encoding="utf-8")
        self.environment = {"FHT_SITE_PROFILE_PATH": str(self.override)}

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_server_defaults_equal_the_previous_literals(self) -> None:
        self.assertEqual(SERVER.DEFAULT_PROTECT_WEBHOOK_URL, f"{PROTECT_BASE}/alarm-manager/webhook/device_offline")
        self.assertEqual(SERVER.DEFAULT_WEATHER_ENTITY, "weather.forecast_home")
        self.assertEqual(SERVER.HIDDEN_SETUP_AREAS, {"adopting", "bridges", "unifi"})
        self.assertEqual(SERVER.DEVICE_ALARM_ROOM_NAMES, {"bridges", "device alarms", "fridges"})
        self.assertEqual(SERVER.SLEEP_SOURCE_EXCLUDED_WORDS, ("bathroom",))
        self.assertEqual(SERVER.CATALOG_RETIRED_UNAVAILABLE_LIGHTS, tuple(THIS_HOME["catalog"]["retired_unavailable_lights"]))
        self.assertEqual(SERVER.CATALOG_INDICATOR_LIGHT_PATTERN, THIS_HOME["catalog"]["indicator_light_pattern"])
        self.assertEqual(SERVER.SITE_PROFILE.timezone, "America/Phoenix")

    def test_server_reads_another_home_at_start(self) -> None:
        server = load_module("server_other_home", "server.py", self.environment)
        self.assertEqual(
            server.DEFAULT_PROTECT_WEBHOOK_URL,
            "https://console.example.net/proxy/protect/integration/v1/alarm-manager/webhook/device_offline",
        )
        self.assertEqual(server.DEFAULT_WEATHER_ENTITY, "weather.cabin")
        self.assertEqual(server.HIDDEN_SETUP_AREAS, {"garage"})
        self.assertTrue(server.is_device_alarm_room_name("Appliance Alerts"))
        self.assertFalse(server.is_device_alarm_room_name("Fridges"))
        self.assertTrue(SERVER.is_device_alarm_room_name("Fridges"))
        entities = [
            {"entity_id": "light.old_switch", "domain": "light", "state": "unavailable", "members": []},
            {"entity_id": "light.kitchen_1g_lights", "domain": "light", "state": "unavailable", "members": []},
            {"entity_id": "light.hall_pilot_light", "domain": "light", "friendly_name": "Hall Pilot Light", "state": "on"},
            {"entity_id": "light.kitchen_switch_rgb_light", "domain": "light", "state": "off"},
        ]
        choices = {item["entity_id"] for group in ("light_groups", "individual_lights")
                   for item in server.action_catalog_from_entities(entities)[group]}
        self.assertEqual(choices, {"light.kitchen_1g_lights", "light.kitchen_switch_rgb_light"})
        choices = {item["entity_id"] for group in ("light_groups", "individual_lights")
                   for item in SERVER.action_catalog_from_entities(entities)[group]}
        self.assertEqual(choices, {"light.old_switch", "light.hall_pilot_light"})

    def test_sleep_sources_and_weather_channel_follow_the_profile(self) -> None:
        inventory = SERVER.EntityInventory("token", "http://test/states", "ws://test/websocket")
        self.assertIn("weather", inventory._event_channels({"entity_id": "weather.forecast_home", "domain": "weather"}))
        self.assertNotIn("weather", inventory._event_channels({"entity_id": "weather.cabin", "domain": "weather"}))
        self.assertIn("bathroom", SERVER.SLEEP_SOURCE_EXCLUDED_WORDS)
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertIn("for word in SLEEP_SOURCE_EXCLUDED_WORDS", source)
        self.assertNotIn('"bathroom" not in', source)

    def test_catalog_rules_are_passed_in_not_built_in(self) -> None:
        catalog = load_module("fht_catalog_under_test", "fht_catalog.py")
        entities = [
            {"entity_id": "light.kitchen_1g_lights", "domain": "light", "state": "unavailable", "members": []},
            {"entity_id": "light.kitchen_switch_rgb_light", "domain": "light", "state": "off"},
            {"entity_id": "light.kitchen_rgb_strip", "domain": "light", "state": "off"},
        ]
        plain = catalog.light_target_catalog(entities)
        self.assertEqual(
            {item["entity_id"] for item in plain["light_groups"] + plain["individual_lights"]},
            {"light.kitchen_1g_lights", "light.kitchen_switch_rgb_light", "light.kitchen_rgb_strip"},
        )
        home = catalog.light_target_catalog(
            entities,
            retired_unavailable_lights=THIS_HOME["catalog"]["retired_unavailable_lights"],
            indicator_light_pattern=THIS_HOME["catalog"]["indicator_light_pattern"],
        )
        self.assertEqual(
            {item["entity_id"] for item in home["light_groups"] + home["individual_lights"]},
            {"light.kitchen_rgb_strip"},
        )

    def test_light_group_generator_shares_the_indicator_pattern(self) -> None:
        generator = load_module("generator_under_test", "generate_light_groups.py")
        self.assertEqual(generator.INDICATOR_LIGHT_PATTERN, THIS_HOME["catalog"]["indicator_light_pattern"])
        self.assertTrue(generator._is_excluded("light.kitchen_switch_rgb_light", "Kitchen Switch", "matter"))
        other = load_module("generator_other_home", "generate_light_groups.py", self.environment)
        self.assertEqual(other.INDICATOR_LIGHT_PATTERN, r"\bpilot\b")
        self.assertTrue(other._is_excluded("light.hall_pilot_light", "Hall Pilot Light", "matter"))
        self.assertFalse(other._is_excluded("light.kitchen_switch_rgb_light", "Kitchen Switch", "matter"))

    def test_configure_webhooks_and_blank_device_alarm_option_use_the_profile(self) -> None:
        configure = load_module("configure_under_test", "configure.py")
        self.assertEqual(configure.PROTECT_DEVICE_OFFLINE_WEBHOOK, f"{PROTECT_BASE}/alarm-manager/webhook/device_offline")
        self.assertEqual(configure.PROTECT_ARMED_SIREN_WEBHOOK, f"{PROTECT_BASE}/alarm-manager/webhook/Armed%20Siren")
        self.assertEqual(configure.DEFAULT_DEVICE_ALARM_WEBHOOK, f"{PROTECT_BASE}/alarm-manager/webhook/DeviceAlarm")
        config_directory = Path(self.directory.name) / "homeassistant"
        config_directory.mkdir()
        (config_directory / "configuration.yaml").write_text("default_config:\n", encoding="utf-8")
        environment = {"HOMEASSISTANT_CONFIG_DIR": str(config_directory), "PROTECT_API_KEY": "key", "DEVICE_ALARM_WEBHOOK": "  "}
        with patch.dict(os.environ, environment), patch("sys.stdout", new=io.StringIO()):
            self.assertEqual(configure.main(), 0)
        package = (config_directory / "packages" / "future_homes_tech_app.yaml").read_text(encoding="utf-8")
        self.assertIn(f'url: "{PROTECT_BASE}/alarm-manager/webhook/DeviceAlarm"', package)
        self.assertIn(f'url: "{PROTECT_BASE}/alarm-manager/webhook/Armed%20Siren"', package)
        with patch.dict(os.environ, {**environment, "DEVICE_ALARM_WEBHOOK": "https://alerts.example.net/custom"}), patch("sys.stdout", new=io.StringIO()):
            self.assertEqual(configure.main(), 0)
        package = (config_directory / "packages" / "future_homes_tech_app.yaml").read_text(encoding="utf-8")
        self.assertIn('url: "https://alerts.example.net/custom"', package)
        self.assertNotIn("webhook/DeviceAlarm", package)
        other = load_module("configure_other_home", "configure.py", self.environment)
        self.assertEqual(
            other.PROTECT_DEVICE_OFFLINE_WEBHOOK,
            "https://console.example.net/proxy/protect/integration/v1/alarm-manager/webhook/device_offline",
        )
        self.assertEqual(other.DEFAULT_DEVICE_ALARM_WEBHOOK, "https://alerts.example.net/hook")

    def test_users_database_time_zone_follows_the_profile(self) -> None:
        self.assertEqual(SERVER.ACCESS.DEFAULT_TIMEZONE, "America/Phoenix")
        other = load_module("fht_access_other_home", "fht_access.py", self.environment)
        self.assertEqual(other.DEFAULT_TIMEZONE, "America/Denver")
        directory = Path(self.directory.name) / "users"
        store = SERVER.ACCESS.AccessStore(directory)
        with store.connection() as database:
            self.assertEqual(database.execute("SELECT timezone FROM properties WHERE id='home'").fetchone()[0], "America/Phoenix")
        moved = SERVER.ACCESS.AccessStore(directory, timezone="Europe/London")
        with moved.connection() as database:
            self.assertEqual(database.execute("SELECT timezone FROM properties WHERE id='home'").fetchone()[0], "Europe/London")
        self.assertEqual(moved.timezone, "Europe/London")
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertIn("timezone=SITE_PROFILE.timezone", source)
        self.assertIn('"timezone": SITE_PROFILE.timezone', source)

    def handler(self, path: str):
        handler = object.__new__(SERVER.FutureHomesTechRequestHandler)
        handler.path = path
        handler.headers = {}
        handler.wfile = io.BytesIO()
        handler.send_response = Mock()
        handler.send_header = Mock()
        handler.end_headers = Mock()
        handler._request_is_allowed = Mock(return_value=True)
        return handler

    def test_profile_is_shown_read_only_over_http(self) -> None:
        handler = self.handler("/api/site-profile")
        handler.do_GET()
        payload = json.loads(handler.wfile.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["values"], THIS_HOME)
        self.assertIn("Built-in defaults", payload["summary"])
        self.assertEqual(payload["problems"], [])
        handler = self.handler("/api/app-info")
        handler.app_info = Mock(fetch=Mock(return_value={"installed_version": "0.7.0"}))
        handler.beta_channel = Mock(status=Mock(return_value={"beta_mode": False}))
        handler.do_GET()
        payload = json.loads(handler.wfile.getvalue())
        self.assertEqual(payload["site_profile"]["values"]["rooms"]["device_alarm_room_names"], ["bridges", "device alarms", "fridges"])
        self.assertEqual(payload["installed_version"], "0.7.0")
        self.assertNotIn('"/api/site-profile"', SERVER.CONFIGURATION_MUTATION_PATHS)

    def test_packaging_ships_the_profile_and_the_launcher_uses_it(self) -> None:
        dockerfile = (APP / "Dockerfile").read_text(encoding="utf-8")
        for line in (
            "COPY fht_site.py /usr/local/bin/future-homes-tech-site\n",
            "COPY fht_site.py /usr/local/bin/fht_site.py\n",
            "COPY site_profile.json /usr/local/bin/site_profile.json\n",
            "    /usr/local/bin/future-homes-tech-site \\\n",
        ):
            with self.subTest(line=line):
                self.assertIn(line, dockerfile)
        launcher = (APP / "run.sh").read_text(encoding="utf-8")
        self.assertIn('DEVICE_ALARM_WEBHOOK="$(future-homes-tech-site protect-webhook device_alarm 2>/dev/null || true)"', launcher)
        self.assertNotIn("unifi.fht.internal", launcher)
        config = (APP / "config.yaml").read_text(encoding="utf-8")
        self.assertIn(f'device_alarm_webhook: "{PROTECT_BASE}/alarm-manager/webhook/DeviceAlarm"', config)
        for module in ("server.py", "configure.py", "fht_access.py", "fht_catalog.py", "generate_light_groups.py", "run.sh"):
            with self.subTest(module=module):
                source = (APP / module).read_text(encoding="utf-8")
                self.assertNotIn("unifi.fht.internal", source)
                self.assertNotIn("America/Phoenix", source)
                self.assertNotIn("kitchen_1g", source)
                self.assertNotIn("rgb indicator", source)

    def test_interface_shows_the_profile_on_the_unifi_page(self) -> None:
        html = (APP / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="site-profile-panel"', html)
        self.assertIn('requestJson("api/site-profile"', html)
        self.assertNotIn('saveJson("api/site-profile"', html)
        self.assertIn("loadSiteProfile()", html)
        self.assertIn("appInfo?.site_profile?.values?.weather_entity", html)
        self.assertIn("appInfo?.site_profile?.values?.rooms?.device_alarm_room_names", html)
        documentation = DOCS.read_text(encoding="utf-8")
        for value in (
            PROTECT_BASE, "America/Phoenix", "weather.forecast_home", "/data/site_profile.json",
            "future-homes-tech-site check",
        ):
            with self.subTest(value=value):
                self.assertIn(value, documentation)
        self.assertTrue(re.search(r"^## .*(?:left in code|stays? in code)", documentation, re.IGNORECASE | re.MULTILINE))


if __name__ == "__main__":
    unittest.main()
