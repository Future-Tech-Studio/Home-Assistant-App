# Step 2 — Reference repair review

## Result

The live Home Assistant configuration was inspected read-only on September 10, 2026. **No entities, groups, saved actions, or automations were changed.** Protect and Exterior repair work was skipped as requested. App version and stable rollback designation are unchanged.

The scan covered 3,308 registry entities and 1,419 reference occurrences across 330 distinct IDs in the Wall Controllers dashboard, root automation files, and generated FHT packages.

- **120 distinct IDs were unresolved** against the exported entity registry and restored-state cache. This is not a claim that 120 devices were deleted: the export is not a live state API snapshot, and YAML-only entities can be absent from both sources.
- **64 unresolved IDs appear on Wall Controllers**, including the former Maverick fan/light controls, thermostat/media references, and old kiosk-toggle helpers.
- **18 likely rename mappings** have an enabled registry match after removing a repeated area prefix. They need identity and saved-settings review before application.
- **43 generated/legacy group pairs** share matching ID suffixes or names. That alone does not prove identical membership.
- Of 116 registered light groups, 54 have definitions in the current managed light-group package; 62 do not. Other YAML includes may define some of those 62, so they are not a deletion list.

## Pantry

The current managed group is `light.fht_pantry_all_lights`, containing exactly:

- `light.pantry_light_1`
- `light.pantry_light_2`

It has 21 references in the scanned files. The older `light.pantry_all_lights` and `light.pantry_lights` remain registered, have no definitions in that managed package, and have zero references in this scan. Check external consumers and actual loaded states before removing them.

## Proposed rename review batch

Each destination below exists and is enabled in the exported registry. A matching name is not physical-device identity verification. **Nothing in this table has been applied.**

| Existing reference | Candidate replacement |
| --- | --- |
| `binary_sensor.bathroom_1_bathroom_1_toliet_presence_occupancy_2` | `binary_sensor.bathroom_1_toliet_presence_occupancy_2` |
| `binary_sensor.bathroom_2_bathroom_2_presence_1_occupancy_2` | `binary_sensor.bathroom_2_presence_1_occupancy_2` |
| `binary_sensor.bathroom_2_bathroom_2_presence_2_occupancy_2` | `binary_sensor.bathroom_2_presence_2_occupancy_2` |
| `binary_sensor.bathroom_3_bathroom_3_presence_occupancy_2` | `binary_sensor.bathroom_3_presence_occupancy_2` |
| `binary_sensor.bedroom_2_bedroom_2_closet_door_sensor` | `binary_sensor.bedroom_2_closet_door_sensor` |
| `binary_sensor.bedroom_3_bedroom_3_closet_door_sensor` | `binary_sensor.bedroom_3_closet_door_sensor` |
| `binary_sensor.closet_1_closet_1_door_sensor` | `binary_sensor.closet_1_door_sensor` |
| `binary_sensor.downstairs_hallway_downstairs_hallway_pir_occupancy` | `binary_sensor.downstairs_hallway_pir_occupancy` |
| `binary_sensor.kitchen_kitchen_presence_occupancy_2` | `binary_sensor.kitchen_presence_occupancy_2` |
| `binary_sensor.laundry_room_laundry_room_pir_occupancy` | `binary_sensor.laundry_room_pir_occupancy` |
| `binary_sensor.pantry_pantry_door_sensor_opening` | `binary_sensor.pantry_door_sensor_opening` |
| `binary_sensor.stairway_stairway_pir_1_occupancy` | `binary_sensor.stairway_pir_1_occupancy` |
| `binary_sensor.stairway_stairway_pir_2_occupancy` | `binary_sensor.stairway_pir_2_occupancy` |
| `binary_sensor.upstairs_hallway_upstairs_hallway_pir_2_occupancy` | `binary_sensor.upstairs_hallway_pir_2_occupancy` |
| `climate.upstairs_hallway_upstairs_hallway_thermostat` | `climate.upstairs_hallway_thermostat` |
| `light.upstairs_hallway_upstairs_hallway_light_1` | `light.upstairs_hallway_light_1` |
| `light.upstairs_hallway_upstairs_hallway_light_2` | `light.upstairs_hallway_light_2` |
| `switch.office_office_speaker` | `switch.office_speaker` |

## Referenced FHT groups requiring separate review

These IDs appear in generated Controls/HomeKit files but were absent from both exported registry and restored-state cache. Do not redirect them to All Lights automatically; that could change which physical lights an action controls.

- `light.fht_bedroom_2_headboard_lights`
- `light.fht_bedroom_4_fan_lights`
- `light.fht_bedroom_5_fan_lights`
- `light.fht_bedroom_6_desk_lights`
- `light.fht_bedroom_6_fan_lights`

## Before applying repairs

1. Confirm destination device identity and live state. Do not treat an offline device as a removed device.
2. Back up the affected Home Assistant files **and private FHT saved settings**, not just the stable app source.
3. Review the explicit mapping and affected locations in the detailed report.
4. Migrate private saved assignments first through supported settings paths; merely patching generated YAML would be overwritten on the next regeneration.
5. Update approved dashboard references through Home Assistant's supported editor rather than writing active `.storage` files directly.
6. Validate generated YAML and persistence. Do not activate alarms, sirens, or physical loads as an unsolicited test.

Private add-on `/data` settings were not accessible through the mounted share. Generated automation references were scanned, but an unsynchronized private saved action is outside this report. This is why no automatic repair or helper deletion was attempted.

## Reproduce and inspect

- Sanitized live snapshot: `/Volumes/addons/fht-reference-audit-20260910-v2`.
- Detailed findings and every location: [reference report](reference-audit-review-2026-09-10/report.md).
- Machine-readable review data: [report JSON](reference-audit-review-2026-09-10/report.json).
- Tools: `scripts/export_reference_audit.sh` and `scripts/audit_entity_references.py`.
- The tools write only new report artifacts, never live configuration. The auditor has no apply/delete operation.
