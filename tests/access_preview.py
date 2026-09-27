"""Loopback-only fixture server for Users UI tests. Never deployed in the app."""

import importlib.util
from http.server import ThreadingHTTPServer
from pathlib import Path
import tempfile
import time
from urllib.parse import urlsplit


ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("access_preview_server", ROOT / "future_homes_tech_app/server.py")
SERVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SERVER)
OWNER_ID = "a" * 32
GUEST_ID = "b" * 32


def create_preview(directory, port=0):
    class Preview(SERVER.FutureHomesTechRequestHandler):
        web_root = ROOT / "future_homes_tech_app/web"
        ingress_proxy_ip = "127.0.0.1"
        allow_non_ingress = False
        access_store = SERVER.ACCESS.AccessStore(Path(directory))
        access_admin = SERVER.ACCESS.AccessAdmin(lambda: [
            {"id": OWNER_ID, "name": "Preview Owner", "is_active": True, "is_owner": True, "group_ids": []},
            {"id": GUEST_ID, "name": "Preview Guest", "is_active": True, "is_owner": False, "group_ids": []},
        ])

        def _access_catalog(self):
            return {"rooms": [{"id": "bedroom2", "name": "Bailey's Bedroom"}, {"id": "bedroom6", "name": "Chloe's Bedroom"}],
                    "resources": [{"id": "binary_sensor.front_door", "name": "Front Door", "kind": "door_sensor"}],
                    "roles": SERVER.ACCESS.ROLES, "role_defaults": SERVER.ACCESS.ROLE_DEFAULTS,
                    "capabilities": SERVER.ACCESS.CAPABILITIES, "timezone": "America/Phoenix",
                    "physical_access_enabled": False, "panel_access_enabled": False}

        def do_GET(self):
            path = urlsplit(self.path).path
            if path.startswith("/api/") and not path.startswith("/api/access/") and not (hasattr(self, "maintenance") and path.startswith("/api/maintenance/")):
                if path == "/api/live/revision":
                    time.sleep(1)
                payload = {"ok": True, "entities": [], "settings": {}, "floors": [], "rooms": [], "revision": 1, "changed": False}
                if path == "/api/app-info":
                    payload.update(installed_version="0.5.24", update_available=False)
                if path == "/api/weather/temperature":
                    payload.update(temperature=89)
                self._send_json(200, payload)
                return
            super().do_GET()

        def do_POST(self):
            if not urlsplit(self.path).path.startswith("/api/access/") and not (hasattr(self, "maintenance") and urlsplit(self.path).path.startswith("/api/maintenance/")):
                self._send_json(405, {"ok": False, "error": "Device operations are disabled in the test fixture."})
                return
            super().do_POST()

        def log_request(self, *args):
            pass

    return ThreadingHTTPServer(("127.0.0.1", port), Preview)


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="fht-users-preview-") as directory:
        server = create_preview(directory, 8784)
        try:
            print("Loopback Users fixture ready on 8784; no Home Assistant device connection", flush=True)
            server.serve_forever()
        finally:
            server.server_close()
