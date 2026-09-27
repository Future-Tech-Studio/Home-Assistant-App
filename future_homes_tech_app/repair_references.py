#!/usr/bin/env python3
"""Repair approved saved references before any managed generators start."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys
import tempfile
import urllib.request


VERSION = "0.5.57"
RENAMES = {
    f"{domain}.{area}_{area}_{suffix}": f"{domain}.{area}_{suffix}"
    for domain, area, suffix in (
        ("binary_sensor", "bathroom_1", "toliet_presence_occupancy_2"),
        ("binary_sensor", "bathroom_2", "presence_1_occupancy_2"),
        ("binary_sensor", "bathroom_2", "presence_2_occupancy_2"),
        ("binary_sensor", "bathroom_3", "presence_occupancy_2"),
        ("binary_sensor", "bedroom_2", "closet_door_sensor"),
        ("binary_sensor", "bedroom_3", "closet_door_sensor"),
        ("binary_sensor", "closet_1", "door_sensor"),
        ("binary_sensor", "downstairs_hallway", "pir_occupancy"),
        ("binary_sensor", "kitchen", "presence_occupancy_2"),
        ("binary_sensor", "laundry_room", "pir_occupancy"),
        ("binary_sensor", "pantry", "door_sensor_opening"),
        ("binary_sensor", "stairway", "pir_1_occupancy"),
        ("binary_sensor", "stairway", "pir_2_occupancy"),
        ("binary_sensor", "upstairs_hallway", "pir_2_occupancy"),
        ("climate", "upstairs_hallway", "thermostat"),
        ("light", "upstairs_hallway", "light_1"),
        ("light", "upstairs_hallway", "light_2"),
        ("switch", "office", "speaker"),
    )
}
FILES = (
    "switch_light_group_assignments.json", "switch_control_settings.json",
    "door_light_group_assignments.json", "presence_light_group_assignments.json",
    "presence_light_group_timings.json", "presence_mode_settings.json",
    "battery_type_assignments.json", "fridge_alarm_settings.json",
    "light_schedules.json", "room_modes.json", "bedroom_modes.json",
    "bedroom_modes.house.json", "wake_routines.json", "homekit_light_groups.json",
    "homekit_climate_entities.json", "homekit_security_entities.json",
)
ATOM = re.compile(r"(?:(?:door|light_group|light|load):)?[a-z_]+\.[a-z0-9_]+(?:\|[a-z0-9_]+)?")
PROTECTED_FIELDS = {"name", "label", "title", "message", "url", "webhook", "text"}


def verified_mapping(registry, states):
    """Only replace absent old IDs with enabled, currently loaded destinations."""
    entities = {entry["entity_id"]: entry for entry in registry}
    mapping = {
        old: new for old, new in RENAMES.items()
        if old not in entities and old not in states and new in states
        and new in entities and not entities[new].get("disabled_by")
    }

    def members(entity_id, seen=frozenset()):
        if entity_id in seen or entity_id not in states:
            return None
        state = states[entity_id]
        if state.get("state") in {"unknown", "unavailable"}:
            return None
        entry = entities.get(entity_id, {})
        if entry.get("disabled_by"):
            return None
        children = state.get("attributes", {}).get("entity_id")
        if entry.get("platform") != "group":
            return frozenset([entity_id]) if children is None else None
        if not isinstance(children, list) or not children:
            return None
        result = frozenset()
        for child in children:
            if not isinstance(child, str) or not child.startswith("light."):
                return None
            leaves = members(child, seen | {entity_id})
            if not leaves:
                return None
            result |= leaves
        return result

    canonical = {}
    groups = sorted(
        (entity_id for entity_id, entry in entities.items()
         if entity_id.startswith("light.") and entry.get("platform") == "group"),
        key=lambda entity_id: (not entity_id.endswith("_all_lights"), entity_id),
    )
    for entity_id in groups:
        if not entity_id.startswith("light.fht_"):
            continue
        if entities[entity_id].get("unique_id") != entity_id.split(".", 1)[1]:
            continue
        leaves = members(entity_id)
        if leaves:
            canonical.setdefault(leaves, next(iter(leaves)) if len(leaves) == 1 else entity_id)
    for entity_id in groups:
        leaves = members(entity_id)
        destination = canonical.get(leaves)
        if destination and destination != entity_id:
            mapping[entity_id] = destination
    for entity_id in groups:
        if not entity_id.startswith("light.fht_") or not entity_id.endswith("_all_bathroom_lights"):
            continue
        if entities[entity_id].get("unique_id") != entity_id.split(".", 1)[1]:
            continue
        destination = entity_id.removesuffix("_all_bathroom_lights") + "_all_lights"
        if destination in entities and destination in states and not entities[destination].get("disabled_by"):
            mapping[entity_id] = destination
    return mapping


def replace_atom(value, mapping):
    if not ATOM.fullmatch(value):
        return value
    prefix, separator, body = value.partition(":")
    if not separator:
        body, prefix = prefix, ""
    entity_id, gesture_separator, gesture = body.partition("|")
    return (prefix + ":" if separator else "") + mapping.get(entity_id, entity_id) + (gesture_separator + gesture)


def rewrite(value, mapping, prefer_current=False, conflicts=None):
    """Preserve labels and reject collisions rather than losing an assignment."""
    if isinstance(value, str):
        return replace_atom(value, mapping)
    if isinstance(value, list):
        rewritten = [rewrite(item, mapping, prefer_current, conflicts) for item in value]
        if all(isinstance(item, str) and ATOM.fullmatch(item) for item in rewritten):
            return list(dict.fromkeys(rewritten))
        return rewritten
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            new_key = replace_atom(key, mapping)
            if prefer_current and new_key != key and new_key in value:
                if item != value[new_key] and conflicts is not None:
                    conflicts.append({"archived_key": key, "retained_key": new_key})
                continue
            new_item = item if key in PROTECTED_FIELDS else rewrite(item, mapping, prefer_current, conflicts)
            if new_key in result and result[new_key] != new_item:
                raise ValueError(f"Conflicting saved assignments for {new_key}")
            result[new_key] = new_item
        return result
    return value


def atomic_write(path, content):
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".fht-repair-")
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def migrate(data, registry, states, config=None, prefer_current=False):
    """Back up a complete batch before writes; resume safely after interruption."""
    backup = data / ("reference-repair-" + VERSION)
    manifest_path = backup / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        if manifest["status"] == "complete":
            return manifest
        for name in manifest["files"]:
            atomic_write(data / name, (backup / name).read_bytes())
        manifest["status"] = "rolled-back"
        atomic_write(manifest_path, json.dumps(manifest, indent=2).encode())
        raise RuntimeError("Interrupted repair restored; review backup before retrying")
    mapping = verified_mapping(registry, states)
    changes = {}
    archived_conflicts = {}
    for name in FILES:
        path = data / name
        if not path.exists():
            continue
        original = path.read_bytes()
        payload = json.loads(original)
        conflicts = []
        updated = rewrite(payload, mapping, prefer_current, conflicts)
        if conflicts:
            archived_conflicts[name] = conflicts
        if payload != updated:
            changes[name] = (original, (json.dumps(updated, indent=2) + "\n").encode())
    backup.mkdir(mode=0o700, parents=True, exist_ok=True)
    if config is not None:
        packages = backup / "packages"
        packages.mkdir(mode=0o700, exist_ok=True)
        for path in (config / "packages").glob("future_homes_tech*.yaml"):
            atomic_write(packages / path.name, path.read_bytes())
    for name, (original, updated) in changes.items():
        atomic_write(backup / name, original)
    manifest = {"version": VERSION, "status": "pending", "files": list(changes),
                "mapping": mapping, "unverified_renames": sorted(set(RENAMES) - set(mapping)),
                "registry_entities_deleted": 0, "archived_conflicts": archived_conflicts}
    atomic_write(manifest_path, json.dumps(manifest, indent=2).encode())
    try:
        for name, (original, updated) in changes.items():
            atomic_write(data / name, updated)
        manifest["status"] = "complete"
        atomic_write(manifest_path, json.dumps(manifest, indent=2).encode())
    except Exception:
        for name, (original, updated) in changes.items():
            atomic_write(data / name, original)
        raise
    return manifest


def main():
    data = Path("/data")
    completed = data / ("reference-repair-" + VERSION) / "manifest.json"
    if completed.exists():
        manifest = json.loads(completed.read_text())
        if manifest.get("status") == "complete":
            print("Reference repair already completed")
            return
        migrate(data, [], {})
    try:
        token = os.environ.get("SUPERVISOR_TOKEN", "")
        if not token:
            raise RuntimeError("Home Assistant authorization unavailable")
        request = urllib.request.Request("http://supervisor/core/api/states", headers={"Authorization": "Bearer " + token})
        with urllib.request.urlopen(request, timeout=15) as response:
            raw_states = json.load(response)
        if not isinstance(raw_states, list) or not raw_states:
            raise RuntimeError("Live state inventory unavailable")
        registry = json.loads(Path("/homeassistant/.storage/core.entity_registry").read_text())["data"]["entities"]
        states = {entry["entity_id"]: entry for entry in raw_states}
        mapping = verified_mapping(registry, states)
        for name in FILES:
            path = data / name
            if path.exists():
                rewrite(json.loads(path.read_text()), mapping, prefer_current=True)
    except Exception as error:
        print(f"Reference repair deferred ({type(error).__name__}); no settings changed")
        return 2
    manifest = migrate(data, registry, states, Path("/homeassistant"), prefer_current=True)
    print(f"Reference repair: {len(manifest['files'])} saved files updated; "
          f"{len(manifest['unverified_renames'])} rename candidates left unchanged. Backup: {completed.parent}")
    for name, conflicts in manifest.get("archived_conflicts", {}).items():
        print(f"Reference repair: kept current settings; archived {len(conflicts)} older conflicts in {name}")


if __name__ == "__main__":
    sys.exit(main())
