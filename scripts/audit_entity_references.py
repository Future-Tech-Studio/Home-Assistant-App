#!/usr/bin/env python3
"""Create a review-only entity-reference report from a sanitized HA export."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import re


def normalized_name(value):
    return re.sub(r"[^a-z0-9]+", "_", re.sub(r"^fht\s*[-_:]?\s*", "", str(value).casefold())).strip("_")


SERVICE_NAMES = {"turn_on", "turn_off", "toggle", "press", "trigger", "set_hvac_mode", "set_temperature", "set_value", "select_option", "set_datetime", "start", "cancel", "finished"}


def group_definitions(lines):
    definitions = {}
    unique_id = None
    in_group = False
    for line in lines:
        text = line.strip()
        if text.startswith("- platform:"):
            in_group = text.split(":", 1)[1].strip().strip("\"'") == "group"
            unique_id = None
        elif in_group and text.startswith("unique_id:"):
            unique_id = text.split(":", 1)[1].strip().strip("\"'")
            definitions[unique_id] = []
        elif in_group and unique_id and re.fullmatch(r"- light\.[a-z0-9_]+", text):
            definitions[unique_id].append(text[2:])
    return definitions


def audit(registry, restored, references, devices=(), definitions=None):
    entities = {item["entity_id"]: item for item in registry}
    historical = {item["entity_id"]: item for item in restored}
    device_areas = {item["id"]: item.get("area_id") for item in devices}
    uses = defaultdict(list)
    for reference in references:
        path = reference["path"]
        entity_id = reference["entity_id"]
        if entity_id not in entities and entity_id.partition(".")[2] in SERVICE_NAMES:
            continue
        if reference["kind"] == "json" and path.rsplit("/", 1)[-1] in {"service", "action"}:
            continue
        uses[reference["entity_id"]].append(reference)
    issues = []
    for entity_id, locations in sorted(uses.items()):
        entity = entities.get(entity_id)
        if entity and not entity.get("disabled_by"):
            continue
        status = "disabled" if entity else "historical_only" if entity_id in historical else "dynamic_prefix" if entity_id.endswith("_") else "unresolved"
        candidates = []
        domain, separator, object_id = entity_id.partition(".")
        replacement = f"{domain}.fht_{object_id}"
        target = entities.get(replacement)
        if separator and not object_id.startswith("fht_") and target and not target.get("disabled_by"):
            candidates.append({"entity_id":replacement, "evidence":"Matching generated FHT ID; membership and behavior need review, not an automatic replacement."})
        words = object_id.split("_")
        for length in range(1, len(words) // 2 + 1):
            if words[:length] != words[length:2 * length]:
                continue
            replacement = domain + "." + "_".join(words[length:])
            target = entities.get(replacement)
            if target and not target.get("disabled_by"):
                candidates.append({"entity_id":replacement, "evidence":"Removing a duplicated area prefix matches an enabled registry entity. Confirm physical device identity and migrate private saved settings before regenerating YAML."})
        issues.append({"entity_id":entity_id, "status":status, "references":locations, "candidates":candidates})
    groups = [item for item in registry if item.get("platform") == "group" and item["entity_id"].startswith("light.")]
    duplicate_candidates = []
    seen_pairs = set()
    for item in groups:
        entity_id = item["entity_id"]
        if entity_id.startswith("light.fht_"):
            legacy_id = "light." + entity_id[len("light.fht_"):]
            legacy = entities.get(legacy_id)
            if legacy and legacy.get("platform") == "group":
                pair = tuple(sorted((legacy_id, entity_id)))
                seen_pairs.add(pair)
                duplicate_candidates.append({"entities":list(pair), "evidence":"Generated and legacy group IDs share the same suffix; member sets have not been compared.", "reference_counts":{target:len(uses.get(target, [])) for target in pair}})
    names = defaultdict(list)
    for item in groups:
        area = item.get("area_id") or device_areas.get(item.get("device_id"))
        name = item.get("name") or item.get("original_name")
        if area and name:
            names[(area, normalized_name(name))].append(item["entity_id"])
    for matches in names.values():
        if len(matches) > 1 and tuple(sorted(matches)) not in seen_pairs:
            duplicate_candidates.append({"entities":sorted(matches), "evidence":"Same normalized group name and registry area; member sets have not been compared.", "reference_counts":{target:len(uses.get(target, [])) for target in matches}})
    definition_review = []
    if definitions is not None:
        for item in groups:
            definition_review.append({"entity_id":item["entity_id"], "unique_id":item.get("unique_id"), "in_managed_package":item.get("unique_id") in definitions, "members":definitions.get(item.get("unique_id")), "reference_count":len(uses.get(item["entity_id"], []))})
    return {
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "mode":"dry-run; no configuration changes",
        "scope":{
            "registry_entities":len(entities), "restored_entities":len(historical),
            "reference_occurrences":sum(map(len, uses.values())), "distinct_referenced_ids":len(uses),
            "sources":dict(sorted(Counter(ref["source"] for rows in uses.values() for ref in rows).items())),
        },
        "limitations":[
            "Registry and restored-state exports are not a live state API snapshot. Unresolved does not prove deleted: YAML-only or non-restoring entities may be absent from both exports.",
            "Historical-only entries are not proof an entity currently exists. Disabled registry entities are explicitly disabled, not merely offline.",
            "Group name or ID overlap alone never authorizes merging. Compare direct and expanded members, availability, and assigned automations first.",
            "Private add-on /data settings were not exported. Generated FHT YAML is covered, but unsynchronized saved actions may still require a runtime audit.",
            "Only listed dashboard storage files, root automations/scripts/scenes, and FHT package files were scanned. External includes and dynamically constructed entity IDs need manual review.",
        ],
        "issue_counts":dict(Counter(item["status"] for item in issues)),
        "issues":issues, "group_overlap_candidates":duplicate_candidates,
        "managed_group_definition_review":definition_review,
    }


def markdown(report):
    lines = ["# Entity and group reference audit", "", "**Read-only report. No entities, assignments, or automations were changed.**", "", "## Coverage", ""]
    scope = report["scope"]
    lines += [f"- Registry entities: {scope['registry_entities']}", f"- Reference occurrences: {scope['reference_occurrences']}", f"- Distinct referenced IDs: {scope['distinct_referenced_ids']}"]
    lines += [f"- {kind}: {count}" for kind, count in report["issue_counts"].items()]
    lines += [f"- Potential legacy/FHT group overlaps: {len(report['group_overlap_candidates'])}", "", "## Limits and safeguards", ""]
    lines += ["- " + value for value in report["limitations"]]
    lines += ["", "## Reference issues", ""]
    for item in report["issues"]:
        lines += [f"### `{item['entity_id']}` — {item['status']}"]
        lines += [f"- `{ref['source']}` → `{ref['path']}`" for ref in item["references"]]
        lines += [f"- Review candidate: `{candidate['entity_id']}`. {candidate['evidence']}" for candidate in item["candidates"]]
        lines += [""]
    lines += ["## Group overlap review", ""]
    for item in report["group_overlap_candidates"]:
        lines += ["- " + " / ".join(f"`{value}` ({item['reference_counts'][value]} references)" for value in item["entities"]) + ". " + item["evidence"]]
    lines += ["", "## Managed group definitions", "", "Absence from this one package is not proof of deletion; external YAML includes still need review.", ""]
    for item in report["managed_group_definition_review"]:
        lines += [f"- `{item['entity_id']}`: " + (f"defined here, {len(item['members'])} direct members" if item["in_managed_package"] else "not defined in the current managed light-group package") + f"; {item['reference_count']} references."]
    lines += ["", "## Safe migration sequence", "", "1. Confirm the currently loaded entity IDs in Home Assistant; never delete or replace an entity solely because it is offline.", "2. Compare proposed old/new groups' member sets and behavior. Retain any intentionally distinct groups.", "3. Review a specific old-ID → new-ID mapping and its affected reference locations with the homeowner.", "4. Back up the affected live files and private saved settings separately from the stable app archive.", "5. Apply only approved references through supported dashboard/settings editors; do not write active `.storage` files directly.", "6. Validate saved actions and generated YAML, then verify controls without unexpectedly activating lights, sirens, or armed modes."]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    registry = json.loads((args.snapshot / "registry.json").read_text())["entities"]
    restored = json.loads((args.snapshot / "restored_states.json").read_text())
    devices = json.loads((args.snapshot / "devices.json").read_text())["devices"]
    references = [json.loads(line) for line in (args.snapshot / "references.jsonl").read_text().splitlines() if line]
    definition_path = args.snapshot / "group_definition_lines.json"
    definitions = group_definitions(json.loads(definition_path.read_text())) if definition_path.exists() else None
    report = audit(registry, restored, references, devices, definitions)
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    (args.output / "report.md").write_text(markdown(report))
    print(json.dumps({"scope":report["scope"], "issue_counts":report["issue_counts"], "group_overlap_candidates":len(report["group_overlap_candidates"])}))


if __name__ == "__main__":
    main()
