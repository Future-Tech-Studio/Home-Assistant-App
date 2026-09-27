"""Exercise the real ingress routing, identity and CSRF checks over loopback."""

import json
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from access_preview import create_preview, OWNER_ID, GUEST_ID, SERVER


class AccessHTTPTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.server = create_preview(self.directory.name)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}/api/access/"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.directory.cleanup()

    def request(self, route, payload=None, user=OWNER_ID, csrf=None, content_type="application/json"):
        headers = {"X-Remote-User-Id": user} if user else {}
        if csrf:
            headers["X-FHT-Access-CSRF"] = csrf
        if payload is not None:
            headers["Content-Type"] = content_type
        request = Request(self.base + route, headers=headers, data=json.dumps(payload).encode() if payload is not None else None)
        try:
            response = urlopen(request, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response), dict(response.headers)

    def test_missing_identity_guest_and_direct_debug_bypass_are_denied(self):
        self.server.RequestHandlerClass.allow_non_ingress = True
        for user in (None, GUEST_ID, "fake-user"):
            status, payload, headers = self.request("people", user=user)
            self.assertEqual(status, 403)
            self.assertFalse(payload["ok"])
            self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertFalse(self.server.RequestHandlerClass.access_store.path.exists())

    def test_csrf_required_and_user_payload_cannot_elevate_caller(self):
        payload = {"name": "Test", "confirmed": True, "user_id": OWNER_ID}
        self.assertEqual(self.request("people/save", payload)[0], 403)
        token = self.request("session")[1]["csrf"]
        self.assertEqual(self.request("people/save", payload, user=GUEST_ID, csrf=token)[0], 403)
        self.assertEqual(self.request("people/save", payload, csrf=token, content_type="text/plain")[0], 415)

    def test_create_read_and_delete_flow_and_no_secret_in_read_response(self):
        token = self.request("session")[1]["csrf"]
        status, payload, headers = self.request("people/save", {"name": "Alex", "role": "resident", "rooms": ["bedroom2"], "confirmed": True}, csrf=token)
        self.assertEqual(status, 200)
        person = payload["record"]
        status, issued, headers = self.request("pin/issue", {"person_id": person["id"], "person_revision": 1, "generate": True, "confirmed": True}, csrf=token)
        self.assertEqual(status, 200)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertFalse(issued["credential"]["physical_access_installed"])
        detail = self.request("people?id=" + person["id"])[1]
        self.assertNotIn(issued["pin"], json.dumps(detail))
        self.assertNotIn("salt", json.dumps(detail))
        self.assertEqual(self.request("people/remove", {"id": person["id"], "revision": 1, "confirmed": True}, csrf=token)[0], 200)
        self.assertEqual(self.request("people")[1]["items"], [])

    def test_unknown_routes_and_catalog_do_not_enable_devices(self):
        self.assertEqual(self.request("credentials/dump")[0], 404)
        token = self.request("session")[1]["csrf"]
        self.assertEqual(self.request("locks/unlock", {"confirmed": True}, csrf=token)[0], 404)
        catalog = self.request("catalog")[1]
        self.assertFalse(catalog["physical_access_enabled"])
        self.assertFalse(catalog["panel_access_enabled"])

    def test_real_catalog_uses_existing_snapshot_not_new_inventory_requests(self):
        handler = SERVER.FutureHomesTechRequestHandler.__new__(SERVER.FutureHomesTechRequestHandler)
        handler.inventory = SimpleNamespace(_config_directory=Path(self.directory.name), _cache_lock=threading.Lock(),
                                           _cached_entities={"lock.front": {"entity_id": "lock.front", "friendly_name": "Front Door"}})
        handler.room_aliases = Mock()
        handler.room_aliases.read.return_value = {"Bedroom 2": "Bailey's Bedroom"}
        structure = {"floors": [{"name": "First Floor", "areas": [{"area_id": "bedroom2", "name": "Bedroom 2"}]}]}
        with patch.object(SERVER, "home_structure_from_storage", return_value=structure):
            catalog = handler._access_catalog()
        self.assertEqual(catalog["rooms"][0]["name"], "Bailey's Bedroom")
        self.assertEqual(catalog["resources"][0]["id"], "lock.front")


if __name__ == "__main__":
    unittest.main()
