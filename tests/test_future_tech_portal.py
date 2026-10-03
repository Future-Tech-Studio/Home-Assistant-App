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
            {"Future Tech - inventory", "Future Tech - offline/online", "Future Tech - low battery", "Future Tech - heartbeat"},
        )
        inventory = automations["Future Tech - inventory"]["triggers"]
        self.assertIn({"trigger": "homeassistant", "event": "start", "id": "start"}, inventory)
        self.assertIn({"trigger": "time_pattern", "minutes": 7, "id": "hourly"}, inventory)
        self.assertEqual(automations["Future Tech - heartbeat"]["triggers"], [{"trigger": "time_pattern", "minutes": "/10"}])
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

    def test_payload_never_contains_the_token(self) -> None:
        self.manager.save_token(TOKEN)
        inventory = Mock()
        inventory.fetch_state.side_effect = lambda entity_id: {
            PORTAL.STATUS_SENSOR: {"state": "200", "attributes": {"ok": True, "last_success": datetime.now(timezone.utc).isoformat()}},
            PORTAL.DEVICES_SENSOR: {"state": "12", "attributes": {"monitored": []}},
        }[entity_id]
        payload = self.manager.payload(inventory)
        self.assertNotIn(TOKEN, json.dumps(payload))
        self.assertTrue(payload["token_saved"])
        self.assertEqual(payload["status"]["connection"], "connected")
        self.assertEqual(payload["status"]["device_count"], 12)
        self.assertEqual([choice["domain"] for choice in payload["integration_choices"]][:7], list(PORTAL.DEFAULT_INTEGRATIONS))
        inventory.fetch_state.side_effect = SERVER.HomeAssistantAPIError("HTTP 404")
        self.assertEqual(self.manager.payload(inventory)["status"]["connection"], "waiting")


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
        status, _ = self.handler("POST", {"action": "explode"})
        self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main()
