"""Exercise startup delivery, live reconnects, and nonblocking cache reads."""

import gzip
import io
import json
from pathlib import Path
import re
import shutil
import socket
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from test_server import SERVER, MODULE_PATH


class StartupDeliveryTests(unittest.TestCase):
    def handler(self, headers=None):
        handler = object.__new__(SERVER.FutureHomesTechRequestHandler)
        handler.web_root = MODULE_PATH.with_name("web")
        handler.headers = headers or {}
        handler.path = "/"
        handler.wfile = io.BytesIO()
        handler.send_response = Mock()
        handler.send_header = Mock()
        handler.end_headers = Mock()
        return handler

    def test_iframe_loads_application_without_destroying_home_assistant(self):
        handler = self.handler({"Sec-Fetch-Dest": "iframe"})
        handler._serve_index()
        document = handler.wfile.getvalue().decode()
        self.assertLess(len(document), 50000)
        self.assertNotIn("window.top.location.replace", document)
        self.assertNotIn("window.location.replace", document)
        self.assertIn("frame.showPopover()", document)
        self.assertNotIn("api/", document)
        self.assertIn("interface-", document)
        self.assertNotIn("__FHT_CSP_NONCE__", document)

    def test_blocked_kiosk_navigation_has_a_complete_embedded_fallback(self):
        handler = self.handler({"Sec-Fetch-Dest": "iframe"})
        handler.path = "/?fht_embedded=1"
        handler._serve_index()
        document = handler.wfile.getvalue().decode()
        self.assertIn('id="view-home"', document)
        self.assertIn('src="interface-', document)

    def test_shell_assets_revalidate_without_resending_the_bundle(self):
        handler = self.handler()
        handler._serve_index()
        shell = handler.wfile.getvalue().decode()
        self.assertLess(len(shell.encode()), 50000)
        paths = re.findall(r'(?:href|src)="(interface-[a-f0-9]+\.(?:css|js))"', shell)
        self.assertEqual(len(paths), 2)
        for path in paths:
            asset_handler = self.handler({"Accept-Encoding": "gzip"})
            asset_handler._serve_interface_asset("/" + path)
            headers = dict(call.args for call in asset_handler.send_header.call_args_list)
            self.assertEqual(headers["Content-Encoding"], "gzip")
            self.assertIn("immutable", headers["Cache-Control"])
            raw = gzip.decompress(asset_handler.wfile.getvalue())
            self.assertGreater(len(raw), 50000)
            if path.endswith(".js"):
                self.assertTrue(raw.startswith(b"if (!window.fhtKioskRedirecting)"))
            cached_handler = self.handler({"If-None-Match": headers["ETag"]})
            cached_handler._serve_interface_asset("/" + path)
            cached_handler.send_response.assert_called_once_with(304)
            self.assertEqual(cached_handler.wfile.getvalue(), b"")

    def test_asset_fingerprint_changes_when_source_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = MODULE_PATH.with_name("web").joinpath("index.html").read_text()
            root.joinpath("index.html").write_text(source)
            before = SERVER.interface_bundle(str(root), 1, len(source))
            root.joinpath("index.html").write_text(source.replace('const CLIENT_VERSION = "', 'const CLIENT_VERSION = "test-'))
            after = SERVER.interface_bundle(str(root), 2, len(source) + 5)
            self.assertNotEqual(set(before["assets"]), set(after["assets"]))

    def test_old_asset_hash_is_a_404_not_html(self):
        handler = self.handler()
        handler._serve_interface_asset("/interface-0000000000000000.js")
        handler.send_response.assert_called_once_with(404)
        self.assertFalse(json.loads(handler.wfile.getvalue())["ok"])

    def test_protect_reports_safe_connection_diagnostics(self):
        cases = (
            (SERVER.URLError(SERVER.ssl.SSLCertVerificationError(1, "private certificate details")), "TLS certificate verification failed"),
            (SERVER.URLError(socket.gaierror(-2, "private hostname")), "hostname could not be resolved"),
            (SERVER.URLError(TimeoutError()), "connection timed out"),
            (SERVER.URLError(ConnectionRefusedError()), "refused the connection"),
        )
        for failure, message in cases:
            with self.subTest(message=message):
                client = SERVER.ProtectAPI("secret-key", "https://console.test/proxy/protect/integration/v1/alarm-manager/webhook/private")
                with patch.object(SERVER, "urlopen", side_effect=failure):
                    with self.assertRaises(SERVER.HomeAssistantAPIError) as caught:
                        client._fetch_json("nvrs")
                self.assertIn(message, str(caught.exception))
                self.assertNotIn("private", str(caught.exception))
                self.assertNotIn("secret-key", str(caught.exception))

    def test_security_projection_uses_already_enriched_snapshot(self):
        inventory = SERVER.EntityInventory("test", "http://test/states", "ws://test/websocket")
        payload = {"generated_at":"now", "entities":[{"entity_id":"binary_sensor.front_door", "domain":"binary_sensor", "state":"off", "friendly_name":"Front Door", "device_class":"door", "area":"Entry"}]}
        with patch.object(inventory, "fetch", return_value=payload), patch.object(SERVER, "entity_areas_from_storage", side_effect=AssertionError("Repeated registry read")):
            result = inventory.fetch_entry_doors()
        self.assertEqual(result["entities"][0]["state"], "off")
        self.assertEqual(result["entities"][0]["area"], "Entry")

    def test_restart_resets_a_client_revision_without_a_long_wait(self):
        inventory = SERVER.EntityInventory("test", "http://test/states", "ws://test/websocket")
        inventory._cache_revision = 3
        with patch.object(inventory._cache_condition, "wait_for", wraps=inventory._cache_condition.wait_for) as wait:
            update = inventory.wait_for_revision(1000, timeout=0)
        self.assertTrue(update["changed"])
        self.assertTrue(update["resync"])
        self.assertEqual(update["revision"], 3)
        self.assertTrue(wait.call_args.args[0]())
        self.assertFalse(inventory.wait_for_revision(3, timeout=0)["changed"])

    def test_new_browser_session_resyncs_after_history_rolls_over(self):
        """A page with no prior revision must load everything even when the snapshot event is gone."""
        inventory = SERVER.EntityInventory("test", "http://test/states", "ws://test/websocket")
        inventory._cache_revision = 0
        self.assertFalse(inventory.wait_for_revision(0, timeout=0)["resync"])
        for revision in range(1, SERVER.ENTITY_EVENT_HISTORY_LIMIT + 50):
            inventory._cache_revision = revision
            inventory._event_history.append({
                "revision": revision, "entity_id": "light.test", "area": "Office",
                "channels": ["lighting"], "resync": revision == 1,
            })
        self.assertFalse(any(event["resync"] for event in inventory._event_history))
        update = inventory.wait_for_revision(0, timeout=0)
        self.assertTrue(update["changed"])
        self.assertTrue(update["resync"])
        self.assertEqual(update["revision"], SERVER.ENTITY_EVENT_HISTORY_LIMIT + 49)
        self.assertFalse(inventory.wait_for_revision(update["revision"] - 1, timeout=0)["resync"])

    def test_stale_cache_returns_while_one_recovery_request_is_pending(self):
        inventory = SERVER.EntityInventory("test", "http://test/states", "ws://test/websocket")
        inventory._cached_entities = {"light.test": {"entity_id": "light.test", "domain": "light", "state": "on"}}
        inventory._cached_complete_at_monotonic = -1000
        entered = threading.Event()
        release = threading.Event()

        def recover():
            entered.set()
            release.wait(2)
            raise SERVER.HomeAssistantAPIError("Temporarily disconnected")

        with patch.object(inventory, "_fetch_full_inventory", side_effect=recover) as refresh:
            try:
                first = inventory.fetch(include_all=True)
                self.assertTrue(entered.wait(1))
                second = inventory.fetch(include_all=True)
                self.assertTrue(first["stale"])
                self.assertEqual(second["entities"], first["entities"])
                self.assertEqual(refresh.call_count, 1)
            finally:
                release.set()
                inventory._background_refresh_thread.join(2)
        self.assertIn("Temporarily disconnected", inventory.peek()["last_error"])

    def test_lighting_projection_does_not_reopen_registry_files(self):
        inventory = SERVER.EntityInventory("test", "http://test/states", "ws://test/websocket")
        inventory._cached_entities = {"light.fht_pantry_all_lights": {"entity_id": "light.fht_pantry_all_lights", "domain": "light", "state": "off", "area": "Pantry"}}
        inventory._live_connected = True
        with patch.object(SERVER, "entity_areas_from_storage", side_effect=AssertionError("Registry read during cached projection")):
            self.assertEqual(inventory.fetch_lighting()["entities"][0]["area"], "Pantry")

    def test_live_events_can_arrive_between_subscription_acknowledgements(self):
        inventory = SERVER.EntityInventory("test", "http://test/states", "ws://test/websocket")
        connection = Mock()
        messages = iter([
            {"type": "auth_required"}, {"type": "auth_ok"},
            {"type": "result", "id": 1, "success": True},
            {"type": "event", "id": 1, "event": {"data": {"entity_id": "light.test", "new_state": {"entity_id": "light.test", "state": "on"}}}},
            *({"type": "result", "id": identifier, "success": True} for identifier in (3, 2, 5, 4)),
        ])

        def receive(*args):
            try:
                return next(messages)
            except StopIteration:
                inventory._live_stop.set()
                return {"type": "pong"}

        with (
            patch.object(SERVER, "_open_websocket", return_value=(connection, bytearray())),
            patch.object(SERVER, "_receive_websocket_json", side_effect=receive),
            patch.object(SERVER, "_send_websocket_json"),
            patch.object(SERVER, "_send_websocket_frame"),
            patch.object(inventory, "_fetch_full_inventory") as refresh,
            patch.object(inventory, "_apply_state_changed") as event,
        ):
            inventory._run_live_updates()
        refresh.assert_called_once()
        event.assert_called_once()
        self.assertTrue(inventory._live_connected)

    def test_live_waiters_leave_capacity_for_navigation(self):
        server = object.__new__(SERVER.BoundedThreadingHTTPServer)
        server.live_waiter_slots = threading.BoundedSemaphore(1)
        server.live_waiter_slots.acquire()
        handler = self.handler()
        handler.server = server
        handler.path = "/api/live/revision?after=1"
        handler._request_is_allowed = Mock(return_value=True)
        handler.inventory = Mock()
        handler.do_GET()
        handler.send_response.assert_called_once_with(503)
        handler.inventory.wait_for_revision.assert_not_called()
        handler.send_response.reset_mock()
        handler.wfile = io.BytesIO()
        handler.path = "/"
        handler.do_GET()
        handler.send_response.assert_called_once_with(200)

    def test_overload_response_content_length_matches_body(self):
        server = object.__new__(SERVER.BoundedThreadingHTTPServer)
        server._worker_slots = threading.BoundedSemaphore(1)
        server._worker_slots.acquire()
        server.shutdown_request = Mock()
        request = Mock(spec=socket.socket)
        server.process_request(request, ("127.0.0.1", 1234))
        headers, body = request.sendall.call_args.args[0].split(b"\r\n\r\n", 1)
        length = re.search(rb"Content-Length: (\d+)", headers).group(1)
        self.assertEqual(int(length), len(body))

    def test_offline_menu_uses_a_small_snapshot_summary(self):
        handler = self.handler()
        handler._request_is_allowed = Mock(return_value=True)
        handler.path = "/api/menu/status"
        handler.inventory = Mock()
        handler.inventory.peek.return_value = {
            "stale": False,
            "entities": [
                {"domain": "climate", "state": "unavailable"},
                {"domain": "climate", "state": "heat"},
                {"domain": "light", "state": "unavailable"},
            ],
        }
        handler.do_GET()
        self.assertEqual(json.loads(handler.wfile.getvalue()), {"ok": True, "climate_offline": 1, "stale": False})
        handler.inventory.fetch.assert_not_called()

    def test_cancelled_browser_request_is_not_a_server_crash(self):
        handler = self.handler()
        with patch.object(SERVER.BaseHTTPRequestHandler, "handle_one_request", side_effect=BrokenPipeError):
            handler.handle_one_request()
        self.assertTrue(handler.close_connection)


class BrowserBehaviorTests(unittest.TestCase):
    def test_real_browser_functions_in_isolated_runtime(self):
        node = shutil.which("node") or str(Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node")
        result = subprocess.run([node, str(Path(__file__).with_name("web_behavior.mjs"))], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
