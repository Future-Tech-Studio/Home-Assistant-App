"""Scoped snapshots stay fresh without blocking live state updates."""

import importlib.util
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch


SPEC = importlib.util.spec_from_file_location("projection_server", Path(__file__).resolve().parents[1] / "future_homes_tech_app/server.py")
SERVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SERVER)


class Uncopiable:
    def __deepcopy__(self, memo):
        raise AssertionError("Unrelated entity was copied")


class ProjectionCacheTests(unittest.TestCase):
    def inventory(self, states):
        inventory = SERVER.EntityInventory("test", "http://unused", "ws://unused")
        inventory._cached_entities = {entity["entity_id"]: entity for entity in SERVER.normalize_entities(states)}
        inventory._live_connected = True
        return inventory

    def state(self, identifier, state="off", **attributes):
        return {"entity_id": identifier, "state": state, "attributes": attributes}

    def test_security_skips_other_entities_and_all_registry_reads(self):
        inventory = self.inventory([
            self.state("binary_sensor.front_door", "off", device_class="door", friendly_name="Front Door"),
            self.state("binary_sensor.hall_motion", "on", device_class="motion"),
            self.state("light.other"),
        ])
        inventory._cached_entities["light.other"]["unused"] = Uncopiable()
        with (
            patch.object(SERVER, "entity_areas_from_storage", side_effect=AssertionError("Registry reopened")),
            patch.object(SERVER, "entity_devices_from_storage", side_effect=AssertionError("Registry reopened")),
            patch.object(SERVER, "entity_integrations_from_storage", side_effect=AssertionError("Registry reopened")),
            patch.object(SERVER, "urlopen", side_effect=AssertionError("Unexpected network request")),
        ):
            first = inventory.fetch_security()
            self.assertEqual(first["count"], 1)
            inventory._apply_state_changed("binary_sensor.front_door", self.state("binary_sensor.front_door", "on", device_class="door", friendly_name="Front Door"))
            updated = inventory.fetch_security()
        self.assertEqual(first["entities"][0]["state"], "off")
        self.assertEqual(updated["entities"][0]["state"], "on")
        self.assertEqual(updated["entities"][0]["entity_id"], "binary_sensor.front_door")

    def test_room_projection_copies_only_room_and_aliases_once(self):
        inventory = self.inventory([
            self.state("light.bedroom", friendly_name="Bedroom 2 Lights", fht_area="Bedroom 2"),
            self.state("light.other", fht_area="Pantry"),
        ])
        inventory._cached_entities["light.other"]["unused"] = Uncopiable()
        inventory._room_aliases = Mock()
        inventory._room_aliases.read.return_value = {"Bedroom 2": "Bailey's Bedroom"}
        result = inventory.refresh_room("Bedroom 2")
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["entities"][0]["area"], "Bailey's Bedroom")
        self.assertEqual(result["entities"][0]["original_area"], "Bedroom 2")
        self.assertEqual(result["entities"][0]["friendly_name"], "Bailey's Bedroom Lights")

    def test_state_updates_keep_index_and_only_change_one_record(self):
        inventory = self.inventory([self.state("light.one"), self.state("light.two")])
        index = inventory._cached_entities
        untouched = index["light.two"]
        old = index["light.one"]
        inventory._apply_state_changed("light.one", self.state("light.one", "on", brightness=100))
        self.assertIs(index, inventory._cached_entities)
        self.assertIs(untouched, inventory._cached_entities["light.two"])
        self.assertEqual(old["state"], "off")
        self.assertEqual(inventory._metadata_revision, 0)
        inventory._apply_state_changed("light.one", self.state("light.one", "on", friendly_name="Renamed"))
        self.assertEqual(inventory._metadata_revision, 1)
        inventory._apply_state_changed("light.one", self.state("light.one", "on", friendly_name="Renamed", entity_id=["light.two"]))
        self.assertEqual(inventory._metadata_revision, 2)
        inventory._apply_state_changed("light.one", None)
        self.assertEqual(inventory._metadata_revision, 3)
        inventory._apply_state_changed("light.new", self.state("light.new"))
        self.assertEqual(inventory._metadata_revision, 4)

    def test_projection_copy_does_not_hold_live_event_lock(self):
        inventory = self.inventory([self.state("light.one")])
        copying, release, changed = threading.Event(), threading.Event(), threading.Event()

        class SlowCopy:
            def __deepcopy__(self, memo):
                copying.set()
                release.wait(2)
                return "copied"

        inventory._cached_entities["light.one"]["unused"] = SlowCopy()
        results = []
        reader = threading.Thread(target=lambda: results.append(inventory.fetch(include_all=True)))
        writer = threading.Thread(target=lambda: (inventory._apply_state_changed("light.one", self.state("light.one", "on")), changed.set()))
        try:
            reader.start()
            self.assertTrue(copying.wait(1))
            writer.start()
            self.assertTrue(changed.wait(1))
        finally:
            release.set()
            reader.join(2)
            if writer.ident:
                writer.join(2)
        self.assertEqual(results[0]["entities"][0]["state"], "off")
        self.assertEqual(inventory.cached_entity("light.one")["state"], "on")

    def test_metadata_fields_exclude_live_values_but_keep_capabilities(self):
        inventory = self.inventory([self.state("select.effect", "Pulse", options=["Pulse", "Blink"])])
        result = inventory.fetch(include_all=True, fields=SERVER.ENTITY_CATALOG_FIELDS)
        self.assertNotIn("state", result["entities"][0])
        self.assertEqual(result["entities"][0]["options"], ["Pulse", "Blink"])
        result["entities"][0]["options"].append("Changed outside cache")
        self.assertEqual(inventory.cached_entity("select.effect")["options"], ["Pulse", "Blink"])

    def test_empty_projection_does_not_mark_populated_cache_stale(self):
        inventory = self.inventory([self.state("light.one")])
        inventory._cached_complete_at_monotonic = SERVER.time.monotonic()
        result = inventory.fetch_security()
        self.assertEqual(result["entities"], [])
        self.assertFalse(result["stale"])

    def test_full_refresh_only_invalidates_catalog_for_metadata_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            inventory = SERVER.EntityInventory("test", "http://unused", "ws://unused", Path(directory))
            current = [self.state("light.one", friendly_name="One", fht_area="Room")]

            def response(*args, **kwargs):
                return io.BytesIO(json.dumps(current).encode())

            with (
                patch.object(SERVER, "urlopen", side_effect=response),
                patch.object(SERVER, "fetch_entity_integrations", return_value={}),
            ):
                first = inventory.fetch(include_all=True, force=True)
                current[0]["state"] = "on"
                second = inventory.fetch(include_all=True, force=True)
                self.assertEqual(first["metadata_revision"], second["metadata_revision"])
                self.assertGreater(second["revision"], first["revision"])
                current[0]["attributes"]["friendly_name"] = "New name"
                renamed = inventory.fetch(include_all=True, force=True)
                self.assertGreater(renamed["metadata_revision"], second["metadata_revision"])
                self.assertEqual(renamed["entities"][0]["friendly_name"], "New name")


if __name__ == "__main__":
    unittest.main()
