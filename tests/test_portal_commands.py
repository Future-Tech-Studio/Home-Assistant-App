"""Tests for requests from the Future Tech Portal (contract v1, app.update).

The package hands the portal's requests to the App in an event; the App
answers each one once, updates only Apps this home reported, through Home
Assistant's own update entities, and sends the results back through the
package's script. scripts/check_portal_package.py runs the package side in a
real Home Assistant core.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import yaml

from test_server import SERVER

PORTAL = SERVER.PORTAL
TOKEN = "fts_abcdEFGH1234_-xyz"


class _PackageLoader(yaml.SafeLoader):
    """Read Home Assistant YAML, keeping !secret as a marker."""


_PackageLoader.add_constructor("!secret", lambda loader, node: f"<secret {loader.construct_scalar(node)}>")

ADDON = {"appId": "core_mosquitto", "name": "Mosquitto broker", "source": "addon",
         "version": "6.5.1", "latestVersion": "6.5.2", "updateAvailable": True}
BUBBLE = {"appId": "Clooos/Bubble-Card", "name": "Bubble Card", "source": "hacs",
          "version": "v3.4.1", "latestVersion": "v3.4.2", "updateAvailable": True, "category": "plugin"}
OWN = {"appId": "a0d7b954_future_homes_tech_app", "name": "Future Homes Tech App", "source": "addon",
       "version": "0.8.62", "latestVersion": "0.8.63", "updateAvailable": True}
CURRENT = {"appId": "core_samba", "name": "Samba share", "source": "addon", "version": "12.3", "updateAvailable": False}

DEVICES = [
    {"id": "dev-mosquitto", "identifiers": [["hassio", "core_mosquitto"]]},
    {"id": "dev-samba", "identifiers": [["hassio", "core_samba"]]},
    {"id": "dev-own", "identifiers": [["hassio", "a0d7b954_future_homes_tech_app"]]},
    {"id": "dev-bubble", "identifiers": [["hacs", "680112919"]], "configuration_url": "https://github.com/Clooos/Bubble-Card"},
    {"id": "dev-mushroom", "identifiers": [["hacs", "444350375"]], "configuration_url": "https://github.com/piitaya/lovelace-mushroom/"},
]
ENTITIES = [
    {"entity_id": "update.mosquitto_broker_update", "platform": "hassio", "device_id": "dev-mosquitto",
     "unique_id": "core_mosquitto_version_latest"},
    {"entity_id": "sensor.mosquitto_broker_version", "platform": "hassio", "device_id": "dev-mosquitto"},
    {"entity_id": "update.samba_share_update", "platform": "hassio", "device_id": "dev-samba"},
    {"entity_id": "update.future_homes_tech_app_update", "platform": "hassio", "device_id": "dev-own"},
    {"entity_id": "update.bubble_card_update", "platform": "hacs", "device_id": "dev-bubble", "unique_id": "680112919"},
    {"entity_id": "update.mushroom_update", "platform": "hacs", "device_id": "dev-mushroom", "unique_id": "444350375"},
]
STATES = {
    "update.mosquitto_broker_update": {"entity_id": "update.mosquitto_broker_update", "state": "on",
                                       "attributes": {"installed_version": "6.5.1", "latest_version": "6.5.2"}},
    "update.samba_share_update": {"entity_id": "update.samba_share_update", "state": "off",
                                  "attributes": {"installed_version": "12.3", "latest_version": "12.3"}},
    "update.future_homes_tech_app_update": {"entity_id": "update.future_homes_tech_app_update", "state": "on",
                                            "attributes": {"installed_version": "0.8.62", "latest_version": "0.8.63"}},
    "update.bubble_card_update": {"entity_id": "update.bubble_card_update", "state": "on",
                                  "attributes": {"installed_version": "v3.4.1", "latest_version": "v3.4.2"}},
}


def command(app: dict, index: int = 1, **extra) -> dict:
    return {"id": f"cmd-{index:024x}", "type": "app.update", "appId": app["appId"], "source": app["source"],
            "targetVersion": app.get("latestVersion", ""), "issuedAt": "2026-10-11T00:00:00Z",
            "expiresAt": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(), **extra}


def restart_command(index: int = 1, **extra) -> dict:
    now = datetime.now(timezone.utc)
    return {"id": f"cmd-{index:024x}", "type": "ha.restart", "runAfter": (now - timedelta(minutes=1)).isoformat(),
            "issuedAt": now.isoformat(), "expiresAt": (now + timedelta(hours=24)).isoformat(), **extra}


class PackageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = PORTAL.render_package(PORTAL.DEFAULT_INTEGRATIONS)
        self.package = yaml.load(self.text, Loader=_PackageLoader)  # noqa: S506 - SafeLoader subclass

    def send_steps(self) -> list[list[dict]]:
        """Every step list holding a report send, with the steps that follow it."""
        found: list[list[dict]] = []

        def walk(node) -> None:
            if isinstance(node, list):
                for index, item in enumerate(node):
                    if isinstance(item, dict) and item.get("action") == "rest_command.future_tech_report":
                        found.append(node[index:])
                for item in node:
                    walk(item)
            elif isinstance(node, dict):
                for value in node.values():
                    walk(value)

        walk(self.package["script"])
        walk(self.package["automation"])
        return found

    def test_every_send_hands_the_portal_requests_to_the_app(self) -> None:
        sends = self.send_steps()
        # Inventory, apps, heartbeat, events, command results.
        self.assertEqual(len(sends), 5)
        for steps in sends:
            commands = steps[2]["variables"]["portal_commands"]
            self.assertIn("200 <= portal_status < 300", commands, "Only a delivered report's answer counts")
            self.assertIn("commands[:5]", commands, "At most five requests a response")
            self.assertIn("commands is not string and commands is not mapping", commands)
            fire = steps[3]
            self.assertEqual(fire["if"][0]["value_template"], "{{ portal_commands | count > 0 }}")
            self.assertEqual(fire["then"], [{"event": PORTAL.COMMANDS_EVENT, "event_data": {"commands": "{{ portal_commands }}"}}])
        self.assertEqual(PORTAL.COMMANDS_EVENT, "future_tech_portal_commands")

    def test_results_script_sends_a_commands_report_without_the_token(self) -> None:
        script = self.package["script"]["future_tech_send_command_results"]
        self.assertEqual(PORTAL.RESULTS_SCRIPT, "script.future_tech_send_command_results")
        self.assertEqual(script["mode"], "queued")
        self.assertIn("payload.results", script["sequence"][0]["variables"]["portal_results"])
        self.assertIn("[:20]", script["sequence"][0]["variables"]["portal_results"])
        send = script["sequence"][3]
        self.assertEqual(send["action"], "rest_command.future_tech_report")
        self.assertIn("'kind': 'commands', 'results': portal_results", send["data"]["payload"])
        self.assertIn("payload.appVersion", send["data"]["payload"])
        self.assertNotIn("fts_", self.text)
        self.assertNotIn("Bearer", self.text)
        self.assertEqual(self.text.count("!secret future_tech_token"), 1)

    def test_package_header_states_what_the_portal_may_ask(self) -> None:
        self.assertNotIn("accepts no commands", self.text)
        self.assertIn("update\n# an installed App or HACS item", self.text)
        self.assertIn("The portal never controls a device.", self.text)


class MatchingTests(unittest.TestCase):
    def test_addon_update_entity_is_the_supervisor_one_on_its_device(self) -> None:
        self.assertEqual(PORTAL.update_entity_candidates(ADDON, ENTITIES, DEVICES), ["update.mosquitto_broker_update"])
        # No device: the Supervisor update entity's unique ID still names the slug.
        entities = [{**ENTITIES[0], "device_id": None}]
        self.assertEqual(PORTAL.update_entity_candidates(ADDON, entities, []), ["update.mosquitto_broker_update"])
        # Disabled, or another integration's update entity on the device, never counts.
        self.assertEqual(PORTAL.update_entity_candidates(ADDON, [{**ENTITIES[0], "disabled_by": "user"}], DEVICES), [])
        self.assertEqual(PORTAL.update_entity_candidates(ADDON, [{**ENTITIES[0], "platform": "hacs"}], DEVICES), [])
        self.assertEqual(PORTAL.update_entity_candidates({**ADDON, "source": "custom"}, ENTITIES, DEVICES), [])

    def test_hacs_update_entity_by_repository_id_or_github_page(self) -> None:
        self.assertEqual(
            PORTAL.update_entity_candidates(BUBBLE, ENTITIES, DEVICES, {"clooos/bubble-card": "680112919"}),
            ["update.bubble_card_update"],
        )
        # No repository ID known: the HACS device's configuration URL is its GitHub page.
        mushroom = {"appId": "piitaya/lovelace-mushroom", "source": "hacs"}
        self.assertEqual(PORTAL.update_entity_candidates(mushroom, ENTITIES, DEVICES, {}), ["update.mushroom_update"])
        # A Supervisor device with the same URL is not a HACS item.
        devices = [{"id": "dev-bubble", "identifiers": [["hassio", "x"]], "configuration_url": "https://github.com/Clooos/Bubble-Card"}]
        self.assertEqual(PORTAL.update_entity_candidates(BUBBLE, ENTITIES, devices, {}), [])

    def test_hacs_repository_ids_from_either_storage_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory)
            (config / ".storage").mkdir()
            (config / ".storage" / "hacs.repositories").write_text(json.dumps({"data": {
                "680112919": {"full_name": "Clooos/Bubble-Card", "installed": True},
                "1": {"full_name": "hacs/integration", "id": "172733314"},
            }}))
            self.assertEqual(PORTAL.hacs_repository_ids(config), {"clooos/bubble-card": "680112919", "hacs/integration": "172733314"})
            (config / ".storage" / "hacs.repositories").unlink()
            (config / ".storage" / "hacs.data").write_text(json.dumps({"data": {"repositories": {
                "plugin": [{"full_name": "Clooos/Bubble-Card", "id": "680112919"}],
            }}}))
            self.assertEqual(PORTAL.hacs_repository_ids(config), {"clooos/bubble-card": "680112919"})

    def test_states_fallback(self) -> None:
        states = [
            {"entity_id": "update.mosquitto", "attributes": {"entity_picture": "/api/hassio/addons/core_mosquitto/icon"}},
            {"entity_id": "update.bubble", "attributes": {"release_url": "https://github.com/clooos/bubble-card/releases/v3.4.2"}},
            {"entity_id": "sensor.other", "attributes": {"entity_picture": "/api/hassio/addons/core_mosquitto/icon"}},
        ]
        self.assertEqual(PORTAL.update_entity_from_states(ADDON, states), "update.mosquitto")
        self.assertEqual(PORTAL.update_entity_from_states(BUBBLE, states), "update.bubble")
        self.assertEqual(PORTAL.update_entity_from_states({**BUBBLE, "appId": "Clooos/Bubble"}, states), "")

    def test_requests_keep_only_known_fields(self) -> None:
        raw = command(ADDON, url="https://evil", entity_id="update.x", script="script.x")
        normalized = PORTAL.normalize_command(raw)
        self.assertEqual(set(normalized), {"id", "type", "appId", "source", "targetVersion", "expiresAt"})
        self.assertIsNone(PORTAL.normalize_command({**raw, "id": "not-a-command"}))
        self.assertIsNone(PORTAL.normalize_command("cmd-1"))
        self.assertEqual(PORTAL.command_result("cmd-1", "failed", "x" * 400)["message"], "x" * 300)
        with self.assertRaises(ValueError):
            PORTAL.command_result("cmd-1", "queued")


class CommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.config = root / "homeassistant"
        (self.config / "packages").mkdir(parents=True)
        (self.config / ".storage").mkdir()
        (self.config / ".storage" / "hacs.repositories").write_text(json.dumps({"data": {
            "680112919": {"full_name": "Clooos/Bubble-Card", "installed": True},
        }}))
        (self.config / "secrets.yaml").write_text("other: keep\n")
        self.data = root / "data"
        self.data.mkdir()
        history_patch = patch.object(SERVER, "SETTINGS_HISTORY", SERVER.HISTORY.SettingsHistory([self.data]))
        history_patch.start()
        self.addCleanup(history_patch.stop)
        self.publisher = Mock()
        self.publisher.confirm_repair.return_value = False
        self.publisher._token = "supervisor-token"
        self.publisher._services_url = "http://supervisor/core/api/services"
        self.registry_lists = [ENTITIES, DEVICES]
        self.registries = Mock(side_effect=lambda commands: [
            {"issues": []} if item["type"] == "repairs/list_issues"
            else self.registry_lists[0] if item["type"] == "config/entity_registry/list"
            else self.registry_lists[1]
            for item in commands
        ])
        self.install = Mock(return_value=None)
        self.manager = SERVER.FutureTechPortalManager(
            SERVER.FutureTechPortalSettings(self.data / "future_tech_portal_settings.json"),
            self.config,
            self.publisher,
            run_websocket=self.registries,
            long_websocket_command=self.install,
        )
        self.manager.save_token(TOKEN)
        self.publisher.reset_mock()
        self.apps = [ADDON, BUBBLE, OWN, CURRENT]
        for name, value in (
            ("system_versions", lambda: {"appVersion": "0.8.63", "apps": [dict(app) for app in self.apps]}),
            ("_read_states", lambda entity_id="": STATES.get(entity_id) if entity_id else list(STATES.values())),
        ):
            patcher = patch.object(self.manager, name, side_effect=value)
            patcher.start()
            self.addCleanup(patcher.stop)
        environment = patch.dict(os.environ, {"FHT_RUNNING_VERSION": "0.8.63"})
        environment.start()
        self.addCleanup(environment.stop)

    def sent_results(self) -> list[dict]:
        """Results posted through the package's script, in order."""
        results = []
        for call in self.publisher._call_service.call_args_list:
            domain, service, data = call.args
            if domain != "script":
                continue
            if service == "turn_on" and data["entity_id"] == PORTAL.RESULTS_SCRIPT:
                payload = data["variables"]["payload"]
            elif service == PORTAL.RESULTS_SCRIPT.split(".", 1)[1]:
                payload = data["payload"]
            else:
                continue
            self.assertEqual(payload["appVersion"], "0.8.63")
            results.extend(payload["results"])
        return results

    def installed(self) -> list[str]:
        return [call.args[0]["target"]["entity_id"] for call in self.install.call_args_list]

    def test_installs_through_the_update_entity_and_resends_the_apps(self) -> None:
        results = self.manager.handle_commands([command(ADDON, 1), command(BUBBLE, 2)])
        self.assertEqual(self.installed(), ["update.mosquitto_broker_update", "update.bubble_card_update"])
        self.assertEqual(self.install.call_args_list[0].args, (
            {"type": "call_service", "domain": "update", "service": "install",
             "target": {"entity_id": "update.mosquitto_broker_update"}},
            SERVER.FutureTechPortalManager.INSTALL_TIMEOUT_SECONDS,
        ))
        self.assertEqual([(item["status"], item.get("version")) for item in results], [("done", "6.5.2"), ("done", "v3.4.2")])
        self.assertEqual(self.sent_results(), results)
        self.publisher._call_service.assert_any_call(
            "script", "turn_on", {"entity_id": PORTAL.INVENTORY_SCRIPT, "variables": {"apps_only": True}}
        )
        self.assertNotIn(TOKEN, json.dumps([call.args for call in self.publisher._call_service.call_args_list]))

    def test_each_request_is_handled_once(self) -> None:
        self.manager.handle_commands([command(ADDON, 1), command(ADDON, 1)])
        self.assertEqual(self.installed(), ["update.mosquitto_broker_update"])
        stored = json.loads((self.data / "future_tech_portal_commands.json").read_text())
        self.assertEqual([(item["id"], item["status"]) for item in stored["handled"]], [(command(ADDON, 1)["id"], "done")])
        self.assertNotIn("appId", json.dumps(stored), "Only the ID and its result are kept")
        # The portal repeats it: not installed again, the same result is sent again.
        self.publisher.reset_mock()
        self.manager.handle_commands([command(ADDON, 1)])
        self.assertEqual(self.installed(), ["update.mosquitto_broker_update"])
        self.assertEqual([item["status"] for item in self.sent_results()], ["done"])
        # ...at most every ten minutes.
        self.publisher.reset_mock()
        self.manager.handle_commands([command(ADDON, 1)])
        self.assertEqual(self.sent_results(), [])
        # A new App process still knows it.
        manager = SERVER.FutureTechPortalManager(
            self.manager.settings, self.config, self.publisher, run_websocket=self.registries, long_websocket_command=self.install,
        )
        with patch.object(manager, "system_versions", return_value={"apps": self.apps}):
            manager.handle_commands([command(ADDON, 1)])
        self.assertEqual(self.installed(), ["update.mosquitto_broker_update"])
        self.assertFalse((self.data / "history").exists() and any((self.data / "history").rglob("*commands*")),
                         "The request log has no settings history")

    def test_the_last_200_requests_are_remembered(self) -> None:
        log = self.manager.command_log
        for index in range(205):
            log.record(PORTAL.command_result(f"cmd-{index}", "rejected"))
        handled = log.read()
        self.assertEqual(len(handled), 200)
        self.assertNotIn("cmd-4", handled)
        self.assertIn("cmd-5", handled)
        self.assertIn("cmd-204", handled)

    def test_unknown_apps_and_requests_are_rejected(self) -> None:
        results = self.manager.handle_commands([
            command({"appId": "someone/else", "source": "hacs"}, 1),
            command({**ADDON, "source": "hacs"}, 2),
            command({"appId": "custom_components/local_thing", "source": "custom"}, 3),
            command(ADDON, 4, type="ha.reboot"),
            {"id": "bad", "type": "app.update"},
        ])
        self.assertEqual([item["status"] for item in results], ["rejected"] * 4)
        self.assertEqual(results[0]["message"], "That app is not installed in this home.")
        self.install.assert_not_called()
        self.assertEqual(self.sent_results(), results)

    def test_already_current_is_done_with_the_installed_version(self) -> None:
        results = self.manager.handle_commands([command(CURRENT, 1)])
        self.assertEqual(results, [{"id": command(CURRENT, 1)["id"], "status": "done", "message": "Already up to date.", "version": "12.3"}])
        self.install.assert_not_called()
        # No update entity found and nothing waiting: also done.
        self.registry_lists = [[], []]
        self.manager._read_states.side_effect = lambda entity_id="": None if entity_id else []
        results = self.manager.handle_commands([command(CURRENT, 2)])
        self.assertEqual((results[0]["status"], results[0]["version"]), ("done", "12.3"))
        # An update waiting but no entity to install it with: failed.
        results = self.manager.handle_commands([command(ADDON, 3)])
        self.assertEqual((results[0]["status"], results[0]["message"]), ("failed", "Home Assistant has no update entity for this app."))

    def test_install_error_is_failed_with_its_message(self) -> None:
        self.install.side_effect = SERVER.HomeAssistantAPIError("Version 6.5.2 is not compatible")
        results = self.manager.handle_commands([command(ADDON, 1)])
        self.assertEqual(results[0]["status"], "failed")
        self.assertEqual(results[0]["message"], "Update failed: Version 6.5.2 is not compatible")

    def test_turned_off_rejects_everything(self) -> None:
        current = self.manager.settings.read()
        self.manager.settings.save(current["enabled"], current["integrations"], False)
        results = self.manager.handle_commands([command(ADDON, 1), command(BUBBLE, 2)])
        self.assertEqual([(item["status"], item["message"]) for item in results], [("rejected", "Turned off in the app")] * 2)
        self.install.assert_not_called()
        self.registries.assert_not_called()
        restart = self.manager.handle_commands([restart_command(3)])
        self.assertEqual((restart[0]["status"], restart[0]["message"]), ("rejected", "Turned off in the app"))
        self.install.assert_not_called()

    def test_setting_defaults_on_and_survives_other_saves(self) -> None:
        settings = self.manager.settings.read()
        self.assertIs(settings["allow_app_updates"], True)
        self.manager.settings.save(True, ["zha"], False)
        self.manager.settings.save(False, ["zha"])
        self.assertIs(self.manager.settings.read()["allow_app_updates"], False)
        self.manager.save_token(TOKEN)
        self.assertIs(self.manager.settings.read()["allow_app_updates"], False)
        inventory = Mock()
        inventory.fetch_state.side_effect = SERVER.HomeAssistantAPIError("HTTP 404")
        self.assertIs(self.manager.payload(inventory)["allow_app_updates"], False)

    def test_own_app_answers_started_before_it_installs_last(self) -> None:
        order: list[str] = []
        self.publisher._call_service.side_effect = lambda domain, service, data: order.append(
            f"{service}:{','.join(item['status'] for item in (data.get('payload') or data.get('variables', {}).get('payload') or {}).get('results', []))}"
        )
        self.install.side_effect = lambda payload, timeout: order.append(f"install:{payload['target']['entity_id']}")
        self.manager.handle_commands([command(OWN, 1), command(ADDON, 2)])
        self.assertEqual(order[:4], [
            "install:update.mosquitto_broker_update",
            # Sent and waited for before this App stops for its own update.
            "future_tech_send_command_results:done,started",
            "install:update.future_homes_tech_app_update",
            "turn_on:done",
        ])
        stored = self.manager.command_log.read()
        self.assertEqual(stored[command(OWN, 1)["id"]]["status"], "done")

    def test_started_is_settled_after_the_restart(self) -> None:
        self.manager.command_log.record(PORTAL.command_result(command(OWN, 1)["id"], "started"))
        self.apps = [{**OWN, "version": "0.8.63", "updateAvailable": False}]
        results = self.manager.handle_commands([command(OWN, 1)])
        self.assertEqual((results[0]["status"], results[0]["version"]), ("done", "0.8.63"))
        self.install.assert_not_called()
        self.manager.command_log.record(PORTAL.command_result(command(OWN, 2)["id"], "started"))
        self.apps = [OWN]
        results = self.manager.handle_commands([command(OWN, 2)])
        self.assertEqual((results[0]["status"], results[0]["message"]), ("failed", "The update did not finish."))

    def test_restart_answers_started_then_restarts_last(self) -> None:
        order: list[str] = []
        self.publisher._call_service.side_effect = lambda domain, service, data: order.append(
            f"{service}:{','.join(item['status'] for item in (data.get('payload') or data.get('variables', {}).get('payload') or {}).get('results', []))}"
        )

        def call(payload, timeout):
            order.append(f"{payload['domain']}.{payload['service']}")
            if payload["service"] == "restart":
                raise SERVER.HomeAssistantConnectionLost("Lost the connection to Home Assistant (OSError).")

        self.install.side_effect = call
        results = self.manager.handle_commands([restart_command(1), command(ADDON, 2), restart_command(3)])
        self.assertEqual(order, [
            "update.install",
            # The second restart in one answer is refused; the first goes last, after "started" is out.
            "future_tech_send_command_results:rejected,done,started",
            "homeassistant.restart",
        ])
        self.assertEqual(self.install.call_args_list[-1].args,
                         ({"type": "call_service", "domain": "homeassistant", "service": "restart"}, 120))
        self.assertEqual(self.manager.command_log.read()[restart_command(1)["id"]]["status"], "started")
        self.assertEqual([item["status"] for item in results], ["rejected", "done", "started"])
        # Repeated once Home Assistant is back: done. Not run again.
        log = self.data / "future_tech_portal_commands.json"
        stored = json.loads(log.read_text())
        for entry in stored["handled"]:
            entry["at"] = (datetime.now(timezone.utc) - timedelta(minutes=3)).isoformat()
        log.write_text(json.dumps(stored))
        order.clear()
        results = self.manager.handle_commands([restart_command(1)])
        self.assertEqual((results[0]["status"], results[0]["message"]), ("done", "Home Assistant restarted."))
        self.assertNotIn("homeassistant.restart", order)

    def test_refused_restart_is_failed_and_early_restart_waits(self) -> None:
        self.install.side_effect = SERVER.HomeAssistantAPIError("The system cannot restart because the configuration is not valid")
        results = self.manager.handle_commands([restart_command(1)])
        self.assertEqual([item["status"] for item in results], ["started", "failed"])
        self.assertIn("configuration is not valid", results[1]["message"])
        self.assertEqual(self.manager.command_log.read()[restart_command(1)["id"]]["status"], "failed")
        self.install.reset_mock()
        later = restart_command(2, runAfter=(datetime.now(timezone.utc) + timedelta(hours=2)).isoformat())
        self.assertEqual(self.manager.handle_commands([later]), [])
        self.install.assert_not_called()

    def test_expired_and_extra_requests_are_ignored(self) -> None:
        expired = command(ADDON, 1, expiresAt=(datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat())
        self.assertEqual(self.manager.handle_commands([expired]), [])
        many = [command(CURRENT, index) for index in range(1, 8)]
        self.assertEqual(len(self.manager.handle_commands(many)), PORTAL.COMMANDS_PER_RESPONSE)

    def test_results_need_the_package(self) -> None:
        self.manager.package_path.unlink()
        self.manager.send_command_results([PORTAL.command_result("cmd-1", "done")])
        self.publisher._call_service.assert_not_called()

    def test_event_reaches_the_worker(self) -> None:
        request = command(ADDON, 1)
        with patch.object(self.manager, "handle_commands") as handle:
            self.manager.receive_commands({"commands": [request]})
            self.manager.receive_commands({"commands": "nope"})
            for _ in range(100):
                if handle.called:
                    break
                self.manager._command_worker.join(0.02)
        handle.assert_called_once_with([request])


class SettingRouteTests(unittest.TestCase):
    def test_the_settings_action_saves_the_switch(self) -> None:
        from test_future_tech_portal import RouteTests

        class Routes(RouteTests):
            def runTest(self) -> None:  # noqa: N802 - unittest hook
                pass

        routes = Routes()
        routes.setUp()
        self.addCleanup(routes.doCleanups)
        routes.manager.save_token(TOKEN)
        status, payload = routes.handler("POST", {"action": "settings", "allow_app_updates": False})
        self.assertEqual((status, payload["allow_app_updates"], payload["enabled"]), (200, False, True))
        status, payload = routes.handler("POST", {"action": "settings", "integrations": ["zha"]})
        self.assertIs(payload["allow_app_updates"], False, "Other settings leave it alone")


class LiveListenerTests(unittest.TestCase):
    def test_listener_gets_the_event_data_and_never_breaks_the_reader(self) -> None:
        inventory = SERVER.EntityInventory("token", "http://supervisor/core/api/states", "ws://supervisor/core/websocket")
        seen: list[dict] = []
        inventory.add_event_listener(PORTAL.COMMANDS_EVENT, seen.append)
        inventory._notify_listener(PORTAL.COMMANDS_EVENT, {"event": {"data": {"commands": [1]}}})
        inventory._notify_listener(PORTAL.COMMANDS_EVENT, {"event": "nope"})
        self.assertEqual(seen, [{"commands": [1]}])
        inventory.add_event_listener(PORTAL.COMMANDS_EVENT, Mock(side_effect=RuntimeError("boom")))
        inventory._notify_listener(PORTAL.COMMANDS_EVENT, {"event": {"data": {}}})


if __name__ == "__main__":
    unittest.main()
