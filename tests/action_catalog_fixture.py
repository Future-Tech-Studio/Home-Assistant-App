"""Light-group fixture matching renamed rooms with area-less legacy helpers."""

import importlib.util
import json
from pathlib import Path


def bedroom_lights():
    entities = []
    for suffix, label, members in (
        ("all_lights", "All Lights", ["closet_light_1", "closet_light_2", "fan_light_1", "fan_light_2"]),
        ("closet_lights", "Closet Lights", ["closet_light_1", "closet_light_2"]),
        ("fan_lights", "Fan Lights", ["fan_light_1", "fan_light_2"]),
    ):
        entities.append({
            "entity_id": f"light.fht_bedroom_2_{suffix}", "domain": "light",
            "friendly_name": f"Bedroom 2 {label}", "area": "Bedroom 2",
            "integration": "group", "members": [f"light.bedroom_2_{member}" for member in members],
        })
        if suffix != "closet_lights":
            entities.append({
                "entity_id": f"light.bedroom_2_{suffix}", "domain": "light",
                "friendly_name": f"Bedroom 2 {label}", "area": None,
                "integration": "group", "members": [f"light.bedroom_2_bedroom_2_{member}" for member in members],
            })
    entities.append({
        "entity_id": "light.bedroom_2_headboard_lights", "domain": "light",
        "friendly_name": "Bedroom 2 Headboard Light", "area": None, "integration": "group", "members": [],
    })
    for suffix in ("closet_light_1", "closet_light_2", "fan_light_1", "fan_light_2"):
        entities.append({
            "entity_id": f"light.bedroom_2_{suffix}", "domain": "light",
            "friendly_name": f"Bedroom 2 {suffix.replace('_', ' ').title()}", "area": "Bedroom 2",
        })
    return entities


if __name__ == "__main__":
    spec = importlib.util.spec_from_file_location("fixture_server", Path(__file__).resolve().parents[1] / "future_homes_tech_app/server.py")
    server = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(server)
    entities = bedroom_lights()
    entities.extend([
        {"entity_id": "light.fht_dining_room_all_lights", "domain": "light", "friendly_name": "Dining Room All Lights", "area": "Dining Room", "members": ["light.dining_room_light_1", "light.dining_room_light_2"]},
        {"entity_id": "light.dining_room_lights", "domain": "light", "friendly_name": "Dining Room Lights", "area": None, "members": []},
    ])
    server.apply_room_aliases(entities, {"Bedroom 2": "Bailey’s Bedoom"})
    print(json.dumps(server.action_catalog_from_entities(entities)))
