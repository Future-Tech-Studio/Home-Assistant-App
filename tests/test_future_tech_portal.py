"""Tests for the Future Tech Portal reporting setup.

The package itself is exercised inside a real Home Assistant core by
scripts/check_portal_package.py; these tests cover the App side: the token
only ever reaches secrets.yaml, the package never contains it, and the
settings page never receives it.
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import yaml

from test_server import SERVER

PORTAL = SERVER.PORTAL
TOKEN = "fts_abcdEFGH1234_-xyz"


class _PackageLoader(yaml.SafeLoader):
    """Read Home Assistant YAML, keeping !secret as a marker."""


_PackageLoader.add_constructor("!secret", lambda loader, node: f"<secret {loader.construct_scalar(node)}>")


def load_package(text: str) -> dict:
    return yaml.load(text, Loader=_PackageLoader)  # noqa: S506 - SafeLoader subclass


class TokenTests(unittest.TestCase):
    def test_accepts_the_token_however_it_is_pasted(self) -> None:
        for pasted in (
            TOKEN,
            f"  {TOKEN}\n",
            f"Bearer {TOKEN}",
            f"bearer {TOKEN}",
            f'"Bearer {TOKEN}"',
            f'future_tech_token: "Bearer {TOKEN}"',
        ):
            self.assertEqual(PORTAL.normalize_token(pasted), f"Bearer {TOKEN}", pasted)

    def test_rejects_anything_else_without_repeating_it(self) -> None:
        for pasted in ("", "Bearer ", "abc", "fts_short", f"{TOKEN} extra", f"{TOKEN};x", "fts_" + "x" * 300):
            with self.assertRaises(PORTAL.PortalError) as caught:
                PORTAL.normalize_token(pasted)
            if pasted.strip():
                self.assertNotIn(pasted.strip(), str(caught.exception))

    def test_secret_line_is_added_replaced_and_removed_keeping_other_lines(self) -> None:
        original = "# my secrets\nhttp_password: hunter2\nlat: 1.5"
        added = PORTAL.with_token(original, f"Bearer {TOKEN}")
        self.assertEqual(added, f'{original}\nfuture_tech_token: "Bearer {TOKEN}"\n')
        self.assertTrue(PORTAL.token_configured(added))
        self.assertEqual(yaml.safe_load(added)["future_tech_token"], f"Bearer {TOKEN}")
        replaced = PORTAL.with_token(added, "Bearer fts_newtoken99")
        self.assertEqual(replaced.count("future_tech_token"), 1)
        self.assertIn('future_tech_token: "Bearer fts_newtoken99"', replaced)
        self.assertNotIn(TOKEN, replaced, "The old token is not left behind")
        removed = PORTAL.without_token(replaced)
        self.assertEqual(removed, f"{original}\n")
        self.assertFalse(PORTAL.token_configured(removed))

    def test_refuses_secrets_it_cannot_edit_safely(self) -> None:
        with self.assertRaises(PORTAL.PortalError):
            PORTAL.with_token('future_tech_token: "a"\nfuture_tech_token: "b"\n', "Bearer fts_x12345678")
        with self.assertRaises(PORTAL.PortalError):
            PORTAL.with_token("future_tech_token: >\n  Bearer fts_x12345678\n", "Bearer fts_x12345678")

    def test_token_configured_needs_a_value(self) -> None:
        self.assertFalse(PORTAL.token_configured(""))
        self.assertFalse(PORTAL.token_configured('future_tech_token: ""\n'))
        self.assertFalse(PORTAL.token_configured("# future_tech_token: \"Bearer fts_x\"\n"))
        self.assertTrue(PORTAL.token_configured('future_tech_token: "Bearer fts_x12345678"  # portal\n'))

    def test_private_write_keeps_the_mode_and_new_files_are_owner_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "secrets.yaml"
            PORTAL.write_private_text(path, "a: 1\n")
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            os.chmod(path, 0o640)
            PORTAL.write_private_text(path, "a: 2\n")
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o640)
            self.assertEqual(path.read_text(), "a: 2\n")
            self.assertEqual(sorted(p.name for p in Path(directory).iterdir()), ["secrets.yaml"], "No backup copies")


class PackageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = PORTAL.render_package(PORTAL.DEFAULT_INTEGRATIONS)
        self.package = load_package(self.text)

    def test_rest_command_matches_the_portal_contract(self) -> None:
        command = self.package["rest_command"]["future_tech_report"]
        self.assertEqual(command["url"], "https://futuretech.studio/api/beta/ingest")
        self.assertEqual(command["method"], "post")
        self.assertEqual(command["headers"], {"authorization": "<secret future_tech_token>"})
        self.assertEqual(command["content_type"], "application/json")
        self.assertEqual(command["timeout"], 20)
        self.assertIs(command["verify_ssl"], True)
        self.assertIn("{{ payload", command["payload"])

    def test_token_is_never_in_the_package(self) -> None:
        self.assertNotIn("fts_", self.text)
        self.assertNotIn("Bearer", self.text)
        self.assertEqual(self.text.count("!secret future_tech_token"), 1)

    def test_only_reporting_services_are_called(self) -> None:
        actions: set[str] = set()

        def walk(node) -> None:
            if isinstance(node, dict):
                if isinstance(node.get("action"), str):
                    actions.add(node["action"])
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)

        walk(self.package["script"])
        walk(self.package["automation"])
        self.assertEqual(
            actions,
            {
                "rest_command.future_tech_report",
                "persistent_notification.create",
                "persistent_notification.dismiss",
                # The inventory automation runs the inventory script.
                "script.future_tech_send_inventory",
            },
        )

    def test_automations_and_schedule(self) -> None:
        automations = {item["alias"]: item for item in self.package["automation"]}
        self.assertEqual(
            set(automations),
            {"Future Tech - inventory", "Future Tech - offline/online", "Future Tech - low battery",
             "Future Tech - activity", "Future Tech - send events"},
        )
        activity = automations["Future Tech - activity"]
        self.assertEqual(activity["triggers"], [{"trigger": "event", "event_type": "automation_triggered"}])
        self.assertEqual(activity["mode"], "queued")
        self.assertIn("future_tech_portal_", activity["conditions"][0]["value_template"], "The portal's own runs are not reported")
        self.assertIn("automation.triggered", json.dumps(activity))
        inventory_script = json.dumps(self.package["script"]["future_tech_send_inventory"])
        self.assertNotIn("'kind': 'automations'", inventory_script, "Only automation runs are sent, not a list of automations")
        steps = self.package["script"]["future_tech_send_inventory"]["sequence"]
        self.assertTrue(steps[0]["variables"]["monitored"].startswith("{%- if apps_only | default(false) -%}"),
                        "Send app versions now skips collecting the devices")
        guarded = steps[1]
        self.assertEqual(guarded["if"][0]["value_template"], "{{ not (apps_only | default(false)) }}")
        self.assertEqual(guarded["then"][0]["event"], "future_tech_portal_devices",
                         "An apps-only run leaves the reported device list alone")
        inventory = automations["Future Tech - inventory"]["triggers"]
        self.assertIn({"trigger": "homeassistant", "event": "start", "id": "start"}, inventory)
        self.assertIn({"trigger": "time_pattern", "minutes": 7, "id": "hourly"}, inventory)
        send = automations["Future Tech - send events"]
        self.assertEqual(send["triggers"], [
            {"trigger": "time_pattern", "minutes": "/5", "id": "timer"},
            {"trigger": "numeric_state", "entity_id": PORTAL.QUEUE_SENSOR, "above": 499, "id": "full"},
        ], "Every five minutes, and at once when 500 are waiting")
        send_text = json.dumps(send)
        self.assertIn("'kind': 'events'", send_text)
        self.assertIn("'appVersion': app_version", send_text)
        self.assertIn("heartbeat", send_text, "A heartbeat only when nothing is waiting")
        self.assertIn("timedelta(days=7)", send_text, "Events older than seven days are dropped")
        self.assertIn("[401, 403, 429]", send_text, "401/403/429 keep the events; other 4xx drop them")
        for name in ("Future Tech - activity", "Future Tech - offline/online", "Future Tech - low battery"):
            producer = json.dumps(automations[name])
            self.assertIn("future_tech_portal_queue", producer, f"{name} queues its events")
            self.assertNotIn("rest_command", producer, f"{name} sends nothing itself")
        queue = next(block for block in self.package["template"] if block["triggers"][0]["event_type"] == "future_tech_portal_queue")
        self.assertEqual(queue["sensor"][0]["attributes"], {PORTAL.QUEUE_ATTRIBUTE: "{{ queued }}"})
        self.assertEqual(PORTAL.QUEUE_ATTRIBUTE, "attribution", "The recorder never stores attribution")
        self.assertIn("[-2000:]", queue["variables"]["queued"])
        self.assertIn("240000", queue["variables"]["queued"])
        offline = json.dumps(automations["Future Tech - offline/online"])
        self.assertIn('"timeout": 120', offline, "Two minute debounce")
        self.assertIn("context.id", offline)
        battery = json.dumps(automations["Future Tech - low battery"])
        self.assertIn("< 20", battery)
        self.assertIn("battery_reported", battery)

    def test_integrations_are_baked_in_and_validated(self) -> None:
        text = PORTAL.render_package(["zha", "hue"])
        self.assertIn('{%- set integrations = ["zha", "hue"] -%}', text)
        self.assertIn("# Reported: devices of zha, hue,", text)
        with self.assertRaises(ValueError):
            PORTAL.render_package(["zha", "bad name"])
        self.assertEqual(PORTAL.normalize_integrations(None), list(PORTAL.DEFAULT_INTEGRATIONS))
        self.assertEqual(PORTAL.normalize_integrations([" ZHA", "zha", "", "esphome"]), ["zha", "esphome"])

    def test_integrations_with_devices_counts_enabled_registry_devices(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = Path(directory) / ".storage"
            storage.mkdir()
            (storage / "core.entity_registry").write_text(json.dumps({"data": {"entities": [
                {"entity_id": "light.a", "platform": "zha", "device_id": "d1"},
                {"entity_id": "sensor.a", "platform": "zha", "device_id": "d1"},
                {"entity_id": "light.b", "platform": "zha", "device_id": "d2"},
                {"entity_id": "light.c", "platform": "hue", "device_id": "d3", "disabled_by": "user"},
                {"entity_id": "light.group", "platform": "group", "device_id": "d4"},
                {"entity_id": "sensor.x", "platform": "esphome", "device_id": None},
            ]}}))
            self.assertEqual(PORTAL.integrations_with_devices(Path(directory)), {"zha": 2})
            self.assertEqual(PORTAL.integrations_with_devices(Path(directory) / "missing"), {})


class LastSeenTests(unittest.TestCase):
    def test_last_seen_is_when_the_last_real_state_ended(self) -> None:
        rows = [
            {"entity_id": "switch.plug", "state": "unavailable", "last_changed": "2026-09-24T00:00:00+00:00"},
            {"state": "on", "last_changed": "2026-09-25T08:00:00+00:00"},
            {"state": "off", "last_changed": "2026-09-26T09:00:00+00:00"},
            {"state": "unavailable", "last_changed": "2026-09-27T10:30:00+00:00"},
            {"state": "unknown", "last_changed": "2026-10-03T16:11:00+00:00"},
            {"state": "unavailable", "last_changed": "2026-10-03T16:12:00+00:00"},
        ]
        self.assertEqual(PORTAL.last_seen_from_history(rows), "2026-09-27T10:30:00+00:00", "A restart's 4:11 PM is not when it was last seen")
        self.assertIsNone(PORTAL.last_seen_from_history(rows[:1]), "Offline for the whole history window: unknown")
        self.assertIsNone(PORTAL.last_seen_from_history([]))

    def test_backfill_reads_history_for_offline_devices_without_a_time(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory)
            (config / "packages").mkdir()
            (config / "packages" / PORTAL.PACKAGE_FILENAME).write_text("# package\n")
            publisher = Mock()
            manager = SERVER.FutureTechPortalManager(SERVER.FutureTechPortalSettings(config / "s.json"), config, publisher)
            inventory = Mock()
            inventory.fetch_state.return_value = {"state": "3", "attributes": {
                "monitored": ["switch.plug", "binary_sensor.presence", "light.kitchen"],
                "last_seen": {"binary_sensor.presence": "2026-10-01T00:00:00+00:00"},
            }}
            inventory.fetch.return_value = {"entities": [
                {"entity_id": "switch.plug", "state": "unavailable"},
                {"entity_id": "binary_sensor.presence", "state": "unavailable"},
                {"entity_id": "light.kitchen", "state": "on"},
            ]}
            history = [[
                {"entity_id": "switch.plug", "state": "on", "last_changed": "2026-09-25T08:00:00+00:00"},
                {"state": "unavailable", "last_changed": "2026-09-27T10:30:00+00:00"},
            ]]
            with patch.object(manager, "_history", return_value=history) as read:
                self.assertEqual(manager.backfill_last_seen(inventory), 1)
            self.assertEqual(read.call_args.args[0], ["switch.plug"], "Only offline devices without a saved time are looked up")
            publisher.fire_event.assert_called_once_with(
                "future_tech_portal_last_seen", {"last_seen": {"switch.plug": "2026-09-27T10:30:00+00:00"}}
            )


class MatterNetworkTests(unittest.TestCase):
    def test_network_from_feature_flags_then_diagnostics_clusters(self) -> None:
        self.assertEqual(PORTAL.matter_network({"0/49/65532": 2}), "thread")
        self.assertEqual(PORTAL.matter_network({"0/49/65532": 1}), "wifi")
        self.assertEqual(PORTAL.matter_network({"0/49/65532": 4}), "ethernet")
        self.assertEqual(PORTAL.matter_network({"0/53/0": 15}), "thread")
        self.assertEqual(PORTAL.matter_network({"0/54/1": 3}), "wifi")
        self.assertIsNone(PORTAL.matter_network({"1/6/0": True}))

    def test_devices_are_matched_to_nodes_including_bridged_ones(self) -> None:
        registry = {"data": {"devices": [
            {"id": "thread-plug", "identifiers": [["matter", "deviceid_00000000AAAA0001-0000000000000002-MatterNodeDevice"],
                                                  ["matter", "serial_123"]]},
            {"id": "wifi-switch", "identifiers": [["matter", "deviceid_00000000AAAA0001-000000000000000A-MatterNodeDevice"]]},
            {"id": "bridged-bulb", "identifiers": [["matter", "deviceid_00000000AAAA0001-000000000000000A-5"]]},
            {"id": "zigbee", "identifiers": [["zha", "00:11"]]},
            {"id": "unknown-node", "identifiers": [["matter", "deviceid_00000000AAAA0001-00000000000000FF-MatterNodeDevice"]]},
        ]}}
        diagnostics = {"data": {"server": {"nodes": [
            {"node_id": 2, "attributes": {"0/49/65532": 2}},
            {"node_id": 10, "attributes": {"0/49/65532": 1}},
        ]}}}
        self.assertEqual(
            PORTAL.matter_networks(registry, diagnostics),
            {"thread-plug": "thread", "wifi-switch": "wifi", "bridged-bulb": "wifi"},
        )

    def test_refresh_reads_matter_diagnostics_and_tells_the_package(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory)
            (config / "packages").mkdir()
            (config / "packages" / PORTAL.PACKAGE_FILENAME).write_text("# package\n")
            (config / ".storage").mkdir()
            (config / ".storage" / "core.config_entries").write_text(json.dumps({"data": {"entries": [
                {"entry_id": "m1", "domain": "matter"}, {"entry_id": "z1", "domain": "zha"}]}}))
            (config / ".storage" / "core.device_registry").write_text(json.dumps({"data": {"devices": [
                {"id": "dev1", "identifiers": [["matter", "deviceid_00000000AAAA0001-0000000000000002-MatterNodeDevice"]]}]}}))
            publisher = Mock(_token="t", _services_url="http://supervisor/core/api/services")
            manager = SERVER.FutureTechPortalManager(SERVER.FutureTechPortalSettings(config / "s.json"), config, publisher)
            response = io.BytesIO(json.dumps({"data": {"server": {"nodes": [{"node_id": 2, "attributes": {"0/49/65532": 2}}]}}}).encode())
            with patch.object(SERVER, "urlopen", return_value=response) as opened:
                self.assertEqual(manager.refresh_matter_networks(), 1)
            self.assertEqual(opened.call_args.args[0].full_url, "http://supervisor/core/api/diagnostics/config_entry/m1")
            publisher.fire_event.assert_called_once_with("future_tech_portal_networks", {"networks": {"dev1": "thread"}})


class SystemVersionTests(unittest.TestCase):
    def test_versions_come_from_the_app_and_supervisor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory)
            (config / "packages").mkdir()
            (config / "packages" / PORTAL.PACKAGE_FILENAME).write_text("# package\n")
            publisher = Mock(_token="t", _services_url="http://supervisor/core/api/services")
            manager = SERVER.FutureTechPortalManager(SERVER.FutureTechPortalSettings(config / "s.json"), config, publisher)
            info = io.BytesIO(json.dumps({"result": "ok", "data": {"supervisor": "2026.09.1", "homeassistant": "2026.9.3", "hassos": "16.2"}}).encode())
            supervisor = io.BytesIO(json.dumps({"data": {"addons": [
                {"name": "Mosquitto broker", "slug": "core_mosquitto", "version": "6.5.1", "version_latest": "6.5.2", "update_available": True, "state": "started"},
                {"name": "Future Homes Tech App", "slug": "fht", "version": "0.7.53", "version_latest": "0.7.53", "update_available": False, "state": "started"},
            ]}}).encode())
            with patch.dict(os.environ, {"FHT_RUNNING_VERSION": "0.7.51"}), patch.object(SERVER, "urlopen", side_effect=[info, supervisor]) as opened:
                system = manager.refresh_system_versions()
            self.assertEqual([call.args[0].full_url for call in opened.call_args_list], ["http://supervisor/info", "http://supervisor/supervisor/info"])
            expected = {"appVersion": "0.7.51", "coreVersion": "2026.9.3", "supervisorVersion": "2026.09.1", "osVersion": "16.2", "apps": [
                {"appId": "fht", "name": "Future Homes Tech App", "source": "addon", "version": "0.7.53", "latestVersion": "0.7.53", "updateAvailable": False, "state": "started"},
                {"appId": "core_mosquitto", "name": "Mosquitto broker", "source": "addon", "version": "6.5.1", "latestVersion": "6.5.2", "updateAvailable": True, "state": "started"},
            ]}
            self.assertEqual(system, expected)
            publisher.fire_event.assert_called_once_with("future_tech_portal_system", {"system": expected})

    def test_hacs_items_and_other_custom_integrations(self) -> None:
        # Rows as HACS stores them: no "name"; hacs.json's name in repository_manifest,
        # an integration's manifest name in manifest_name; "installed" only when true.
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory)
            (config / ".storage").mkdir()
            (config / ".storage" / "hacs.repositories").write_text(json.dumps({"data": {
                "1": {"full_name": "hacs/integration", "category": "integration", "installed": True, "version_installed": "2.0.5",
                      "last_version": "2.0.5", "domain": "hacs", "manifest_name": "HACS", "repository_manifest": {"name": "HACS"}},
                "2": {"full_name": "custom-components/alexa_media_player", "category": "integration", "installed": True,
                      "version_installed": "4.13.0", "last_version": "4.13.2", "domain": "alexa_media",
                      "manifest_name": "Alexa Media Player", "repository_manifest": {"name": "Alexa Media Player"}},
                "3": {"full_name": "someone/not-installed", "category": "integration"},
                "4": {"full_name": "thomasloven/lovelace-card-mod", "category": "plugin", "installed": True, "version_installed": "v3.4.4",
                      "repository_manifest": {"name": "card-mod", "filename": "card-mod.js"}},
                "5": {"full_name": "Nerwyn/android-tv-card", "category": "plugin", "installed": True, "installed_commit": "1a2b3c4d5e",
                      "last_commit": "1a2b3c4d5e", "repository_manifest": {}},
                "6": {"full_name": "someone/frigate-hass-integration", "category": "integration", "installed": True,
                      "version_installed": "5.4.0", "domain": "frigate", "repository_manifest": {}},
            }}))
            for domain, manifest in (("hacs", {"domain": "hacs", "name": "HACS", "version": "2.0.5"}),
                                     ("alexa_media", {"domain": "alexa_media", "version": "4.13.0"}),
                                     ("frigate", {"domain": "frigate", "name": "Frigate", "version": "5.4.0"}),
                                     ("local_thing", {"domain": "local_thing", "name": "Local Thing", "version": "1.0.0"})):
                (config / "custom_components" / domain).mkdir(parents=True)
                (config / "custom_components" / domain / "manifest.json").write_text(json.dumps(manifest))
            self.assertEqual(PORTAL.hacs_items(config), [
                {"appId": "custom-components/alexa_media_player", "name": "Alexa Media Player", "source": "hacs", "version": "4.13.0",
                 "latestVersion": "4.13.2", "updateAvailable": True, "category": "integration"},
                {"appId": "Nerwyn/android-tv-card", "name": "Android Tv Card", "source": "hacs", "version": "1a2b3c4",
                 "latestVersion": "1a2b3c4", "updateAvailable": False, "category": "plugin"},
                {"appId": "thomasloven/lovelace-card-mod", "name": "card-mod", "source": "hacs", "version": "v3.4.4", "category": "plugin"},
                {"appId": "someone/frigate-hass-integration", "name": "Frigate", "source": "hacs", "version": "5.4.0", "category": "integration"},
                {"appId": "hacs/integration", "name": "HACS", "source": "hacs", "version": "2.0.5", "latestVersion": "2.0.5",
                 "updateAvailable": False, "category": "integration"},
                {"appId": "custom_components/local_thing", "name": "Local Thing", "source": "custom", "version": "1.0.0", "category": "integration"},
            ])
            self.assertEqual(PORTAL.hacs_items(config / "missing"), [])

    def test_hacs_items_from_the_newer_hacs_data_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory)
            (config / ".storage").mkdir()
            (config / ".storage" / "hacs.data").write_text(json.dumps({"key": "hacs.data", "data": {"repositories": {
                "integration": [{"id": "1", "full_name": "hacs/integration", "installed": True, "version_installed": "2.0.5",
                                 "domain": "hacs", "repository_manifest": {"name": "HACS"}},
                                {"id": "2", "full_name": "someone/not-installed"}],
                "theme": [{"id": "3", "full_name": "catppuccin/home-assistant", "installed": True, "version_installed": "v2.1.2",
                           "repository_manifest": {"name": "Catppuccin Theme"}}],
            }}}))
            self.assertEqual(PORTAL.hacs_items(config), [
                {"appId": "catppuccin/home-assistant", "name": "Catppuccin Theme", "source": "hacs", "version": "v2.1.2", "category": "theme"},
                {"appId": "hacs/integration", "name": "HACS", "source": "hacs", "version": "2.0.5", "category": "integration"},
            ])

    def test_supervisor_unreachable_still_sends_the_app_version(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory)
            (config / "packages").mkdir()
            (config / "packages" / PORTAL.PACKAGE_FILENAME).write_text("# package\n")
            publisher = Mock(_token="t", _services_url="http://supervisor/core/api/services")
            manager = SERVER.FutureTechPortalManager(SERVER.FutureTechPortalSettings(config / "s.json"), config, publisher)
            with patch.dict(os.environ, {"FHT_RUNNING_VERSION": "0.7.51"}), patch.object(SERVER, "urlopen", side_effect=SERVER.URLError("down")):
                self.assertEqual(manager.refresh_system_versions(), {"appVersion": "0.7.51"})


class StatusTests(unittest.TestCase):
    NOW = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)

    def status(self, state: str, minutes_ago: int = 3, **attributes) -> dict:
        when = (self.NOW - timedelta(minutes=minutes_ago)).isoformat()
        return {"state": state, "attributes": {"ok": state.startswith("2"), "last_success": when, "kind": "events", **attributes}}

    def describe(self, status, devices=None, **kwargs):
        options = {"token_saved": True, "enabled": True, "now": self.NOW, **kwargs}
        return PORTAL.describe_status(status, devices, **options)

    def test_connection_states(self) -> None:
        self.assertEqual(self.describe(None, token_saved=False)["connection"], "not_set_up")
        self.assertEqual(self.describe(None, enabled=False)["connection"], "paused")
        self.assertEqual(self.describe(None)["connection"], "waiting")
        self.assertEqual(self.describe(self.status("200"))["connection"], "connected")
        self.assertEqual(self.describe(self.status("200", minutes_ago=16))["connection"], "disconnected")
        self.assertEqual(self.describe(self.status("503"))["connection"], "disconnected")
        self.assertEqual(self.describe(self.status("401", paused=True))["connection"], "rejected")
        described = self.describe(self.status("200"), {"state": "42", "attributes": {"monitored": ["a", "b"]}})
        self.assertEqual((described["device_count"], described["http_status"], described["monitored_count"]), (42, 200, 2))
        self.assertEqual(self.describe(self.status("no response"))["http_status"], None)
        self.assertEqual(self.describe(self.status("200"), queue_state={"state": "37"})["queued_events"], 37)
        self.assertIsNone(self.describe(self.status("200"), queue_state={"state": "unknown"})["queued_events"])
        self.assertIsNone(self.describe(self.status("200"))["queued_events"])


class ManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.config = root / "homeassistant"
        (self.config / "packages").mkdir(parents=True)
        self.secrets = self.config / "secrets.yaml"
        self.secrets.write_text("other: keep\n")
        os.chmod(self.secrets, 0o600)
        self.data = root / "data"
        self.data.mkdir()
        self.publisher = Mock()
        self.publisher.confirm_repair.return_value = False
        self.history = SERVER.HISTORY.SettingsHistory([self.data])
        history_patch = patch.object(SERVER, "SETTINGS_HISTORY", self.history)
        history_patch.start()
        self.addCleanup(history_patch.stop)
        self.manager = SERVER.FutureTechPortalManager(
            SERVER.FutureTechPortalSettings(self.data / "future_tech_portal_settings.json"),
            self.config,
            self.publisher,
        )
        self.package = self.config / "packages" / PORTAL.PACKAGE_FILENAME

    def everything_outside_secrets(self) -> str:
        return "".join(
            path.read_text(errors="ignore")
            for path in Path(self.temporary.name).rglob("*")
            if path.is_file() and path != self.secrets
        )

    def test_save_token_writes_only_secrets_and_installs_the_package(self) -> None:
        self.manager.save_token(f"Bearer {TOKEN}")
        self.assertEqual(self.secrets.read_text(), f'other: keep\nfuture_tech_token: "Bearer {TOKEN}"\n')
        self.assertEqual(stat.S_IMODE(self.secrets.stat().st_mode), 0o600)
        self.assertTrue(self.package.exists())
        self.publisher.reload_domains.assert_called_once_with(("rest_command", "template", "script", "automation"))
        self.assertNotIn(TOKEN, self.everything_outside_secrets(), "Token only in secrets.yaml")

    def test_replacing_the_token_reloads_rest_command(self) -> None:
        self.manager.save_token(TOKEN)
        self.publisher.reset_mock()
        self.manager.save_token("fts_replacement42")
        self.assertIn("fts_replacement42", self.secrets.read_text())
        self.assertNotIn(TOKEN, self.secrets.read_text())
        self.publisher.reload_domains.assert_called_once_with(("rest_command",))

    def test_remove_token_removes_the_package_before_the_secret(self) -> None:
        self.manager.save_token(TOKEN)
        order: list[str] = []
        self.publisher.reload_domains.side_effect = lambda domains: order.append(
            f"reload package={self.package.exists()} token={'fts_' in self.secrets.read_text()}"
        )
        self.manager.remove_token()
        self.assertEqual(order, ["reload package=False token=True"])
        self.assertEqual(self.secrets.read_text(), "other: keep\n")
        self.assertFalse(self.package.exists())

    def test_pausing_removes_the_package_and_keeps_the_token(self) -> None:
        self.manager.save_token(TOKEN)
        self.manager.settings.save(False, ["zha"])
        self.assertTrue(self.manager.apply())
        self.assertFalse(self.package.exists())
        self.assertIn(TOKEN, self.secrets.read_text())
        self.manager.settings.save(True, ["zha"])
        self.manager.apply()
        self.assertIn('["zha"]', self.package.read_text())

    def test_removing_the_package_reloads_automations_before_rest_command(self) -> None:
        self.manager.save_token(TOKEN)
        self.publisher.reset_mock()
        self.manager.settings.save(False, ["zha"])
        self.manager.apply()
        self.publisher.reload_domains.assert_called_once_with(("automation", "script", "template", "rest_command"))
        self.publisher.confirm_repair.assert_not_called()

    def test_install_clears_stale_unknown_action_repairs(self) -> None:
        self.publisher.has_service.return_value = True
        self.publisher.confirm_repair.return_value = False
        self.manager.save_token(TOKEN)
        self.publisher.has_service.assert_called_with("rest_command", "future_tech_report")
        issues = [call.args for call in self.publisher.confirm_repair.call_args_list]
        self.assertIn(
            ("automation", "automation.future_tech_activity_service_not_found_rest_command.future_tech_report"),
            issues,
        )
        self.assertEqual(len(issues), len(PORTAL.REPORT_AUTOMATIONS))
        self.publisher.dismiss_notification.assert_called_once_with("future_tech_portal_restart")
        self.publisher.show_notification.assert_not_called()

    def test_install_without_rest_command_asks_for_a_restart(self) -> None:
        self.publisher.has_service.return_value = False
        self.manager.save_token(TOKEN)
        self.publisher.show_notification.assert_called_once()
        self.assertIn("Restart Home Assistant", self.publisher.show_notification.call_args.args[2])
        self.publisher.confirm_repair.assert_not_called()

    def test_report_command_check_never_fails_the_install(self) -> None:
        self.publisher.has_service.side_effect = SERVER.HomeAssistantAPIError("HTTP 502")
        self.manager.save_token(TOKEN)
        self.assertTrue(self.package.exists())

    def test_no_package_without_a_token(self) -> None:
        self.assertFalse(self.manager.apply())
        self.assertFalse(self.package.exists())
        self.publisher.reload_domains.assert_not_called()
        with self.assertRaises(ValueError):
            self.manager.send_inventory()

    def test_bad_token_changes_nothing(self) -> None:
        with self.assertRaises(ValueError):
            self.manager.save_token("not a token")
        self.assertEqual(self.secrets.read_text(), "other: keep\n")
        self.assertFalse(self.package.exists())

    def test_send_inventory_starts_the_script(self) -> None:
        self.manager.save_token(TOKEN)
        self.manager.send_inventory()
        self.publisher._call_service.assert_called_once_with(
            "script", "turn_on", {"entity_id": "script.future_tech_send_inventory"}
        )

    def test_send_apps_sends_only_the_apps_report(self) -> None:
        with self.assertRaises(ValueError):
            self.manager.send_apps()
        self.manager.save_token(TOKEN)
        apps = [{"appId": "core_mosquitto", "name": "Mosquitto broker", "source": "addon", "version": "6.5.1"}]
        with patch.object(self.manager, "refresh_system_versions", return_value={"appVersion": "0.7.58", "apps": apps}) as refresh:
            self.assertEqual(self.manager.send_apps(), 1)
        refresh.assert_called_once_with()
        self.publisher._call_service.assert_called_once_with(
            "script", "turn_on", {"entity_id": "script.future_tech_send_inventory", "variables": {"apps_only": True}}
        )
        self.publisher._call_service.reset_mock()
        with patch.object(self.manager, "refresh_system_versions", return_value={"appVersion": "0.7.58"}):
            with self.assertRaisesRegex(ValueError, "No installed Apps"):
                self.manager.send_apps()
        self.publisher._call_service.assert_not_called()

    def test_payload_never_contains_the_token(self) -> None:
        self.manager.save_token(TOKEN)
        inventory = Mock()
        inventory.fetch_state.side_effect = lambda entity_id: {
            PORTAL.STATUS_SENSOR: {"state": "200", "attributes": {"ok": True, "last_success": datetime.now(timezone.utc).isoformat()}},
            PORTAL.DEVICES_SENSOR: {"state": "12", "attributes": {"monitored": []}},
            PORTAL.QUEUE_SENSOR: {"state": "3", "attributes": {}},
        }[entity_id]
        payload = self.manager.payload(inventory)
        self.assertEqual(payload["status"]["queued_events"], 3)
        self.assertNotIn(TOKEN, json.dumps(payload))
        self.assertTrue(payload["token_saved"])
        self.assertEqual(payload["status"]["connection"], "connected")
        self.assertEqual(payload["status"]["device_count"], 12)
        self.assertEqual([choice["domain"] for choice in payload["integration_choices"]][:7], list(PORTAL.DEFAULT_INTEGRATIONS))
        inventory.fetch_state.side_effect = SERVER.HomeAssistantAPIError("HTTP 404")
        self.assertEqual(self.manager.payload(inventory)["status"]["connection"], "waiting")


class OptionTests(unittest.TestCase):
    """The token and URL can come from the App's Configuration tab."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.config = root / "homeassistant"
        (self.config / "packages").mkdir(parents=True)
        self.secrets = self.config / "secrets.yaml"
        self.secrets.write_text("other: keep\n")
        history_patch = patch.object(SERVER, "SETTINGS_HISTORY", SERVER.HISTORY.SettingsHistory([root]))
        history_patch.start()
        self.addCleanup(history_patch.stop)
        self.settings = SERVER.FutureTechPortalSettings(root / "future_tech_portal_settings.json")

    def manager(self, token: str = "", url: str = "") -> SERVER.FutureTechPortalManager:
        return SERVER.FutureTechPortalManager(self.settings, self.config, Mock(), option_token=token, option_url=url)

    def test_url_rules(self) -> None:
        self.assertEqual(PORTAL.normalize_url(""), PORTAL.INGEST_URL)
        self.assertEqual(PORTAL.normalize_url(" https://portal.example.com/api/v2/ingest "), "https://portal.example.com/api/v2/ingest")
        self.assertEqual(PORTAL.normalize_url("https://10.0.0.5:8443/ingest"), "https://10.0.0.5:8443/ingest")
        for bad in ("http://futuretech.studio/api/beta/ingest", "https://x.com/{{ payload }}", 'https://x.com/"a', "https://x.com/a b", "ftp://x"):
            with self.assertRaises(PORTAL.PortalError):
                PORTAL.normalize_url(bad)
        text = PORTAL.render_package(["zha"], "https://portal.example.com/api/v2/ingest")
        self.assertEqual(load_package(text)["rest_command"]["future_tech_report"]["url"], "https://portal.example.com/api/v2/ingest")

    def test_option_token_is_copied_into_secrets_and_the_package_uses_the_option_url(self) -> None:
        manager = self.manager(f"Bearer {TOKEN}", "https://portal.example.com/ingest")
        self.assertTrue(manager.apply_option_token())
        self.assertFalse(manager.apply_option_token(), "Unchanged on the next start")
        self.assertEqual(self.secrets.read_text(), f'other: keep\nfuture_tech_token: "Bearer {TOKEN}"\n')
        self.assertTrue(manager.apply(reload=False))
        package = (self.config / "packages" / PORTAL.PACKAGE_FILENAME).read_text()
        self.assertIn('url: "https://portal.example.com/ingest"', package)
        self.assertNotIn(TOKEN, package)
        inventory = Mock()
        inventory.fetch_state.side_effect = SERVER.HomeAssistantAPIError("HTTP 404")
        payload = manager.payload(inventory)
        self.assertEqual((payload["token_source"], payload["endpoint"]), ("options", "https://portal.example.com/ingest"))
        self.assertNotIn(TOKEN, json.dumps(payload))
        with self.assertRaises(ValueError):
            manager.save_token("fts_somethingelse1")
        with self.assertRaises(ValueError):
            manager.remove_token()
        self.assertIn(TOKEN, self.secrets.read_text())

    def test_bad_option_values_never_echo_the_token(self) -> None:
        manager = self.manager("fts_bad token!", "http://insecure.example.com")
        self.assertEqual(manager.ingest_url, PORTAL.INGEST_URL)
        self.assertIn("https://", manager.url_problem)
        with self.assertRaises(SERVER.HomeAssistantAPIError) as caught:
            manager.apply_option_token()
        self.assertNotIn("fts_bad", str(caught.exception))
        self.assertEqual(self.secrets.read_text(), "other: keep\n")

    def test_blank_option_leaves_a_page_token_alone(self) -> None:
        manager = self.manager()
        manager.save_token(TOKEN)
        self.assertFalse(manager.apply_option_token())
        self.assertIn(TOKEN, self.secrets.read_text())
        inventory = Mock()
        inventory.fetch_state.side_effect = SERVER.HomeAssistantAPIError("HTTP 404")
        self.assertEqual(manager.payload(inventory)["token_source"], "page")

    def test_configuration_tab_lists_token_and_url_under_the_protect_key(self) -> None:
        app = Path(SERVER.__file__).parent
        config = yaml.safe_load((app / "config.yaml").read_text())
        option_names = list(config["options"])
        position = option_names.index("protect_api_key")
        self.assertEqual(option_names[position + 1:position + 3], ["future_tech_token", "future_tech_url"])
        self.assertEqual(config["options"]["future_tech_url"], PORTAL.INGEST_URL)
        # Optional, so a Beta build still installs over a Stable that lacks them.
        self.assertEqual((config["schema"]["future_tech_token"], config["schema"]["future_tech_url"]), ("password?", "str?"))
        manifest = json.loads((app / "RELEASE.json").read_text())
        self.assertIn("future_tech_token", manifest["requires"]["optional_options"])
        self.assertNotIn("future_tech_token", manifest["requires"]["options"])
        labels = yaml.safe_load((app / "translations" / "en.yaml").read_text())["configuration"]
        self.assertEqual(labels["future_tech_token"]["name"], "Future Tech Portal token")
        self.assertEqual(labels["future_tech_url"]["name"], "Future Tech Portal URL")
        run = (app / "run.sh").read_text()
        self.assertIn("export FUTURE_TECH_TOKEN", run)
        self.assertNotRegex(run, r"(echo|log\.[a-z]+)[^\n]*FUTURE_TECH_TOKEN", "run.sh never prints the token")


class RouteTests(ManagerTests):
    def handler(self, method: str, body: dict | None = None):
        handler = object.__new__(SERVER.FutureHomesTechRequestHandler)
        handler.path = "/api/future-tech-portal"
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
        handler.future_tech_portal = self.manager
        handler.inventory = Mock()
        handler.inventory.fetch_state.side_effect = SERVER.HomeAssistantAPIError("HTTP 404")
        getattr(handler, f"do_{method}")()
        return handler.send_response.call_args.args[0], json.loads(handler.wfile.getvalue())

    def test_routes(self) -> None:
        status, payload = self.handler("GET")
        self.assertEqual((status, payload["token_saved"], payload["status"]["connection"]), (200, False, "not_set_up"))
        status, payload = self.handler("POST", {"action": "save_token", "token": TOKEN})
        self.assertEqual((status, payload["token_saved"]), (200, True))
        self.assertNotIn(TOKEN, json.dumps(payload))
        self.publisher._call_service.assert_called_once_with(
            "script", "turn_on", {"entity_id": "script.future_tech_send_inventory"}
        )
        status, payload = self.handler("POST", {"action": "settings", "integrations": ["zha"], "enabled": True})
        self.assertEqual((status, payload["integrations"]), (200, ["zha"]))
        status, payload = self.handler("POST", {"action": "save_token", "token": "nope"})
        self.assertEqual(status, 400)
        self.assertNotIn("nope", payload["error"])
        status, payload = self.handler("POST", {"action": "remove_token"})
        self.assertEqual((status, payload["token_saved"]), (200, False))
        self.manager.save_token(TOKEN)
        self.publisher._call_service.reset_mock()
        with patch.object(self.manager, "refresh_system_versions", return_value={"apps": [{"appId": "a"}, {"appId": "b"}]}):
            status, payload = self.handler("POST", {"action": "send_apps"})
        self.assertEqual((status, payload["apps_sent"], payload["saved"]), (200, 2, False))
        self.publisher._call_service.assert_called_once_with(
            "script", "turn_on", {"entity_id": "script.future_tech_send_inventory", "variables": {"apps_only": True}}
        )
        status, _ = self.handler("POST", {"action": "explode"})
        self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main()


class PublisherRepairTests(unittest.TestCase):
    def setUp(self) -> None:
        self.publisher = SERVER.HomeAssistantHelperPublisher("token", "http://supervisor/core/api/services")
        self.requests: list[tuple[str, str, object]] = []

    def respond(self, *answers):
        answers = list(answers)

        def fake_urlopen(request, timeout=10):
            body = json.loads(request.data) if request.data else None
            self.requests.append((request.get_method(), request.full_url, body))
            answer = answers.pop(0)
            if isinstance(answer, Exception):
                raise answer
            return io.BytesIO(json.dumps(answer).encode())

        return patch.object(SERVER, "urlopen", side_effect=fake_urlopen)

    def test_has_service(self) -> None:
        services = [{"domain": "rest_command", "services": {"reload": {}, "future_tech_report": {}}}]
        with self.respond(services, services):
            self.assertTrue(self.publisher.has_service("rest_command", "future_tech_report"))
            self.assertFalse(self.publisher.has_service("rest_command", "other"))

    def test_confirm_repair_submits_the_fix_flow(self) -> None:
        with self.respond({"flow_id": "abc", "type": "form"}, {"type": "create_entry"}):
            self.assertTrue(self.publisher.confirm_repair("automation", "issue"))
        self.assertEqual(self.requests, [
            ("POST", "http://supervisor/core/api/repairs/issues/fix", {"handler": "automation", "issue_id": "issue"}),
            ("POST", "http://supervisor/core/api/repairs/issues/fix/abc", {}),
        ])

    def test_confirm_repair_without_an_open_repair(self) -> None:
        missing = SERVER.HTTPError("http://supervisor/core/api/repairs/issues/fix", 400, "Bad Request", {}, None)
        with self.respond(missing):
            self.assertFalse(self.publisher.confirm_repair("automation", "issue"))
