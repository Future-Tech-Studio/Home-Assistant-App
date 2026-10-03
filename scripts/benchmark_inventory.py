#!/usr/bin/env python3
"""Compare warm-cache CPU work against stable code without contacting HA."""

import copy
import importlib.util
import json
from pathlib import Path
import statistics
import tarfile
import time
import types
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]


def load_versions():
    pointer = json.loads((ROOT / "stable_releases/STABLE.json").read_text())
    with tarfile.open(ROOT / "stable_releases" / pointer["source_archive"]) as archive:
        content = archive.extractfile("./future_homes_tech_app/server.py").read()
    baseline = types.ModuleType("baseline_server")
    exec(compile(content, "stable/server.py", "exec"), baseline.__dict__)
    spec = importlib.util.spec_from_file_location("candidate_server", ROOT / "future_homes_tech_app/server.py")
    candidate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(candidate)
    return [("stable_" + pointer["stable_version"], baseline), ("candidate", candidate)]


def measure(server):
    states = [
        {
            "entity_id": f"{'binary_sensor' if index % 40 == 0 else 'light'}.device_{index}",
            "state": "off",
            "attributes": {
                "friendly_name": f"Room {index % 20} Device {index}",
                "fht_area": f"Room {index % 20}",
                "device_class": "door" if index % 40 == 0 else None,
            },
        }
        for index in range(4000)
    ]
    inventory = server.EntityInventory("test-only", "http://unused", "ws://unused")
    normalized = server.normalize_entities(states)
    inventory._cached_entities = (
        {entity["entity_id"]: entity for entity in normalized}
        if hasattr(inventory, "_metadata_revision") else normalized
    )
    inventory._cached_complete_at_monotonic = time.monotonic()
    inventory._live_connected = True
    inventory._room_aliases = Mock()
    inventory._room_aliases.read.return_value = {f"Room {index}": f"Area {index}" for index in range(20)}

    def median_milliseconds(operation):
        timings = []
        for _sample in range(7):
            started = time.perf_counter()
            operation()
            timings.append((time.perf_counter() - started) * 1000)
        return round(statistics.median(timings), 3)

    state = copy.deepcopy(states[1])
    with (
        patch.object(server, "urlopen", side_effect=AssertionError("Network access forbidden")),
        patch.object(server, "entity_areas_from_storage", return_value={}),
        patch.object(server, "entity_devices_from_storage", return_value={}),
        patch.object(server, "entity_integrations_from_storage", return_value={}),
    ):
        return {
            "security_projection_ms": median_milliseconds(inventory.fetch_security),
            "one_room_projection_ms": median_milliseconds(lambda: inventory.refresh_room("Room 1")),
            "one_state_event_ms": median_milliseconds(lambda: inventory._apply_state_changed(state["entity_id"], state)),
        }


if __name__ == "__main__":
    print(json.dumps({
        "scope": "Local synthetic warm cache: 4000 entities, 100 door sensors, 20 rooms; no network or disk I/O in measured operations",
        "results": {name: measure(server) for name, server in load_versions()},
    }, indent=2))
