#!/usr/bin/env python3
"""Generate Future Homes Tech light groups from Home Assistant registries."""

from __future__ import annotations

from collections import OrderedDict
import importlib.util
import json
import os
from pathlib import Path
import re
import tempfile
import sys
from typing import Any

_site_spec = importlib.util.spec_from_file_location("fht_site", Path(__file__).with_name("fht_site.py"))
SITE = importlib.util.module_from_spec(_site_spec)
_site_spec.loader.exec_module(SITE)
# Switch indicator lights are never room lighting; the pattern that spots them
# is a site profile value (docs/SITE_PROFILE.md) shared with the action catalog.
INDICATOR_LIGHT_PATTERN = str(SITE.load_site_profile().get("catalog.indicator_light_pattern"))

DEFAULT_CONFIG_DIRECTORY = Path("/homeassistant")
OUTPUT_FILENAME = "future_homes_tech_light_groups.yaml"
ENTITY_NAME_PREFIX = "FHT - "
UNIQUE_ID_PREFIX = "fht_"
EXCLUDE_TERMS = (
    "scene",
    "moes",
    "firmware",
    "identify",
    "update",
    "version",
    "battery",
    "voltage",
    "current",
    "power",
    "energy",
    "illuminance",
    "temperature",
    "humidity",
    "diagnostic",
    "group",
    "all_lights",
    "all lights",
    "all_light",
    "all light",
    "candle_warmer",
    "candle warmer",
    "presence_pro",
    "presence pro",
    "static_presence_led",
    "static presence led",
)


def _load_storage(path: Path, key: str) -> list[dict[str, Any]]:
    """Load one list from a Home Assistant storage registry."""
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as registry_file:
        payload = json.load(registry_file)
    values = payload.get("data", {}).get(key, [])
    return values if isinstance(values, list) else []


def _slugify(value: str) -> str:
    """Create a stable Home Assistant-style slug."""
    value = re.sub(r"[^a-z0-9]+", "_", value.casefold().strip())
    return re.sub(r"_+", "_", value).strip("_")


def _labelize(value: str) -> str:
    """Create a readable label from a descriptor slug."""
    words = []
    for word in value.replace("_", " ").split():
        if word.isdigit():
            words.append(f"({word})")
        elif re.fullmatch(r"\d+g", word):
            words.append(word.upper())
        elif word == "rgb":
            words.append("RGB")
        elif word == "led":
            words.append("LED")
        else:
            words.append(word.capitalize())
    return " ".join(words)


def _strip_area_prefixes(object_id: str, area_slug: str) -> str:
    """Remove repeated area prefixes from an entity object ID."""
    value = object_id
    while value.startswith(f"{area_slug}_"):
        value = value[len(area_slug) + 1 :]
    return value


def _grouping_object_id(
    entity_id: str,
    friendly_name: str,
    area_label: str,
) -> str:
    """Prefer the current Home Assistant display name for grouping."""
    friendly_slug = _slugify(friendly_name)
    area_slug = _slugify(area_label)
    if friendly_slug:
        stripped = _strip_area_prefixes(friendly_slug, area_slug)
        if "light" in stripped.split("_"):
            return f"{area_slug}_{stripped}"
    return entity_id.removeprefix("light.").casefold()


def _is_excluded(
    entity_id: str,
    friendly_name: str,
    platform: str,
) -> bool:
    """Exclude diagnostics, helpers, and existing generated groups."""
    if platform == "group":
        return True
    object_id = entity_id.removeprefix("light.").casefold()
    friendly_lower = friendly_name.casefold()
    combined = " ".join(
        (
            object_id,
            object_id.replace("_", " "),
            friendly_lower,
            friendly_lower.replace("_", " "),
        )
    )
    if INDICATOR_LIGHT_PATTERN and re.search(INDICATOR_LIGHT_PATTERN, combined):
        return True
    return any(
        term in object_id
        or term in friendly_lower
        or term.replace("_", " ") in combined
        for term in EXCLUDE_TERMS
    )


def _light_descriptions(
    object_id: str,
    area_slug: str,
) -> list[str]:
    """Return full and parent fixture descriptors for one light."""
    tokens = _strip_area_prefixes(object_id, area_slug).split("_")
    if "light" not in tokens:
        return []

    light_index = tokens.index("light")
    before = tokens[:light_index]
    after = tokens[light_index + 1 :]
    if not before:
        return ["lights"]

    if not after or (len(after) == 1 and after[0].isdigit()):
        full_base = before
    else:
        full_base = before + after

    descriptions = []
    full_slug = _slugify("_".join(full_base))
    if full_slug:
        descriptions.append(full_slug)
    if len(before) > 1 and before[-1] in {"left", "right"}:
        directional_parent = _slugify("_".join(before[:-1]))
        if directional_parent and directional_parent not in descriptions:
            descriptions.append(directional_parent)
    if len(before) and len(after) == 1 and after[0] in {"left", "right"}:
        directional_parent = _slugify("_".join(before))
        if directional_parent and directional_parent not in descriptions:
            descriptions.append(directional_parent)
    if len(before) > 1:
        # "bathroom her vanity" joins "bathroom his vanity" as "bathroom
        # vanity": drop the qualifier, keep the location words before it.
        parent_slug = _slugify("_".join(before[:-2] + before[-1:]))
        if parent_slug and parent_slug not in descriptions:
            descriptions.append(parent_slug)

    blocked = {
        "all",
        "all_light",
        "all_lights",
        "group",
        "light_group",
        "lights_group",
        "candle_warmer",
    }
    return [
        description
        for description in descriptions
        if description not in blocked
    ]


def _collect_areas(
    config_directory: Path,
) -> OrderedDict[str, dict[str, Any]]:
    """Collect physical lights into deterministic area groups."""
    storage_directory = config_directory / ".storage"
    areas_raw = _load_storage(
        storage_directory / "core.area_registry",
        "areas",
    )
    entities_raw = _load_storage(
        storage_directory / "core.entity_registry",
        "entities",
    )
    devices_raw = _load_storage(
        storage_directory / "core.device_registry",
        "devices",
    )

    area_by_id = {
        str(area.get("area_id") or area.get("id")): str(area["name"])
        for area in areas_raw
        if (area.get("area_id") or area.get("id")) and area.get("name")
    }
    device_area_by_id = {
        str(device["id"]): str(device["area_id"])
        for device in devices_raw
        if device.get("id") and device.get("area_id")
    }
    device_name_by_id = {
        str(device["id"]): str(
            device.get("name_by_user") or device.get("name") or ""
        )
        for device in devices_raw
        if device.get("id")
    }
    areas: OrderedDict[str, dict[str, Any]] = OrderedDict()

    for entity in entities_raw:
        entity_id = str(entity.get("entity_id") or "")
        if not entity_id.startswith("light."):
            continue

        platform = str(entity.get("platform") or "")
        area_id = entity.get("area_id")
        if not area_id:
            area_id = device_area_by_id.get(
                str(entity.get("device_id") or "")
            )
        area_label = area_by_id.get(str(area_id or ""))
        if not area_label:
            continue

        area_slug = _slugify(area_label)
        if area_slug not in areas:
            areas[area_slug] = {
                "label": area_label,
                "all": set(),
                "area_lights": set(),
                "groups": OrderedDict(),
            }

        if platform == "group":
            continue
        areas[area_slug]["area_lights"].add(entity_id)
        if entity.get("disabled_by"):
            continue

        friendly_name = str(
            entity.get("name")
            or device_name_by_id.get(str(entity.get("device_id") or ""))
            or entity.get("original_name")
            or entity_id.removeprefix("light.").replace("_", " ").title()
        )
        if _is_excluded(entity_id, friendly_name, platform):
            continue

        grouping_object_id = _grouping_object_id(
            entity_id,
            friendly_name,
            area_label,
        )
        descriptions = _light_descriptions(
            grouping_object_id,
            area_slug,
        )
        areas[area_slug]["all"].add(entity_id)
        location_tokens = _strip_area_prefixes(grouping_object_id, area_slug).split("_")
        if (
            "bathroom" not in area_slug.split("_")
            and location_tokens[0] == "bathroom"
            and "light" in location_tokens[2:]
        ):
            # A bedroom's own bathroom (Master Bedroom Bathroom Shower Light)
            # gets one group for every bathroom light, toilet included.
            areas[area_slug]["groups"].setdefault(
                "bathroom_lights",
                {"label": "All Bathroom Lights", "entities": set()},
            )["entities"].add(entity_id)

        for description in descriptions:
            if description == "lights":
                suffix = "lights"
                label = "Lights"
            else:
                suffix = f"{description}_lights"
                label = f"{_labelize(description)} Lights"
            if suffix in {"all_lights", "light_lights", "lights_lights"}:
                continue
            group = areas[area_slug]["groups"].setdefault(
                suffix,
                {"label": label, "entities": set()},
            )
            group["entities"].add(entity_id)

    return areas


def _append_group(
    lines: list[str],
    customizations: list[tuple[str, str, str]],
    area_name: str,
    name: str,
    unique_id: str,
    entities: set[str],
) -> bool:
    """Append one YAML light group when it has members."""
    if not entities:
        return False
    lines.extend(
        [
            "  - platform: group\n",
            f"    name: {json.dumps(ENTITY_NAME_PREFIX + name)}\n",
            f"    unique_id: {UNIQUE_ID_PREFIX}{unique_id}\n",
            "    entities:\n",
        ]
    )
    lines.extend(
        f"      - {entity_id}\n"
        for entity_id in sorted(entities)
    )
    lines.append("\n")
    customizations.append(
        (f"light.{UNIQUE_ID_PREFIX}{unique_id}", name, area_name)
    )
    return True


def render_light_groups(config_directory: Path) -> tuple[str, int]:
    """Render the managed light-group package and group count."""
    areas = _collect_areas(config_directory)
    lines = ["light:\n"]
    customizations: list[tuple[str, str | None, str]] = []
    replacements: list[tuple[str, str]] = []
    standalone_lights: list[str] = []
    count = 0

    for area_slug in sorted(areas):
        area = areas[area_slug]
        area_label = str(area["label"])
        def add_group(name: str, suffix: str, entities: set[str],
                      area_slug: str = area_slug, area_label: str = area_label) -> int:
            return _append_group(lines, customizations, area_label, name, f"{area_slug}_{suffix}", entities)

        for entity_id in sorted(area["area_lights"]):
            customizations.append((entity_id, None, area_label))
        if len(area["all"]) == 1:
            standalone_lights.extend(area["all"])
            continue
        fan_group = area["groups"].get("fan_lights")
        only_fan_lights = fan_group is not None and fan_group["entities"] == area["all"]
        plain_group = area["groups"].get("lights")
        # Dining Room Light 1 to 5 are simply the Dining Room Lights; the group
        # keeps its All Lights ID so saved actions and automations still work.
        only_plain_lights = plain_group is not None and plain_group["entities"] == area["all"]
        # All Lights covers the whole room; when one group already is the
        # whole room (for example only fan bulbs), that group is used instead.
        count += add_group(
            f"{area_label} {'Fan Lights' if only_fan_lights else 'Lights' if only_plain_lights else 'All Lights'}",
            "fan_lights" if only_fan_lights else "all_lights",
            area["all"],
        )
        generated_suffixes = set()
        # Lights in no group but the whole room's (Porch Light, a lamp) get
        # their own Lighting control; a Fan Lights or Lights room has none.
        covered = set(area["all"]) if only_fan_lights or only_plain_lights else set()
        for suffix in sorted(area["groups"], key=lambda item: (-len(item), item)):
            group = area["groups"][suffix]
            if group["entities"] == area["all"]:
                continue
            duplicate = next(
                (other for other in generated_suffixes if area["groups"][other]["entities"] == group["entities"]),
                None,
            )
            if duplicate:
                # Same lights as a more specific group: keep only that one.
                replacements.append((
                    f"light.{UNIQUE_ID_PREFIX}{area_slug}_{suffix}",
                    f"light.{UNIQUE_ID_PREFIX}{area_slug}_{duplicate}",
                ))
                continue
            if len(group["entities"]) < 2:
                # A single light is offered as itself, not as a group.
                replacements.append((
                    f"light.{UNIQUE_ID_PREFIX}{area_slug}_{suffix}",
                    ", ".join(sorted(group["entities"])),
                ))
                continue
            label = group["label"]
            count += add_group(
                f"{area_label} {label}",
                suffix,
                group["entities"],
            )
            generated_suffixes.add(suffix)
            if suffix != "bathroom_lights":
                # All Bathroom Lights is a room part, not a fixture: the
                # Shower Light in it still gets its own control.
                covered |= group["entities"]
        standalone_lights.extend(sorted(area["all"] - covered))
        # Earlier releases named combined groups by their last word only
        # (Vanity Lights for Bathroom Vanity Lights); point those IDs here.
        legacy_targets: dict[str, list[str]] = {}
        for suffix in generated_suffixes:
            words = suffix.removesuffix("_lights").split("_")
            if len(words) > 1:
                legacy_targets.setdefault(f"{words[-1]}_lights", []).append(suffix)
        for legacy, targets in sorted(legacy_targets.items()):
            # The most general group (fewest words) is the old combined one.
            fewest = min(len(target.split("_")) for target in targets)
            general = [target for target in targets if len(target.split("_")) == fewest]
            if legacy not in generated_suffixes and legacy not in area["groups"] and len(general) == 1:
                replacements.append((
                    f"light.{UNIQUE_ID_PREFIX}{area_slug}_{legacy}",
                    f"light.{UNIQUE_ID_PREFIX}{area_slug}_{general[0]}",
                ))

    if count == 0:
        lines.append("  []\n")

    header = [
        "# Managed by Future Homes Tech App. Changes may be overwritten.\n",
        "# Generated from Home Assistant area, device, and entity registries.\n",
        *(f"# fht_replaced_group: {retired} -> {replacement}\n" for retired, replacement in replacements),
        *(f"# fht_standalone_light: {entity_id}\n" for entity_id in standalone_lights),
    ]
    if customizations:
        header.extend(
            [
                "homeassistant:\n",
                "  customize:\n",
            ]
        )
        for entity_id, friendly_name, area_name in customizations:
            header.append(f"    {entity_id}:\n")
            if friendly_name is not None:
                header.append(
                    "      friendly_name: "
                    f"{json.dumps(friendly_name)}\n"
                )
            header.append(
                f"      fht_area: {json.dumps(area_name)}\n"
            )
        header.append("\n")
    return "".join(header + lines), count


def generate_light_groups(
    config_directory: Path,
    output_path: Path | None = None,
) -> tuple[int, bool]:
    """Atomically write generated groups when content changed."""
    if output_path is None:
        output_path = (
            config_directory
            / "packages"
            / OUTPUT_FILENAME
        )
    content, count = render_light_groups(config_directory)
    previous = (
        output_path.read_text(encoding="utf-8")
        if output_path.exists()
        else None
    )
    if previous == content:
        return count, False

    output_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=output_path.parent,
        prefix=f".{output_path.name}.",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output_file:
            output_file.write(content)
            output_file.flush()
            os.fsync(output_file.fileno())
        os.chmod(temporary_path, 0o644)
        os.replace(temporary_path, output_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return count, True


def light_groups_status(config_directory: Path) -> tuple[int, bool]:
    """Report whether managed output differs without changing files."""
    output_path = config_directory / "packages" / OUTPUT_FILENAME
    content, count = render_light_groups(config_directory)
    current = (
        output_path.read_text(encoding="utf-8")
        if output_path.exists()
        else None
    )
    return count, current != content


def main() -> int:
    """Generate groups for the configured Home Assistant directory."""
    config_directory = Path(
        os.environ.get(
            "HOMEASSISTANT_CONFIG_DIR",
            DEFAULT_CONFIG_DIRECTORY,
        )
    )
    if "--check" in sys.argv[1:]:
        count, changed = light_groups_status(config_directory)
    else:
        count, changed = generate_light_groups(config_directory)
    print(f"{'changed' if changed else 'unchanged'} {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
