import json
import tempfile
import threading
import unittest
from unittest.mock import Mock
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from access_preview import create_preview, OWNER_ID, GUEST_ID


class MaintenanceHTTPTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.server = create_preview(self.directory.name)
        self.service = Mock()
        self.service.review.return_value = {"items": []}
        self.service.archive.return_value = {"count": 1}
        self.server.RequestHandlerClass.maintenance = self.service
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}/api/"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.directory.cleanup()

    def request(self, route, payload=None, user=OWNER_ID, csrf=None):
        headers = {"X-Remote-User-Id": user} if user else {}
        if csrf:
            headers["X-FHT-Access-CSRF"] = csrf
        if payload is not None:
            headers["Content-Type"] = "application/json"
        request = Request(self.base + route, headers=headers, data=json.dumps(payload).encode() if payload is not None else None)
        try:
            response = urlopen(request, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response), dict(response.headers)

    def test_admin_required_for_reads_and_writes(self):
        for user in (None, GUEST_ID, "fake"):
            self.assertEqual(self.request("maintenance/review", user=user)[0], 403)
            self.assertEqual(self.request("maintenance/archive", {}, user=user)[0], 403)
        self.service.review.assert_not_called()
        self.service.archive.assert_not_called()

    def test_no_store_and_csrf_for_mutations(self):
        status, result, headers = self.request("maintenance/review")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(self.request("maintenance/archive", {})[0], 403)
        token = self.request("access/session")[1]["csrf"]
        self.assertEqual(self.request("maintenance/archive", {"confirmed": True}, csrf=token)[0], 200)
        self.service.archive.assert_called_once()

    def test_unknown_route_invalid_query_and_redacted_error(self):
        self.assertEqual(self.request("maintenance/missing")[0], 404)
        self.service.review.side_effect = RuntimeError("private-token-secret")
        status, result, headers = self.request("maintenance/review")
        self.assertEqual(status, 503)
        self.assertNotIn("private-token", json.dumps(result))
