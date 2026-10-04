"""Build the light and switch choices shared by every action editor.

Split out of server.py; server.action_catalog_from_entities adds the room-mode
and wake-override choices around this catalog.
"""

from __future__ import annotations

import copy
import re
from typing import Any, Iterable

LIGHT_GROUP_ENTITY_PREFIX = "light.fht_"


def light_target_catalog(
    entities: list[dict[str, Any]],
    saved_actions: dict[str, list[str]] | None = None,
    generated_group_ids: set[str] | None = None,
    group_replacements: dict[str, list[str]] | None = None,
    retired_unavailable_lights: Iterable[str] | None = None,
    indicator_light_pattern: str = "",
) -> dict[str, Any]:
    """Return the light groups, lights, and switch targets action editors offer.

    Duplicate, retired, and single-light groups are folded into the choice
    that replaces them, so every editor shows the same stable list.
    ``retired_unavailable_lights`` (hidden while unavailable) and
    ``indicator_light_pattern`` (never room lighting) are site profile values;
    server.py passes this home's.
    """
    group_replacements = group_replacements or {}
    retired_unavailable = set(retired_unavailable_lights or ())
    indicator_light = re.compile(indicator_light_pattern) if indicator_light_pattern else None
    by_id = {
        str(entity.get("entity_id") or ""): copy.deepcopy(entity)
        for entity in entities
        if str(entity.get("entity_id") or "")
    }
    lights = [
        entity for entity in by_id.values()
        if entity.get("domain") == "light"
        and not (
            entity.get("entity_id") in retired_unavailable
            and entity.get("state") in {"unavailable", "unknown"}
            and not entity.get("members")
        )
        and not (
            indicator_light is not None
            and indicator_light.search(
                " ".join(str(entity.get(key) or "") for key in ("entity_id", "friendly_name", "original_name")).replace("_", " ").casefold(),
            )
        )
    ]
    retired_group_aliases: dict[str, str] = {}
    if generated_group_ids:
        # Home Assistant keeps groups the App no longer generates (for example
        # a room's old All Lights after it became Fan Lights only). Offer only
        # current groups; saved actions on a retired group show its
        # replacement in the same room.
        for entity in [entity for entity in lights if str(entity.get("entity_id") or "").startswith(LIGHT_GROUP_ENTITY_PREFIX)]:
            entity_id = str(entity["entity_id"])
            if entity_id in generated_group_ids:
                continue
            base = re.sub(r"_(?:all|fan)_lights$", "", entity_id)
            replacement = next(
                (candidate for candidate in ((group_replacements.get(entity_id) or [""])[0], f"{base}_fan_lights", f"{base}_all_lights")
                 if candidate and candidate != entity_id and candidate in by_id
                 and (candidate in generated_group_ids or not candidate.startswith(LIGHT_GROUP_ENTITY_PREFIX))),
                "",
            )
            if replacement:
                retired_group_aliases[entity_id] = replacement
            lights.remove(entity)
    light_groups = [
        entity for entity in lights
        if str(entity.get("entity_id") or "").startswith(LIGHT_GROUP_ENTITY_PREFIX)
        or bool(entity.get("members"))
        or not re.search(
            r"(?:^|[\s_-])\d+\s*$",
            " ".join(
                str(entity.get(key) or "")
                for key in ("friendly_name", "original_name", "entity_id")
            ),
        )
    ]
    group_ids = {
        str(entity.get("entity_id") or "") for entity in light_groups
    }
    individual_lights = [
        entity for entity in lights
        if str(entity.get("entity_id") or "") not in group_ids
    ]
    entity_targets = [
        entity for entity in by_id.values()
        if entity.get("domain") in {"switch", "fan"}
        and not str(entity.get("entity_id") or "").startswith("switch.fht_")
    ]

    catalog_aliases: dict[str, str] = {}
    catalog_aliases.update(retired_group_aliases)
    retired_bathroom_ids = {
        str(entity["entity_id"]) for entity in light_groups
        if str(entity["entity_id"]).endswith("_all_bathroom_lights")
    }
    for entity_id in retired_bathroom_ids:
        destination = entity_id.removesuffix("_all_bathroom_lights") + "_all_lights"
        candidates = [destination, "light.fht_" + destination.removeprefix("light.")]
        for candidate in candidates:
            if candidate in by_id and by_id[candidate].get("domain") == "light":
                catalog_aliases[entity_id] = candidate
                break
    light_groups = [entity for entity in light_groups if entity["entity_id"] not in retired_bathroom_ids]
    for entity in light_groups:
        entity_id = str(entity.get("entity_id") or "")
        if entity.get("area") or entity_id.startswith(LIGHT_GROUP_ENTITY_PREFIX):
            continue
        counterpart = by_id.get(f"{LIGHT_GROUP_ENTITY_PREFIX}{entity_id.removeprefix('light.')}")
        if counterpart is None and entity_id.endswith("_lights") and not entity_id.endswith("_all_lights"):
            counterpart = by_id.get(f"{LIGHT_GROUP_ENTITY_PREFIX}{entity_id.removeprefix('light.').removesuffix('_lights')}_all_lights")
        if not counterpart or not counterpart.get("area"):
            continue
        names = [
            re.sub(r"[^a-z0-9]+", " ", str(target.get("friendly_name") or "").casefold()).strip()
            for target in (entity, counterpart)
        ]
        if names[0] and re.sub(r" all lights$", " lights", names[0]) == re.sub(r" all lights$", " lights", names[1]):
            entity["area"] = counterpart["area"]
            entity["original_area"] = counterpart.get("original_area", counterpart["area"])
            catalog_aliases[entity_id] = str(counterpart["entity_id"])

    for preferred, canonical in by_id.items():
        if (not preferred.startswith(LIGHT_GROUP_ENTITY_PREFIX)
                or not preferred.endswith("_fan_lights")
                or canonical.get("state") in {"unavailable", "unknown"}):
            continue
        area = preferred.removeprefix(LIGHT_GROUP_ENTITY_PREFIX).removesuffix("_fan_lights")
        for retired in (f"light.{area}_fan_lights", f"light.fht_{area}_all_lights"):
            legacy = by_id.get(retired)
            if legacy and legacy.get("state") in {"unavailable", "unknown"} and not legacy.get("members"):
                catalog_aliases[retired] = preferred

    member_aliases: dict[tuple[str, ...], dict[str, Any]] = {}
    for entity in light_groups:
        members = tuple(sorted(str(member) for member in entity.get("members", []) if member))
        if not members:
            continue
        current = member_aliases.get(members)
        if current is None or (
            str(entity.get("entity_id") or "").startswith(LIGHT_GROUP_ENTITY_PREFIX)
            and not str(current.get("entity_id") or "").startswith(LIGHT_GROUP_ENTITY_PREFIX)
        ) or (
            str(entity.get("entity_id") or "").startswith(LIGHT_GROUP_ENTITY_PREFIX)
            and str(entity.get("entity_id") or "").endswith("_fan_lights")
            and str(current.get("entity_id") or "").endswith("_all_lights")
        ):
            member_aliases[members] = entity
    catalog_aliases.update({
        str(entity.get("entity_id") or ""): str(preferred["entity_id"])
        for members, preferred in member_aliases.items()
        for entity in light_groups
        if tuple(sorted(str(member) for member in entity.get("members", []) if member)) == members
        and entity is not preferred
    })
    light_groups = [
        entity for entity in light_groups
        if str(entity.get("entity_id") or "") not in catalog_aliases
    ]
    canonical_all_areas = {
        str(entity.get("area") or "").strip().casefold(): str(entity["entity_id"])
        for entity in light_groups
        if str(entity.get("entity_id") or "").startswith(LIGHT_GROUP_ENTITY_PREFIX)
        and str(entity.get("entity_id") or "").endswith("_all_lights")
        and str(entity.get("area") or "").strip()
    }
    # A room without an App All Lights group (its lights form one group)
    # folds old "All Lights" groups into that one App group instead.
    fht_groups_by_area: dict[str, list[str]] = {}
    for entity in light_groups:
        area_key = str(entity.get("area") or "").strip().casefold()
        if area_key and str(entity.get("entity_id") or "").startswith(LIGHT_GROUP_ENTITY_PREFIX) and len(entity.get("members") or []) >= 2:
            fht_groups_by_area.setdefault(area_key, []).append(str(entity["entity_id"]))
    for area_key, group_ids in fht_groups_by_area.items():
        if area_key not in canonical_all_areas and len(group_ids) == 1:
            canonical_all_areas[area_key] = group_ids[0]
    for entity in light_groups:
        normalized_area = re.sub(r"[^a-z0-9]+", " ", str(entity.get("area") or "").casefold()).strip()
        if (
            not str(entity.get("entity_id") or "").startswith(LIGHT_GROUP_ENTITY_PREFIX)
            and str(entity.get("area") or "").strip().casefold() in canonical_all_areas
            and re.sub(
                r"[^a-z0-9]+",
                " ",
                str(entity.get("friendly_name") or "").casefold(),
            ).strip()
            in {
                "lights",
                "all lights",
                f"{normalized_area} lights",
                f"{normalized_area} all lights",
            }
        ):
            catalog_aliases[str(entity["entity_id"])] = canonical_all_areas[str(entity["area"]).strip().casefold()]
    for entity in light_groups:
        entity_id = str(entity.get("entity_id") or "")
        if entity_id.startswith(LIGHT_GROUP_ENTITY_PREFIX) or entity_id in catalog_aliases:
            continue
        legacy = re.fullmatch(r"light\.([a-z0-9_]+)_all_lights", entity_id)
        if legacy and not entity.get("members") and entity.get("state") in {None, "unavailable", "unknown"}:
            candidates = [
                group_id for group_ids in fht_groups_by_area.values() for group_id in group_ids
                if group_id.startswith(f"{LIGHT_GROUP_ENTITY_PREFIX}{legacy.group(1)}_")
                and len(group_ids) == 1
            ]
            if len(candidates) == 1:
                catalog_aliases[entity_id] = candidates[0]
    light_groups = [
        entity for entity in light_groups
        if str(entity["entity_id"]) not in catalog_aliases
    ]
    def room_relative_group_name(entity: dict[str, Any]) -> str:
        area = re.sub(
            r"[^a-z0-9]+",
            " ",
            str(entity.get("area") or "").casefold(),
        ).strip()
        name = re.sub(
            r"[^a-z0-9]+",
            " ",
            str(entity.get("friendly_name") or entity.get("entity_id") or "").casefold(),
        ).strip()
        if area and name.startswith(f"{area} "):
            name = name[len(area):].strip()
        if area and name.endswith(f" {area}"):
            name = name[:-len(area)].strip()
        return name

    groups_by_name: dict[tuple[str, str], dict[str, Any]] = {}
    for entity in light_groups:
        key = (
            re.sub(
                r"[^a-z0-9]+",
                " ",
                str(entity.get("area") or "").casefold(),
            ).strip(),
            room_relative_group_name(entity),
        )
        current = groups_by_name.get(key)
        if current is None or (
            str(entity.get("entity_id") or "").startswith(LIGHT_GROUP_ENTITY_PREFIX)
            and not str(current.get("entity_id") or "").startswith(LIGHT_GROUP_ENTITY_PREFIX)
        ):
            if current is not None:
                catalog_aliases[str(current["entity_id"])] = str(entity["entity_id"])
            groups_by_name[key] = entity
        else:
            catalog_aliases[str(entity["entity_id"])] = str(current["entity_id"])
    light_groups = list(groups_by_name.values())
    physical_lights_by_area: dict[str, list[dict[str, Any]]] = {}
    for entity in lights:
        entity_id = str(entity.get("entity_id") or "")
        area_key = str(entity.get("area") or "").strip().casefold()
        if (
            area_key
            and not entity_id.startswith(LIGHT_GROUP_ENTITY_PREFIX)
            and not entity.get("members")
        ):
            physical_lights_by_area.setdefault(area_key, []).append(entity)
    single_light_aliases: dict[str, str] = {}
    for group in light_groups:
        group_id = str(group.get("entity_id") or "")
        area_key = str(group.get("area") or "").strip().casefold()
        physical_lights = physical_lights_by_area.get(area_key, [])
        area_name = re.sub(r"[^a-z0-9]+", " ", str(group.get("area") or "").casefold()).strip()
        relative_name = re.sub(r"[^a-z0-9]+", " ", str(group.get("friendly_name") or group_id).casefold()).strip()
        if area_name and relative_name.startswith(f"{area_name} "):
            relative_name = relative_name[len(area_name):].strip()
        if area_name and relative_name.endswith(f" {area_name}"):
            relative_name = relative_name[:-len(area_name)].strip()
        relative_name = re.sub(r"^fht ", "", relative_name).strip()
        if (
            len(physical_lights) == 1
            and not group_id.startswith(LIGHT_GROUP_ENTITY_PREFIX)
            and group_id != str(physical_lights[0].get("entity_id") or "")
            and relative_name in {"light", "lights", "all light", "all lights"}
        ):
            single_light_aliases[group_id] = str(physical_lights[0]["entity_id"])
    catalog_aliases.update(single_light_aliases)
    light_groups = [
        group for group in light_groups
        if str(group.get("entity_id") or "") not in single_light_aliases
    ]
    fan_groups_by_area: dict[str, set[str]] = {}
    for group in light_groups:
        group_id = str(group.get("entity_id") or "")
        if not group_id.endswith("_fan_lights"):
            continue
        area_key = str(group.get("area") or "").strip().casefold()
        members = {
            str(member)
            for member in group.get("members", [])
            if isinstance(member, str) and member
        }
        if area_key and len(members) >= 2:
            fan_groups_by_area[area_key] = fan_groups_by_area.get(area_key, set()) | members
    redundant_all_lights: dict[str, str] = {}
    for group in light_groups:
        group_id = str(group.get("entity_id") or "")
        area_key = str(group.get("area") or "").strip().casefold()
        if (
            group_id.endswith("_all_lights")
            and area_key in fan_groups_by_area
            and set(group.get("members", [])) <= fan_groups_by_area[area_key]
        ):
            fan_group_id = next(
                (
                    str(candidate.get("entity_id") or "")
                    for candidate in light_groups
                    if str(candidate.get("entity_id") or "").endswith("_fan_lights")
                    and str(candidate.get("area") or "").strip().casefold() == area_key
                ),
                "",
            )
            if fan_group_id:
                redundant_all_lights[group_id] = fan_group_id
    catalog_aliases.update(redundant_all_lights)
    light_groups = [
        group for group in light_groups
        if str(group.get("entity_id") or "") not in redundant_all_lights
    ]
    for group in list(light_groups):
        group_id = str(group.get("entity_id") or "")
        members = set(group.get("members") or [])
        if len(members) != 1:
            continue
        member_id = next(iter(members))
        member = by_id.get(member_id)
        if not member or member.get("domain") != "light" or member.get("members"):
            continue
        light_groups.remove(group)
        catalog_aliases[group_id] = member_id
        if not any(entity["entity_id"] == member_id for entity in light_groups):
            light_groups.append(member)
        individual_lights = [entity for entity in individual_lights if entity["entity_id"] != member_id]
    for group in list(light_groups):
        if group.get("state") not in {"unavailable", "unknown"} or group.get("members"):
            continue
        name = re.sub(r"[^a-z0-9]+", " ", str(group.get("friendly_name") or "").casefold()).strip()
        name = re.sub(r"^fht ", "", name)
        area = re.sub(r"[^a-z0-9]+", " ", str(group.get("area") or "").casefold()).strip()
        if area and name in {"lights", "all lights"}:
            name = f"{area} {name}"
        if not name.endswith(" lights"):
            continue
        singular = re.sub(r"(?: all)? lights$", " light", name)
        relative_singular = singular[len(area):].strip() if area and singular.startswith(f"{area} ") else singular
        candidates = [
            entity for entity in lights
            if entity.get("state") not in {"unavailable", "unknown"}
            and not entity.get("members")
            and not str(entity["entity_id"]).startswith(LIGHT_GROUP_ENTITY_PREFIX)
            and (
                re.sub(r"[^a-z0-9]+", " ", str(entity.get("friendly_name") or "").casefold()).strip() == singular
                or (area and entity.get("area") == group.get("area")
                    and room_relative_group_name(entity) == relative_singular)
            )
            and (not group.get("area") or group.get("area") == entity.get("area"))
        ]
        if len(candidates) != 1:
            continue
        member = candidates[0]
        light_groups.remove(group)
        catalog_aliases[str(group["entity_id"])] = str(member["entity_id"])
        if not any(entity["entity_id"] == member["entity_id"] for entity in light_groups):
            light_groups.append(member)
        individual_lights = [entity for entity in individual_lights if entity["entity_id"] != member["entity_id"]]
    visible_groups = {str(entity["entity_id"]): entity for entity in light_groups}
    for alias_id, preferred_id in sorted(catalog_aliases.items()):
        visited = {alias_id}
        while preferred_id in catalog_aliases and preferred_id not in visited:
            visited.add(preferred_id)
            preferred_id = catalog_aliases[preferred_id]
        if preferred_id in visible_groups:
            visible_groups[preferred_id].setdefault("action_aliases", []).append(alias_id)

    available_ids = set(by_id)
    unavailable_targets = []
    for actions in (saved_actions or {}).values():
        for action in actions:
            action_type, separator, target_id = str(action).partition(":")
            if (
                not separator
                or action_type not in {
                    "light_group",
                    "entity_target",
                    "actual_load",
                    "switch_target",
                }
                or target_id in available_ids
                or "." not in target_id
            ):
                continue
            available_ids.add(target_id)
            unavailable_targets.append(
                {
                    "entity_id": target_id,
                    "friendly_name": f"{target_id} (Unavailable)",
                    "domain": target_id.partition(".")[0],
                    "state": "unavailable",
                    "area": "",
                    "device_name": "",
                    "members": [],
                }
            )

    sorter = lambda entity: (
        str(entity.get("friendly_name") or entity.get("entity_id") or "").casefold(),
        str(entity.get("entity_id") or ""),
    )
    return {
        "light_groups": sorted(light_groups, key=sorter),
        "entity_targets": sorted(entity_targets, key=sorter),
        "individual_lights": sorted(individual_lights, key=sorter),
        "unavailable_targets": sorted(unavailable_targets, key=sorter),
    }
