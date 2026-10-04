"""Scenes light automations offer lights that have no group of their own."""

from __future__ import annotations

import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from test_server import SERVER


class SingleLightScheduleTests(unittest.TestCase):
    def handler(self, method: str, body: dict | None = None):
        handler = object.__new__(SERVER.FutureHomesTechRequestHandler)
        handler.path = "/api/light-schedules"
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
        handler.light_schedules = self.schedules
        handler.light_schedule_automations = Mock()
        handler.light_schedule_automations.sync.return_value = []
        handler.registry_organizer = Mock()
        handler.inventory = Mock()
        handler.inventory.fetch.return_value = {"entities": [
            {"entity_id": "light.fht_outside_all_lights", "area": "Outside"},
            {"entity_id": "light.porch", "area": "Outside"},
            {"entity_id": "light.no_room"},
        ]}
        getattr(handler, f"do_{method}")()
        return handler.send_response.call_args.args[0], json.loads(handler.wfile.getvalue())

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        history = patch.object(SERVER, "SETTINGS_HISTORY", SERVER.HISTORY.SettingsHistory([root]))
        history.start()
        self.addCleanup(history.stop)
        self.schedules = SERVER.LightScheduleSettings(root / "light_schedules.json")

    def test_lists_lights_the_generator_offers_as_themselves(self) -> None:
        replacements = {
            "light.fht_outside_porch_lights": ["light.porch"],
            "light.fht_outside_side_yard_lights": ["light.side_yard"],
            "light.fht_outside_lights": ["light.fht_outside_all_lights"],
            "light.fht_den_fan_lights": ["light.fht_den_all_lights", "light.den_lamp"],
        }
        with patch.object(SERVER, "generated_light_group_replacements", return_value=replacements):
            status, payload = self.handler("GET")
        self.assertEqual(status, 200)
        self.assertEqual(payload["single_lights"], ["light.porch", "light.side_yard"])

    def test_a_single_room_light_can_be_scheduled(self) -> None:
        status, payload = self.handler("POST", {"entity_id": "light.porch", "schedule": {"enabled": True}})
        self.assertEqual(status, 200, payload)
        self.assertIn("light.porch", payload["schedules"])
        status, payload = self.handler("POST", {"entity_id": "light.no_room", "schedule": {"enabled": True}})
        self.assertEqual(status, 400, "A light outside any room is still refused")


if __name__ == "__main__":
    unittest.main()
