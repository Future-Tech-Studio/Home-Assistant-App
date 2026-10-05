"""The Security page shows UniFi Protect devices, read-only."""

import importlib.util
import io
from pathlib import Path
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location("protect_server", Path(__file__).resolve().parents[1] / "future_homes_tech_app/server.py")
SERVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SERVER)


def entity(entity_id, state, device_id="", device_name="", integration="unifiprotect", **extra):
    return {
        "entity_id": entity_id,
        "domain": entity_id.partition(".")[0],
        "state": state,
        "friendly_name": extra.pop("friendly_name", ""),
        "device_id": device_id,
        "device_name": device_name,
        "integration": integration,
        **extra,
    }


DOORBELL = [
    entity("camera.doorbell_lite_high", "recording", "db", "Doorbell Lite", area="Porch"),
    entity("camera.doorbell_lite_package", "idle", "db", "Doorbell Lite", area="Porch"),
    entity("binary_sensor.doorbell_lite_doorbell", "off", "db", "Doorbell Lite", friendly_name="Doorbell Lite Doorbell"),
    entity("binary_sensor.doorbell_lite_person_detected", "on", "db", "Doorbell Lite", friendly_name="Doorbell Lite Person Detected", device_class="occupancy"),
    entity("switch.doorbell_lite_privacy_mode", "off", "db", "Doorbell Lite"),
    entity("select.doorbell_lite_recording_mode", "Always", "db", "Doorbell Lite"),
    entity("sensor.doorbell_lite_uptime", "2026-10-01T00:00:00Z", "db", "Doorbell Lite", entity_category="diagnostic"),
]
SENSOR = [
    entity("binary_sensor.garage_sense_contact", "on", "up", "Garage Sense", friendly_name="Garage Sense Contact", device_class="door", area="Garage"),
    entity("sensor.garage_sense_battery", "88", "up", "Garage Sense", friendly_name="Garage Sense Battery", device_class="battery", unit_of_measurement="%", entity_category="diagnostic"),
]
NVR = [entity("sensor.nvr_storage_used", "40", "nvr", "UNVR", entity_category="diagnostic")]
OTHER = [entity("binary_sensor.front_door", "off", "zz", "Front Door", integration="zha", device_class="door")]


class ProtectDeviceTests(unittest.TestCase):
    def test_groups_protect_devices_and_leaves_out_settings(self):
        devices = SERVER.protect_devices_from_entities(DOORBELL + SENSOR + NVR + OTHER)
        self.assertEqual([device["name"] for device in devices], ["Doorbell Lite", "Garage Sense"])
        doorbell, sensor = devices
        self.assertEqual(doorbell["kind"], "Doorbell")
        self.assertEqual(doorbell["area"], "Porch")
        self.assertEqual(doorbell["snapshot_entity"], "camera.doorbell_lite_high")
        self.assertEqual(doorbell["camera_state"], "recording")
        self.assertTrue(doorbell["online"])
        self.assertEqual(
            [reading["entity_id"] for reading in doorbell["readings"]],
            ["binary_sensor.doorbell_lite_doorbell", "binary_sensor.doorbell_lite_person_detected"],
        )
        self.assertEqual(doorbell["readings"][1]["label"], "Person Detected")
        self.assertEqual(sensor["kind"], "Sensor")
        self.assertEqual(sensor["snapshot_entity"], "")
        # A diagnostic battery stays; it is the one diagnostic worth showing.
        self.assertIn("sensor.garage_sense_battery", [reading["entity_id"] for reading in sensor["readings"]])

    def test_offline_camera(self):
        devices = SERVER.protect_devices_from_entities([
            entity("camera.side_g4", "unavailable", "g4", "Side G4"),
            entity("binary_sensor.side_g4_motion", "unavailable", "g4", "Side G4", device_class="motion"),
        ])
        self.assertEqual(devices[0]["kind"], "Camera")
        self.assertFalse(devices[0]["online"])

    def inventory(self, entities):
        inventory = SERVER.EntityInventory("token", "http://supervisor/core/api/states", "ws://unused")
        inventory._cached_entities = {item["entity_id"]: dict(item) for item in entities}
        inventory._live_connected = True
        inventory._cached_complete_at_monotonic = SERVER.time.monotonic()
        return inventory

    def test_fetch_protect_projection(self):
        result = self.inventory(DOORBELL + OTHER).fetch_protect()
        self.assertEqual(result["count"], 1)
        self.assertFalse(result["stale"])

    def test_snapshot_only_for_protect_cameras(self):
        inventory = self.inventory(DOORBELL + OTHER + [entity("camera.reolink", "idle", integration="reolink")])
        for entity_id in ("binary_sensor.front_door", "camera.reolink", "camera.nope", "switch.doorbell_lite_privacy_mode"):
            with self.assertRaises(ValueError):
                inventory.fetch_camera_snapshot(entity_id)

        class Response(io.BytesIO):
            headers = {"Content-Type": "image/jpeg"}

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        requests = []

        def fake_urlopen(request, timeout):
            requests.append(request)
            return Response(b"jpeg")

        with patch.object(SERVER, "urlopen", side_effect=fake_urlopen):
            body, content_type = inventory.fetch_camera_snapshot("camera.doorbell_lite_high", 640)
            inventory.fetch_camera_snapshot("camera.doorbell_lite_high", 640)
        self.assertEqual((body, content_type), (b"jpeg", "image/jpeg"))
        self.assertEqual(len(requests), 1, "a second request within the cache window reuses the snapshot")
        self.assertEqual(requests[0].full_url, "http://supervisor/core/api/camera_proxy/camera.doorbell_lite_high?width=640")
        self.assertEqual(requests[0].get_method(), "GET")

    def test_protect_state_change_notifies_protect_channel(self):
        inventory = self.inventory(DOORBELL)
        inventory._apply_state_changed(
            "binary_sensor.doorbell_lite_doorbell",
            {"entity_id": "binary_sensor.doorbell_lite_doorbell", "state": "on", "attributes": {}},
        )
        self.assertIn("protect", SERVER.EntityInventory._event_channels(inventory.cached_entity("binary_sensor.doorbell_lite_doorbell")))


if __name__ == "__main__":
    unittest.main()
