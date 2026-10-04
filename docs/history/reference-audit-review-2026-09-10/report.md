# Entity and group reference audit

**Read-only report. No entities, assignments, or automations were changed.**

## Coverage

- Registry entities: 3308
- Reference occurrences: 1419
- Distinct referenced IDs: 330
- unresolved: 120
- dynamic_prefix: 1
- Potential legacy/FHT group overlaps: 43

## Limits and safeguards

- Registry and restored-state exports are not a live state API snapshot. Unresolved does not prove deleted: YAML-only or non-restoring entities may be absent from both exports.
- Historical-only entries are not proof an entity currently exists. Disabled registry entities are explicitly disabled, not merely offline.
- Group name or ID overlap alone never authorizes merging. Compare direct and expanded members, availability, and assigned automations first.
- Private add-on /data settings were not exported. Generated FHT YAML is covered, but unsynchronized saved actions may still require a runtime audit.
- Only listed dashboard storage files, root automations/scripts/scenes, and FHT package files were scanned. External includes and dynamically constructed entity IDs need manual review.

## Reference issues

### `binary_sensor.bathroom_1_bathroom_1_toliet_presence_occupancy_2` — unresolved
- `packages/future_homes_tech_presence_automations.yaml` → `line:4`
- `packages/future_homes_tech_presence_automations.yaml` → `line:8`
- `packages/future_homes_tech_presence_automations.yaml` → `line:12`
- `packages/future_homes_tech_presence_automations.yaml` → `line:29`
- `packages/future_homes_tech_presence_automations.yaml` → `line:39`
- `packages/future_homes_tech_presence_automations.yaml` → `line:52`
- Review candidate: `binary_sensor.bathroom_1_toliet_presence_occupancy_2`. Removing a duplicated area prefix matches an enabled registry entity. Confirm physical device identity and migrate private saved settings before regenerating YAML.

### `binary_sensor.bathroom_2_bathroom_2_presence_1_occupancy_2` — unresolved
- `packages/future_homes_tech_presence_automations.yaml` → `line:122`
- `packages/future_homes_tech_presence_automations.yaml` → `line:126`
- `packages/future_homes_tech_presence_automations.yaml` → `line:130`
- `packages/future_homes_tech_presence_automations.yaml` → `line:147`
- `packages/future_homes_tech_presence_automations.yaml` → `line:157`
- `packages/future_homes_tech_presence_automations.yaml` → `line:170`
- Review candidate: `binary_sensor.bathroom_2_presence_1_occupancy_2`. Removing a duplicated area prefix matches an enabled registry entity. Confirm physical device identity and migrate private saved settings before regenerating YAML.

### `binary_sensor.bathroom_2_bathroom_2_presence_1_occupancy_2_2` — unresolved
- `packages/future_homes_tech_presence_automations.yaml` → `line:181`
- `packages/future_homes_tech_presence_automations.yaml` → `line:185`
- `packages/future_homes_tech_presence_automations.yaml` → `line:189`
- `packages/future_homes_tech_presence_automations.yaml` → `line:206`
- `packages/future_homes_tech_presence_automations.yaml` → `line:216`
- `packages/future_homes_tech_presence_automations.yaml` → `line:229`

### `binary_sensor.bathroom_2_bathroom_2_presence_2_occupancy_2` — unresolved
- `packages/future_homes_tech_presence_automations.yaml` → `line:240`
- `packages/future_homes_tech_presence_automations.yaml` → `line:244`
- `packages/future_homes_tech_presence_automations.yaml` → `line:248`
- `packages/future_homes_tech_presence_automations.yaml` → `line:265`
- `packages/future_homes_tech_presence_automations.yaml` → `line:275`
- `packages/future_homes_tech_presence_automations.yaml` → `line:288`
- Review candidate: `binary_sensor.bathroom_2_presence_2_occupancy_2`. Removing a duplicated area prefix matches an enabled registry entity. Confirm physical device identity and migrate private saved settings before regenerating YAML.

### `binary_sensor.bathroom_2_bathroom_2_presence_2_occupancy_2_2` — unresolved
- `packages/future_homes_tech_presence_automations.yaml` → `line:299`
- `packages/future_homes_tech_presence_automations.yaml` → `line:303`
- `packages/future_homes_tech_presence_automations.yaml` → `line:307`
- `packages/future_homes_tech_presence_automations.yaml` → `line:324`
- `packages/future_homes_tech_presence_automations.yaml` → `line:334`
- `packages/future_homes_tech_presence_automations.yaml` → `line:347`

### `binary_sensor.bathroom_3_bathroom_3_presence_occupancy_2` — unresolved
- `packages/future_homes_tech_presence_automations.yaml` → `line:476`
- `packages/future_homes_tech_presence_automations.yaml` → `line:480`
- `packages/future_homes_tech_presence_automations.yaml` → `line:484`
- `packages/future_homes_tech_presence_automations.yaml` → `line:501`
- `packages/future_homes_tech_presence_automations.yaml` → `line:511`
- `packages/future_homes_tech_presence_automations.yaml` → `line:524`
- Review candidate: `binary_sensor.bathroom_3_presence_occupancy_2`. Removing a duplicated area prefix matches an enabled registry entity. Confirm physical device identity and migrate private saved settings before regenerating YAML.

### `binary_sensor.bedroom_1_bedroom_1_closet_pir_occupancy` — unresolved
- `packages/future_homes_tech_presence_automations.yaml` → `line:594`
- `packages/future_homes_tech_presence_automations.yaml` → `line:598`
- `packages/future_homes_tech_presence_automations.yaml` → `line:602`
- `packages/future_homes_tech_presence_automations.yaml` → `line:619`
- `packages/future_homes_tech_presence_automations.yaml` → `line:629`
- `packages/future_homes_tech_presence_automations.yaml` → `line:642`

### `binary_sensor.bedroom_2_bedroom_2_closet_door_sensor` — unresolved
- `packages/future_homes_tech_control_automations.yaml` → `line:24`
- `packages/future_homes_tech_control_automations.yaml` → `line:28`
- `packages/future_homes_tech_control_automations.yaml` → `line:32`
- `packages/future_homes_tech_control_automations.yaml` → `line:62`
- `packages/future_homes_tech_control_automations.yaml` → `line:66`
- `packages/future_homes_tech_control_automations.yaml` → `line:70`
- Review candidate: `binary_sensor.bedroom_2_closet_door_sensor`. Removing a duplicated area prefix matches an enabled registry entity. Confirm physical device identity and migrate private saved settings before regenerating YAML.

### `binary_sensor.bedroom_3_bedroom_3_closet_door_sensor` — unresolved
- `packages/future_homes_tech_control_automations.yaml` → `line:100`
- `packages/future_homes_tech_control_automations.yaml` → `line:104`
- `packages/future_homes_tech_control_automations.yaml` → `line:108`
- `packages/future_homes_tech_control_automations.yaml` → `line:138`
- `packages/future_homes_tech_control_automations.yaml` → `line:142`
- `packages/future_homes_tech_control_automations.yaml` → `line:146`
- Review candidate: `binary_sensor.bedroom_3_closet_door_sensor`. Removing a duplicated area prefix matches an enabled registry entity. Confirm physical device identity and migrate private saved settings before regenerating YAML.

### `binary_sensor.closet_1_closet_1_door_sensor` — unresolved
- `packages/future_homes_tech_control_automations.yaml` → `line:176`
- `packages/future_homes_tech_control_automations.yaml` → `line:180`
- `packages/future_homes_tech_control_automations.yaml` → `line:184`
- `packages/future_homes_tech_control_automations.yaml` → `line:214`
- `packages/future_homes_tech_control_automations.yaml` → `line:218`
- `packages/future_homes_tech_control_automations.yaml` → `line:222`
- Review candidate: `binary_sensor.closet_1_door_sensor`. Removing a duplicated area prefix matches an enabled registry entity. Confirm physical device identity and migrate private saved settings before regenerating YAML.

### `binary_sensor.doorbell_lite_dashboard_active` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/1/cards/3/conditions/0/entity`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/1/cards/3/card/cards/1/entities/4/entity`

### `binary_sensor.doorbell_lite_doorbell` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/1/cards/3/card/cards/1/entities/2/entity`

### `binary_sensor.doorbell_lite_motion` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/1/cards/3/card/cards/1/entities/0/entity`

### `binary_sensor.doorbell_lite_person_detected` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/1/cards/3/card/cards/1/entities/1/entity`

### `binary_sensor.doorbell_lite_speaking_detected` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/1/cards/3/card/cards/1/entities/3/entity`

### `binary_sensor.downstairs_hallway_downstairs_hallway_pir_occupancy` — unresolved
- `packages/future_homes_tech_presence_automations.yaml` → `line:653`
- `packages/future_homes_tech_presence_automations.yaml` → `line:657`
- `packages/future_homes_tech_presence_automations.yaml` → `line:661`
- `packages/future_homes_tech_presence_automations.yaml` → `line:678`
- `packages/future_homes_tech_presence_automations.yaml` → `line:688`
- `packages/future_homes_tech_presence_automations.yaml` → `line:701`
- Review candidate: `binary_sensor.downstairs_hallway_pir_occupancy`. Removing a duplicated area prefix matches an enabled registry entity. Confirm physical device identity and migrate private saved settings before regenerating YAML.

### `binary_sensor.downstairs_hallway_downstairs_hallway_pir_sensor_occupancy` — unresolved
- `packages/future_homes_tech_presence_automations.yaml` → `line:712`
- `packages/future_homes_tech_presence_automations.yaml` → `line:716`
- `packages/future_homes_tech_presence_automations.yaml` → `line:720`
- `packages/future_homes_tech_presence_automations.yaml` → `line:737`
- `packages/future_homes_tech_presence_automations.yaml` → `line:747`
- `packages/future_homes_tech_presence_automations.yaml` → `line:760`

### `binary_sensor.kitchen_kitchen_presence_occupancy_2` — unresolved
- `packages/future_homes_tech_presence_automations.yaml` → `line:948`
- `packages/future_homes_tech_presence_automations.yaml` → `line:952`
- `packages/future_homes_tech_presence_automations.yaml` → `line:956`
- `packages/future_homes_tech_presence_automations.yaml` → `line:974`
- `packages/future_homes_tech_presence_automations.yaml` → `line:984`
- `packages/future_homes_tech_presence_automations.yaml` → `line:997`
- Review candidate: `binary_sensor.kitchen_presence_occupancy_2`. Removing a duplicated area prefix matches an enabled registry entity. Confirm physical device identity and migrate private saved settings before regenerating YAML.

### `binary_sensor.laundry_room_laundry_room_pir_occupancy` — unresolved
- `packages/future_homes_tech_presence_automations.yaml` → `line:1067`
- `packages/future_homes_tech_presence_automations.yaml` → `line:1071`
- `packages/future_homes_tech_presence_automations.yaml` → `line:1075`
- `packages/future_homes_tech_presence_automations.yaml` → `line:1092`
- `packages/future_homes_tech_presence_automations.yaml` → `line:1102`
- `packages/future_homes_tech_presence_automations.yaml` → `line:1115`
- Review candidate: `binary_sensor.laundry_room_pir_occupancy`. Removing a duplicated area prefix matches an enabled registry entity. Confirm physical device identity and migrate private saved settings before regenerating YAML.

### `binary_sensor.pantry_pantry_door_sensor_opening` — unresolved
- `packages/future_homes_tech_control_automations.yaml` → `line:367`
- `packages/future_homes_tech_control_automations.yaml` → `line:371`
- `packages/future_homes_tech_control_automations.yaml` → `line:375`
- `packages/future_homes_tech_control_automations.yaml` → `line:405`
- `packages/future_homes_tech_control_automations.yaml` → `line:409`
- `packages/future_homes_tech_control_automations.yaml` → `line:413`
- Review candidate: `binary_sensor.pantry_door_sensor_opening`. Removing a duplicated area prefix matches an enabled registry entity. Confirm physical device identity and migrate private saved settings before regenerating YAML.

### `binary_sensor.stairway_stairway_pir_1_occupancy` — unresolved
- `packages/future_homes_tech_presence_automations.yaml` → `line:1303`
- `packages/future_homes_tech_presence_automations.yaml` → `line:1307`
- `packages/future_homes_tech_presence_automations.yaml` → `line:1311`
- `packages/future_homes_tech_presence_automations.yaml` → `line:1328`
- `packages/future_homes_tech_presence_automations.yaml` → `line:1338`
- `packages/future_homes_tech_presence_automations.yaml` → `line:1351`
- Review candidate: `binary_sensor.stairway_pir_1_occupancy`. Removing a duplicated area prefix matches an enabled registry entity. Confirm physical device identity and migrate private saved settings before regenerating YAML.

### `binary_sensor.stairway_stairway_pir_2_occupancy` — unresolved
- `packages/future_homes_tech_presence_automations.yaml` → `line:1362`
- `packages/future_homes_tech_presence_automations.yaml` → `line:1366`
- `packages/future_homes_tech_presence_automations.yaml` → `line:1370`
- `packages/future_homes_tech_presence_automations.yaml` → `line:1387`
- `packages/future_homes_tech_presence_automations.yaml` → `line:1397`
- `packages/future_homes_tech_presence_automations.yaml` → `line:1410`
- Review candidate: `binary_sensor.stairway_pir_2_occupancy`. Removing a duplicated area prefix matches an enabled registry entity. Confirm physical device identity and migrate private saved settings before regenerating YAML.

### `binary_sensor.stairway_stairway_pir_sensor_occupancy` — unresolved
- `packages/future_homes_tech_presence_automations.yaml` → `line:1421`
- `packages/future_homes_tech_presence_automations.yaml` → `line:1425`
- `packages/future_homes_tech_presence_automations.yaml` → `line:1429`
- `packages/future_homes_tech_presence_automations.yaml` → `line:1446`
- `packages/future_homes_tech_presence_automations.yaml` → `line:1456`
- `packages/future_homes_tech_presence_automations.yaml` → `line:1469`

### `binary_sensor.upstairs_hallway_upstairs_hallway_pir_2_occupancy` — unresolved
- `packages/future_homes_tech_presence_automations.yaml` → `line:1598`
- `packages/future_homes_tech_presence_automations.yaml` → `line:1602`
- `packages/future_homes_tech_presence_automations.yaml` → `line:1606`
- `packages/future_homes_tech_presence_automations.yaml` → `line:1623`
- `packages/future_homes_tech_presence_automations.yaml` → `line:1633`
- `packages/future_homes_tech_presence_automations.yaml` → `line:1646`
- Review candidate: `binary_sensor.upstairs_hallway_pir_2_occupancy`. Removing a duplicated area prefix matches an enabled registry entity. Confirm physical device identity and migrate private saved settings before regenerating YAML.

### `climate.downstairs_hallway_downstairs_thermostat` — unresolved
- `packages/future_homes_tech_homekit.yaml` → `line:72`
- `packages/future_homes_tech_homekit.yaml` → `line:75`
- `packages/future_homes_tech_homekit.yaml` → `line:76`

### `climate.downstairs_thermostat_downstairs` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/1/cards/1/entity`

### `climate.upstairs_hallway_upstairs_hallway_thermostat` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/1/cards/0/entity`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/1/cards/4/entity`
- `packages/future_homes_tech_homekit.yaml` → `line:73`
- `packages/future_homes_tech_homekit.yaml` → `line:77`
- `packages/future_homes_tech_homekit.yaml` → `line:78`
- Review candidate: `climate.upstairs_hallway_thermostat`. Removing a duplicated area prefix matches an enabled registry entity. Confirm physical device identity and migrate private saved settings before regenerating YAML.

### `event.kitchen_kitchen_switch_1g_button_down` — unresolved
- `packages/future_homes_tech_control_automations.yaml` → `line:443`
- `packages/future_homes_tech_control_automations.yaml` → `line:447`
- `packages/future_homes_tech_control_automations.yaml` → `line:465`
- `packages/future_homes_tech_control_automations.yaml` → `line:469`

### `event.kitchen_kitchen_switch_1g_button_up` — unresolved
- `packages/future_homes_tech_control_automations.yaml` → `line:487`
- `packages/future_homes_tech_control_automations.yaml` → `line:491`
- `packages/future_homes_tech_control_automations.yaml` → `line:511`
- `packages/future_homes_tech_control_automations.yaml` → `line:515`

### `event.office_office_button_button_1` — unresolved
- `packages/future_homes_tech_control_automations.yaml` → `line:535`
- `packages/future_homes_tech_control_automations.yaml` → `line:539`

### `event.office_office_button_button_2` — unresolved
- `packages/future_homes_tech_control_automations.yaml` → `line:1315`
- `packages/future_homes_tech_control_automations.yaml` → `line:1319`

### `event.office_office_desk_button_button_1` — unresolved
- `packages/future_homes_tech_control_automations.yaml` → `line:557`
- `packages/future_homes_tech_control_automations.yaml` → `line:561`

### `event.office_office_desk_button_button_2` — unresolved
- `packages/future_homes_tech_control_automations.yaml` → `line:579`
- `packages/future_homes_tech_control_automations.yaml` → `line:583`

### `fan.maverick_ceiling_fan` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/0/cards/4/cards/1/card/chips/0/entity`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/0/cards/4/cards/1/card/chips/0/icon_color`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/0/cards/4/cards/1/card/chips/0/card_mod/style/mushroom-shape-icon$`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/0/cards/4/cards/1/card/chips/0/card_mod/style/.`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/0/cards/4/cards/1/card/chips/1/entity`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/0/cards/4/cards/1/card/chips/1/icon_color`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/0/cards/4/cards/1/card/chips/1/card_mod/style`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/0/cards/4/cards/1/card/chips/1/tap_action/target/entity_id`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/0/cards/4/cards/1/card/chips/2/entity`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/0/cards/4/cards/1/card/chips/2/icon_color`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/0/cards/4/cards/1/card/chips/2/icon_color`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/0/cards/4/cards/1/card/chips/2/card_mod/style`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/0/cards/4/cards/1/card/chips/2/card_mod/style`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/0/cards/4/cards/1/card/chips/2/tap_action/target/entity_id`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/0/cards/4/cards/1/card/chips/3/entity`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/0/cards/4/cards/1/card/chips/3/icon_color`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/0/cards/4/cards/1/card/chips/3/icon_color`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/0/cards/4/cards/1/card/chips/3/card_mod/style`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/0/cards/4/cards/1/card/chips/3/card_mod/style`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/0/cards/4/cards/1/card/chips/3/tap_action/target/entity_id`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/0/cards/4/cards/1/card/chips/4/entity`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/0/cards/4/cards/1/card/chips/4/icon_color`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/0/cards/4/cards/1/card/chips/4/card_mod/style`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/0/cards/4/cards/1/card/chips/4/tap_action/target/entity_id`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/0/cards/4/cards/1/card/chips/5/entity`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/0/cards/4/cards/1/card/chips/5/icon_color`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/0/cards/4/cards/1/card/chips/5/card_mod/style`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/0/cards/4/cards/1/card/chips/5/tap_action/target/entity_id`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/0/cards/4/cards/1/card/chips/6/entity`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/0/cards/4/cards/1/card/chips/6/icon_color`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/0/cards/4/cards/1/card/chips/6/card_mod/style`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/0/cards/4/cards/1/card/chips/6/tap_action/target/entity_id`

### `input_boolean.block_context_menu` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/kiosk_mode/block_context_menu`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/2/cards/3/cards/1/entities/15/entity`

### `input_boolean.block_mouse` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/kiosk_mode/block_mouse`

### `input_boolean.block_overflow` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/kiosk_mode/block_overflow`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/2/cards/3/cards/1/entities/14/entity`

### `input_boolean.debug6` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/kiosk_mode/debug`

### `input_boolean.debug_template6` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/kiosk_mode/debug_template`

### `input_boolean.hide_account` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/kiosk_mode/hide_account`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/2/cards/3/cards/1/entities/0/entity`

### `input_boolean.hide_add_to_home_assistant` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/kiosk_mode/hide_add_to_home_assistant`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/2/cards/3/cards/1/entities/13/entity`

### `input_boolean.hide_assistant` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/kiosk_mode/hide_assistant`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/2/cards/3/cards/1/entities/1/entity`

### `input_boolean.hide_dialog_camera_actions` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/kiosk_mode/hide_dialog_camera_actions`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/2/cards/3/cards/1/entities/27/entity`

### `input_boolean.hide_dialog_climate_actions` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/kiosk_mode/hide_dialog_climate_actions`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/2/cards/3/cards/1/entities/29/entity`

### `input_boolean.hide_dialog_climate_settings_actions` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/kiosk_mode/hide_dialog_climate_settings_actions`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/2/cards/3/cards/1/entities/31/entity`

### `input_boolean.hide_dialog_climate_temperature_actions` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/kiosk_mode/hide_dialog_climate_temperature_actions`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/2/cards/3/cards/1/entities/30/entity`

### `input_boolean.hide_dialog_header_action_items` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/kiosk_mode/hide_dialog_header_action_items`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/2/cards/3/cards/1/entities/20/entity`

### `input_boolean.hide_dialog_header_breadcrumb_navigation` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/2/cards/3/cards/1/entities/16/entity`

### `input_boolean.hide_dialog_header_breadcrumb_navigation2` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/kiosk_mode/hide_dialog_header_breadcrumb_navigation`

### `input_boolean.hide_dialog_header_history` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/kiosk_mode/hide_dialog_header_history`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/2/cards/3/cards/1/entities/17/entity`

### `input_boolean.hide_dialog_header_overflow` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/2/cards/3/cards/1/entities/19/entity`

### `input_boolean.hide_dialog_header_overflow3` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/kiosk_mode/hide_dialog_header_overflow`

### `input_boolean.hide_dialog_header_settings` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/2/cards/3/cards/1/entities/18/entity`

### `input_boolean.hide_dialog_header_settings3` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/kiosk_mode/hide_dialog_header_settings`

### `input_boolean.hide_dialog_history` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/kiosk_mode/hide_dialog_history`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/2/cards/3/cards/1/entities/21/entity`

### `input_boolean.hide_dialog_history_show_more` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/kiosk_mode/hide_dialog_history_show_more`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/2/cards/3/cards/1/entities/22/entity`

### `input_boolean.hide_dialog_light_actions` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/kiosk_mode/hide_dialog_light_actions`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/2/cards/3/cards/1/entities/32/entity`

### `input_boolean.hide_dialog_light_color_actions` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/kiosk_mode/hide_dialog_light_color_actions`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/2/cards/3/cards/1/entities/34/entity`

### `input_boolean.hide_dialog_light_control_actions` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/kiosk_mode/hide_dialog_light_control_actions`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/2/cards/3/cards/1/entities/33/entity`

### `input_boolean.hide_dialog_light_settings_actions` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/kiosk_mode/hide_dialog_light_settings_actions`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/2/cards/3/cards/1/entities/35/entity`

### `input_boolean.hide_dialog_logbook` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/kiosk_mode/hide_dialog_logbook`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/2/cards/3/cards/1/entities/23/entity`

### `input_boolean.hide_dialog_logbook_show_more` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/kiosk_mode/hide_dialog_logbook_show_more`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/2/cards/3/cards/1/entities/24/entity`

### `input_boolean.hide_dialog_media_actions` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/kiosk_mode/hide_dialog_media_actions`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/2/cards/3/cards/1/entities/25/entity`

### `input_boolean.hide_dialog_timer_actions` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/kiosk_mode/hide_dialog_timer_actions`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/2/cards/3/cards/1/entities/28/entity`

### `input_boolean.hide_dialog_update_actions` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/kiosk_mode/hide_dialog_update_actions`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/2/cards/3/cards/1/entities/26/entity`

### `input_boolean.hide_edit_dashboard` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/kiosk_mode/hide_edit_dashboard`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/2/cards/3/cards/1/entities/12/entity`

### `input_boolean.hide_menubutton` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/kiosk_mode/hide_menubutton`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/2/cards/3/cards/1/entities/3/entity`

### `input_boolean.hide_notifications` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/kiosk_mode/hide_notifications`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/2/cards/3/cards/1/entities/4/entity`

### `input_boolean.hide_overflow` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/kiosk_mode/hide_overflow`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/2/cards/3/cards/1/entities/5/entity`

### `input_boolean.hide_refresh` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/kiosk_mode/hide_refresh`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/2/cards/3/cards/1/entities/9/entity`

### `input_boolean.hide_reload_resources` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/kiosk_mode/hide_reload_resources`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/2/cards/3/cards/1/entities/11/entity`

### `input_boolean.hide_search` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/kiosk_mode/hide_search`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/2/cards/3/cards/1/entities/6/entity`

### `input_boolean.hide_settings` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/kiosk_mode/hide_settings`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/2/cards/3/cards/1/entities/7/entity`

### `input_boolean.hide_unused_entities` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/kiosk_mode/hide_unused_entities`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/2/cards/3/cards/1/entities/10/entity`

### `input_boolean.ignore_disable_km4` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/kiosk_mode/ignore_disable_km`

### `input_boolean.ignore_mobile_settings4` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/kiosk_mode/ignore_mobile_settings`

### `input_boolean.maverick_sleep_mode` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/badges/4/entity`

### `input_number.fht_delta_` — dynamic_prefix
- `packages/future_homes_tech_climate.yaml` → `line:1810`
- `packages/future_homes_tech_climate.yaml` → `line:1825`
- `packages/future_homes_tech_climate.yaml` → `line:2176`
- `packages/future_homes_tech_climate.yaml` → `line:2284`
- `packages/future_homes_tech_climate.yaml` → `line:2396`
- `packages/future_homes_tech_climate.yaml` → `line:2627`
- `packages/future_homes_tech_climate.yaml` → `line:2628`

### `input_number.fht_super_cool_max_time_prior_allowed` — unresolved
- `packages/future_homes_tech_climate.yaml` → `line:2289`

### `input_select.room_mode` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/0/cards/2/entity`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/0/cards/3/visibility/0/entity`

### `light.all_lights` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/2/cards/4/cards/1/filter/exclude/0/entity_id`

### `light.fht_bedroom_2_headboard_lights` — unresolved
- `packages/future_homes_tech_control_automations.yaml` → `line:839`
- `packages/future_homes_tech_control_automations.yaml` → `line:857`
- `packages/future_homes_tech_control_automations.yaml` → `line:860`
- `packages/future_homes_tech_control_automations.yaml` → `line:868`
- `packages/future_homes_tech_control_automations.yaml` → `line:871`
- `packages/future_homes_tech_control_automations.yaml` → `line:1603`
- `packages/future_homes_tech_control_automations.yaml` → `line:1607`
- `packages/future_homes_tech_control_automations.yaml` → `line:1611`

### `light.fht_bedroom_4_fan_lights` — unresolved
- `packages/future_homes_tech_control_automations.yaml` → `line:941`
- `packages/future_homes_tech_control_automations.yaml` → `line:959`
- `packages/future_homes_tech_control_automations.yaml` → `line:962`
- `packages/future_homes_tech_control_automations.yaml` → `line:970`
- `packages/future_homes_tech_control_automations.yaml` → `line:973`
- `packages/future_homes_tech_control_automations.yaml` → `line:1717`
- `packages/future_homes_tech_control_automations.yaml` → `line:1721`
- `packages/future_homes_tech_control_automations.yaml` → `line:1725`
- `packages/future_homes_tech_homekit.yaml` → `line:11`
- `packages/future_homes_tech_homekit.yaml` → `line:36`

### `light.fht_bedroom_5_fan_lights` — unresolved
- `packages/future_homes_tech_homekit.yaml` → `line:12`
- `packages/future_homes_tech_homekit.yaml` → `line:38`

### `light.fht_bedroom_6_desk_lights` — unresolved
- `packages/future_homes_tech_control_automations.yaml` → `line:1009`
- `packages/future_homes_tech_control_automations.yaml` → `line:1027`
- `packages/future_homes_tech_control_automations.yaml` → `line:1030`
- `packages/future_homes_tech_control_automations.yaml` → `line:1038`
- `packages/future_homes_tech_control_automations.yaml` → `line:1041`
- `packages/future_homes_tech_control_automations.yaml` → `line:1755`
- `packages/future_homes_tech_control_automations.yaml` → `line:1759`
- `packages/future_homes_tech_control_automations.yaml` → `line:1763`
- `packages/future_homes_tech_homekit.yaml` → `line:13`
- `packages/future_homes_tech_homekit.yaml` → `line:40`
- `packages/future_homes_tech_homekit.yaml` → `line:41`

### `light.fht_bedroom_6_fan_lights` — unresolved
- `packages/future_homes_tech_control_automations.yaml` → `line:975`
- `packages/future_homes_tech_control_automations.yaml` → `line:993`
- `packages/future_homes_tech_control_automations.yaml` → `line:996`
- `packages/future_homes_tech_control_automations.yaml` → `line:1004`
- `packages/future_homes_tech_control_automations.yaml` → `line:1007`
- `packages/future_homes_tech_control_automations.yaml` → `line:1793`
- `packages/future_homes_tech_control_automations.yaml` → `line:1797`
- `packages/future_homes_tech_control_automations.yaml` → `line:1801`
- `packages/future_homes_tech_homekit.yaml` → `line:14`
- `packages/future_homes_tech_homekit.yaml` → `line:42`

### `light.kitchen_light` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/0/cards/3/cards/0/conditions/0/entity`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/0/cards/3/cards/0/card/entity`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/0/cards/3/cards/1/conditions/0/entity`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/0/cards/3/cards/1/card/entity`

### `light.maverick_bed_rgb_light` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/0/cards/4/cards/2/card/cards/0/entity`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/0/cards/4/cards/2/card/cards/1/chips/0/entity`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/0/cards/4/cards/2/card/cards/1/chips/0/icon_color`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/0/cards/4/cards/2/card/cards/1/chips/0/card_mod/style`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/0/cards/4/cards/2/card/cards/1/chips/0/tap_action/target/entity_id`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/0/cards/4/cards/2/card/cards/1/chips/1/entity`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/0/cards/4/cards/2/card/cards/1/chips/1/tap_action/target/entity_id`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/0/cards/4/cards/2/card/cards/1/chips/2/entity`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/0/cards/4/cards/2/card/cards/1/chips/2/tap_action/target/entity_id`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/0/cards/4/cards/2/card/cards/1/chips/3/entity`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/0/cards/4/cards/2/card/cards/1/chips/3/tap_action/target/entity_id`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/0/cards/4/cards/2/card/cards/1/chips/4/entity`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/0/cards/4/cards/2/card/cards/1/chips/4/tap_action/target/entity_id`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/0/cards/4/cards/2/card/cards/1/chips/5/entity`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/0/cards/4/cards/2/card/cards/1/chips/5/tap_action/target/entity_id`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/0/cards/4/cards/2/card/cards/1/chips/6/entity`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/0/cards/4/cards/2/card/cards/1/chips/6/tap_action/target/entity_id`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/0/cards/4/cards/2/card/cards/1/chips/7/entity`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/0/cards/4/cards/2/card/cards/1/chips/7/tap_action/target/entity_id`

### `light.maverick_s_bedroom_light` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/0/cards/4/cards/0/cards/0/entity`

### `light.mavericks_bedroom_closet_light` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/0/cards/4/cards/0/cards/1/entity`

### `light.upstairs_hallway_upstairs_hallway_light_1` — unresolved
- `packages/future_homes_tech_presence_automations.yaml` → `line:1598`
- `packages/future_homes_tech_presence_automations.yaml` → `line:1627`
- `packages/future_homes_tech_presence_automations.yaml` → `line:1639`
- `packages/future_homes_tech_presence_automations.yaml` → `line:1653`
- Review candidate: `light.upstairs_hallway_light_1`. Removing a duplicated area prefix matches an enabled registry entity. Confirm physical device identity and migrate private saved settings before regenerating YAML.

### `light.upstairs_hallway_upstairs_hallway_light_2` — unresolved
- `packages/future_homes_tech_presence_automations.yaml` → `line:1067`
- `packages/future_homes_tech_presence_automations.yaml` → `line:1096`
- `packages/future_homes_tech_presence_automations.yaml` → `line:1108`
- `packages/future_homes_tech_presence_automations.yaml` → `line:1122`
- Review candidate: `light.upstairs_hallway_light_2`. Removing a duplicated area prefix matches an enabled registry entity. Confirm physical device identity and migrate private saved settings before regenerating YAML.

### `media_player.office_apple_tv` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/1/cards/2/cards/1/entity`

### `media_player.office_homepod` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/1/cards/2/cards/2/entity`

### `media_player.office_tv_65` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/1/cards/2/cards/0/cards/0/entity`

### `sensor.battery_low` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/badges/0/visibility/0/entity`

### `sensor.email_history` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/2/cards/1/content`

### `sensor.kitchen_light_display_name` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/0/cards/3/cards/0/card/primary`
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/sections/0/cards/3/cards/1/card/primary`

### `sensor.lights_on_count` — unresolved
- `.storage/lovelace.dashboard_dashboard` → `data/config/views/0/badges/2/entity`

### `switch.bathroom_1_bathroom_1_toilet_switch_2g_switch_1` — unresolved
- `packages/future_homes_tech_control_automations.yaml` → `line:601`
- `packages/future_homes_tech_control_automations.yaml` → `line:605`
- `packages/future_homes_tech_control_automations.yaml` → `line:609`
- `packages/future_homes_tech_control_automations.yaml` → `line:1394`
- `packages/future_homes_tech_control_automations.yaml` → `line:1399`
- `packages/future_homes_tech_control_automations.yaml` → `line:1406`
- `packages/future_homes_tech_control_automations.yaml` → `line:1411`

### `switch.bathroom_2_bathroom_2_switch_1g` — unresolved
- `packages/future_homes_tech_control_automations.yaml` → `line:635`
- `packages/future_homes_tech_control_automations.yaml` → `line:639`
- `packages/future_homes_tech_control_automations.yaml` → `line:643`
- `packages/future_homes_tech_control_automations.yaml` → `line:1470`
- `packages/future_homes_tech_control_automations.yaml` → `line:1475`
- `packages/future_homes_tech_control_automations.yaml` → `line:1482`
- `packages/future_homes_tech_control_automations.yaml` → `line:1487`

### `switch.bathroom_2_bathroom_2_toilet_switch_2g_switch_1` — unresolved
- `packages/future_homes_tech_control_automations.yaml` → `line:669`
- `packages/future_homes_tech_control_automations.yaml` → `line:673`
- `packages/future_homes_tech_control_automations.yaml` → `line:677`
- `packages/future_homes_tech_control_automations.yaml` → `line:1432`
- `packages/future_homes_tech_control_automations.yaml` → `line:1437`
- `packages/future_homes_tech_control_automations.yaml` → `line:1444`
- `packages/future_homes_tech_control_automations.yaml` → `line:1449`

### `switch.bathroom_3_bathroom_3_switch_2g_switch_1` — unresolved
- `packages/future_homes_tech_control_automations.yaml` → `line:703`
- `packages/future_homes_tech_control_automations.yaml` → `line:707`
- `packages/future_homes_tech_control_automations.yaml` → `line:711`
- `packages/future_homes_tech_control_automations.yaml` → `line:1508`
- `packages/future_homes_tech_control_automations.yaml` → `line:1513`
- `packages/future_homes_tech_control_automations.yaml` → `line:1520`
- `packages/future_homes_tech_control_automations.yaml` → `line:1525`

### `switch.bedroom_1_bedroom_1_closet_switch_3g_switch_2` — unresolved
- `packages/future_homes_tech_control_automations.yaml` → `line:737`
- `packages/future_homes_tech_control_automations.yaml` → `line:741`
- `packages/future_homes_tech_control_automations.yaml` → `line:745`
- `packages/future_homes_tech_control_automations.yaml` → `line:1356`
- `packages/future_homes_tech_control_automations.yaml` → `line:1361`
- `packages/future_homes_tech_control_automations.yaml` → `line:1368`
- `packages/future_homes_tech_control_automations.yaml` → `line:1373`

### `switch.bedroom_1_bedroom_1_switch_3g_switch_1` — unresolved
- `packages/future_homes_tech_control_automations.yaml` → `line:771`
- `packages/future_homes_tech_control_automations.yaml` → `line:775`
- `packages/future_homes_tech_control_automations.yaml` → `line:779`
- `packages/future_homes_tech_control_automations.yaml` → `line:1546`
- `packages/future_homes_tech_control_automations.yaml` → `line:1551`
- `packages/future_homes_tech_control_automations.yaml` → `line:1558`
- `packages/future_homes_tech_control_automations.yaml` → `line:1563`

### `switch.bedroom_2_bedroom_2_switch_3g_switch_1` — unresolved
- `packages/future_homes_tech_control_automations.yaml` → `line:805`
- `packages/future_homes_tech_control_automations.yaml` → `line:809`
- `packages/future_homes_tech_control_automations.yaml` → `line:813`
- `packages/future_homes_tech_control_automations.yaml` → `line:1584`
- `packages/future_homes_tech_control_automations.yaml` → `line:1589`
- `packages/future_homes_tech_control_automations.yaml` → `line:1596`
- `packages/future_homes_tech_control_automations.yaml` → `line:1601`

### `switch.bedroom_2_bedroom_2_switch_3g_switch_2` — unresolved
- `packages/future_homes_tech_control_automations.yaml` → `line:839`
- `packages/future_homes_tech_control_automations.yaml` → `line:843`
- `packages/future_homes_tech_control_automations.yaml` → `line:847`
- `packages/future_homes_tech_control_automations.yaml` → `line:1622`
- `packages/future_homes_tech_control_automations.yaml` → `line:1627`
- `packages/future_homes_tech_control_automations.yaml` → `line:1634`
- `packages/future_homes_tech_control_automations.yaml` → `line:1639`

### `switch.bedroom_3_bedroom_3_switch_3g_switch_1` — unresolved
- `packages/future_homes_tech_control_automations.yaml` → `line:873`
- `packages/future_homes_tech_control_automations.yaml` → `line:877`
- `packages/future_homes_tech_control_automations.yaml` → `line:881`
- `packages/future_homes_tech_control_automations.yaml` → `line:1698`
- `packages/future_homes_tech_control_automations.yaml` → `line:1703`
- `packages/future_homes_tech_control_automations.yaml` → `line:1710`
- `packages/future_homes_tech_control_automations.yaml` → `line:1715`

### `switch.bedroom_3_bedroom_3_switch_3g_switch_2` — unresolved
- `packages/future_homes_tech_control_automations.yaml` → `line:907`
- `packages/future_homes_tech_control_automations.yaml` → `line:911`
- `packages/future_homes_tech_control_automations.yaml` → `line:915`
- `packages/future_homes_tech_control_automations.yaml` → `line:1660`
- `packages/future_homes_tech_control_automations.yaml` → `line:1665`
- `packages/future_homes_tech_control_automations.yaml` → `line:1672`
- `packages/future_homes_tech_control_automations.yaml` → `line:1677`

### `switch.bedroom_4_bedroom_4_switch_3g_switch_1` — unresolved
- `packages/future_homes_tech_control_automations.yaml` → `line:941`
- `packages/future_homes_tech_control_automations.yaml` → `line:945`
- `packages/future_homes_tech_control_automations.yaml` → `line:949`
- `packages/future_homes_tech_control_automations.yaml` → `line:1736`
- `packages/future_homes_tech_control_automations.yaml` → `line:1741`
- `packages/future_homes_tech_control_automations.yaml` → `line:1748`
- `packages/future_homes_tech_control_automations.yaml` → `line:1753`

### `switch.bedroom_6_bedroom_6_switch_3g_switch_1` — unresolved
- `packages/future_homes_tech_control_automations.yaml` → `line:975`
- `packages/future_homes_tech_control_automations.yaml` → `line:979`
- `packages/future_homes_tech_control_automations.yaml` → `line:983`
- `packages/future_homes_tech_control_automations.yaml` → `line:1812`
- `packages/future_homes_tech_control_automations.yaml` → `line:1817`
- `packages/future_homes_tech_control_automations.yaml` → `line:1824`
- `packages/future_homes_tech_control_automations.yaml` → `line:1829`

### `switch.bedroom_6_bedroom_6_switch_3g_switch_2` — unresolved
- `packages/future_homes_tech_control_automations.yaml` → `line:1009`
- `packages/future_homes_tech_control_automations.yaml` → `line:1013`
- `packages/future_homes_tech_control_automations.yaml` → `line:1017`
- `packages/future_homes_tech_control_automations.yaml` → `line:1774`
- `packages/future_homes_tech_control_automations.yaml` → `line:1779`
- `packages/future_homes_tech_control_automations.yaml` → `line:1786`
- `packages/future_homes_tech_control_automations.yaml` → `line:1791`

### `switch.dining_room_dining_room_switch_1g` — unresolved
- `packages/future_homes_tech_control_automations.yaml` → `line:1043`
- `packages/future_homes_tech_control_automations.yaml` → `line:1047`
- `packages/future_homes_tech_control_automations.yaml` → `line:1051`
- `packages/future_homes_tech_control_automations.yaml` → `line:1850`
- `packages/future_homes_tech_control_automations.yaml` → `line:1855`
- `packages/future_homes_tech_control_automations.yaml` → `line:1862`
- `packages/future_homes_tech_control_automations.yaml` → `line:1867`

### `switch.downstairs_hallway_downstairs_hallway_switch_1_1g` — unresolved
- `packages/future_homes_tech_control_automations.yaml` → `line:1077`
- `packages/future_homes_tech_control_automations.yaml` → `line:1081`
- `packages/future_homes_tech_control_automations.yaml` → `line:1085`
- `packages/future_homes_tech_control_automations.yaml` → `line:1888`
- `packages/future_homes_tech_control_automations.yaml` → `line:1893`
- `packages/future_homes_tech_control_automations.yaml` → `line:1908`
- `packages/future_homes_tech_control_automations.yaml` → `line:1913`

### `switch.downstairs_hallway_downstairs_hallway_switch_2_1g` — unresolved
- `packages/future_homes_tech_control_automations.yaml` → `line:1111`
- `packages/future_homes_tech_control_automations.yaml` → `line:1115`
- `packages/future_homes_tech_control_automations.yaml` → `line:1119`
- `packages/future_homes_tech_control_automations.yaml` → `line:1896`
- `packages/future_homes_tech_control_automations.yaml` → `line:1901`
- `packages/future_homes_tech_control_automations.yaml` → `line:1916`
- `packages/future_homes_tech_control_automations.yaml` → `line:1921`

### `switch.living_room_living_room_switch_3g_switch_1` — unresolved
- `packages/future_homes_tech_control_automations.yaml` → `line:1145`
- `packages/future_homes_tech_control_automations.yaml` → `line:1149`
- `packages/future_homes_tech_control_automations.yaml` → `line:1153`
- `packages/future_homes_tech_control_automations.yaml` → `line:1980`
- `packages/future_homes_tech_control_automations.yaml` → `line:1985`
- `packages/future_homes_tech_control_automations.yaml` → `line:1992`
- `packages/future_homes_tech_control_automations.yaml` → `line:1997`

### `switch.living_room_living_room_switch_3g_switch_2` — unresolved
- `packages/future_homes_tech_control_automations.yaml` → `line:1179`
- `packages/future_homes_tech_control_automations.yaml` → `line:1183`
- `packages/future_homes_tech_control_automations.yaml` → `line:1187`
- `packages/future_homes_tech_control_automations.yaml` → `line:1942`
- `packages/future_homes_tech_control_automations.yaml` → `line:1947`
- `packages/future_homes_tech_control_automations.yaml` → `line:1954`
- `packages/future_homes_tech_control_automations.yaml` → `line:1959`

### `switch.office_office_speaker` — unresolved
- `packages/future_homes_tech_control_automations.yaml` → `line:1328`
- `packages/future_homes_tech_control_automations.yaml` → `line:1330`
- `packages/future_homes_tech_control_automations.yaml` → `line:1335`
- Review candidate: `switch.office_speaker`. Removing a duplicated area prefix matches an enabled registry entity. Confirm physical device identity and migrate private saved settings before regenerating YAML.

### `switch.stairway_stairway_switch_1g` — unresolved
- `packages/future_homes_tech_control_automations.yaml` → `line:1213`
- `packages/future_homes_tech_control_automations.yaml` → `line:1217`
- `packages/future_homes_tech_control_automations.yaml` → `line:1221`
- `packages/future_homes_tech_control_automations.yaml` → `line:2018`
- `packages/future_homes_tech_control_automations.yaml` → `line:2023`
- `packages/future_homes_tech_control_automations.yaml` → `line:2038`
- `packages/future_homes_tech_control_automations.yaml` → `line:2043`

### `switch.upstairs_hallway_upstairs_hallway_switch_2g_switch_1` — unresolved
- `packages/future_homes_tech_control_automations.yaml` → `line:1247`
- `packages/future_homes_tech_control_automations.yaml` → `line:1251`
- `packages/future_homes_tech_control_automations.yaml` → `line:1255`
- `packages/future_homes_tech_control_automations.yaml` → `line:2072`
- `packages/future_homes_tech_control_automations.yaml` → `line:2077`
- `packages/future_homes_tech_control_automations.yaml` → `line:2084`
- `packages/future_homes_tech_control_automations.yaml` → `line:2089`

### `switch.upstairs_hallway_upstairs_hallway_switch_2g_switch_2` — unresolved
- `packages/future_homes_tech_control_automations.yaml` → `line:1281`
- `packages/future_homes_tech_control_automations.yaml` → `line:1285`
- `packages/future_homes_tech_control_automations.yaml` → `line:1289`
- `packages/future_homes_tech_control_automations.yaml` → `line:2026`
- `packages/future_homes_tech_control_automations.yaml` → `line:2031`
- `packages/future_homes_tech_control_automations.yaml` → `line:2046`
- `packages/future_homes_tech_control_automations.yaml` → `line:2051`

## Group overlap review

- `light.bathroom_1_all_lights` (0 references) / `light.fht_bathroom_1_all_lights` (3 references). Generated and legacy group IDs share the same suffix; member sets have not been compared.
- `light.bathroom_1_all_bathroom_lights` (0 references) / `light.fht_bathroom_1_all_bathroom_lights` (13 references). Generated and legacy group IDs share the same suffix; member sets have not been compared.
- `light.bathroom_1_bath_lights` (0 references) / `light.fht_bathroom_1_bath_lights` (1 references). Generated and legacy group IDs share the same suffix; member sets have not been compared.
- `light.bathroom_1_her_vanity_lights` (0 references) / `light.fht_bathroom_1_her_vanity_lights` (1 references). Generated and legacy group IDs share the same suffix; member sets have not been compared.
- `light.bathroom_1_his_vanity_lights` (0 references) / `light.fht_bathroom_1_his_vanity_lights` (1 references). Generated and legacy group IDs share the same suffix; member sets have not been compared.
- `light.bathroom_1_shower_lights` (0 references) / `light.fht_bathroom_1_shower_lights` (1 references). Generated and legacy group IDs share the same suffix; member sets have not been compared.
- `light.bathroom_1_toilet_lights` (0 references) / `light.fht_bathroom_1_toilet_lights` (13 references). Generated and legacy group IDs share the same suffix; member sets have not been compared.
- `light.bathroom_1_vanity_lights` (0 references) / `light.fht_bathroom_1_vanity_lights` (1 references). Generated and legacy group IDs share the same suffix; member sets have not been compared.
- `light.bathroom_2_all_lights` (0 references) / `light.fht_bathroom_2_all_lights` (1 references). Generated and legacy group IDs share the same suffix; member sets have not been compared.
- `light.bathroom_2_shower_lights` (0 references) / `light.fht_bathroom_2_shower_lights` (16 references). Generated and legacy group IDs share the same suffix; member sets have not been compared.
- `light.bathroom_2_vanity_lights` (0 references) / `light.fht_bathroom_2_vanity_lights` (16 references). Generated and legacy group IDs share the same suffix; member sets have not been compared.
- `light.bedroom_2_all_lights` (0 references) / `light.fht_bedroom_2_all_lights` (1 references). Generated and legacy group IDs share the same suffix; member sets have not been compared.
- `light.bedroom_2_fan_lights` (0 references) / `light.fht_bedroom_2_fan_lights` (10 references). Generated and legacy group IDs share the same suffix; member sets have not been compared.
- `light.bedroom_3_all_lights` (0 references) / `light.fht_bedroom_3_all_lights` (1 references). Generated and legacy group IDs share the same suffix; member sets have not been compared.
- `light.bedroom_3_bed_lights` (0 references) / `light.fht_bedroom_3_bed_lights` (7 references). Generated and legacy group IDs share the same suffix; member sets have not been compared.
- `light.bedroom_3_closet_lights` (0 references) / `light.fht_bedroom_3_closet_lights` (9 references). Generated and legacy group IDs share the same suffix; member sets have not been compared.
- `light.bedroom_3_fan_lights` (0 references) / `light.fht_bedroom_3_fan_lights` (9 references). Generated and legacy group IDs share the same suffix; member sets have not been compared.
- `light.bedroom_6_all_lights` (0 references) / `light.fht_bedroom_6_all_lights` (1 references). Generated and legacy group IDs share the same suffix; member sets have not been compared.
- `light.fht_kitchen_all_lights` (1 references) / `light.kitchen_all_lights` (1 references). Generated and legacy group IDs share the same suffix; member sets have not been compared.
- `light.fht_kitchen_bar_lights` (9 references) / `light.kitchen_bar_lights` (0 references). Generated and legacy group IDs share the same suffix; member sets have not been compared.
- `light.fht_kitchen_lights` (15 references) / `light.kitchen_lights` (0 references). Generated and legacy group IDs share the same suffix; member sets have not been compared.
- `light.fht_living_room_all_lights` (1 references) / `light.living_room_all_lights` (0 references). Generated and legacy group IDs share the same suffix; member sets have not been compared.
- `light.fht_living_room_can_lights` (9 references) / `light.living_room_can_lights` (0 references). Generated and legacy group IDs share the same suffix; member sets have not been compared.
- `light.fht_living_room_fan_lights` (9 references) / `light.living_room_fan_lights` (0 references). Generated and legacy group IDs share the same suffix; member sets have not been compared.
- `light.fht_outside_perimeter_all_lights` (4 references) / `light.outside_perimeter_all_lights` (0 references). Generated and legacy group IDs share the same suffix; member sets have not been compared.
- `light.fht_outside_perimeter_backyard_lights` (3 references) / `light.outside_perimeter_backyard_lights` (0 references). Generated and legacy group IDs share the same suffix; member sets have not been compared.
- `light.fht_outside_perimeter_coach_left_lights` (1 references) / `light.outside_perimeter_coach_left_lights` (0 references). Generated and legacy group IDs share the same suffix; member sets have not been compared.
- `light.fht_outside_perimeter_coach_right_lights` (1 references) / `light.outside_perimeter_coach_right_lights` (0 references). Generated and legacy group IDs share the same suffix; member sets have not been compared.
- `light.fht_outside_perimeter_porch_lights` (7 references) / `light.outside_perimeter_porch_lights` (0 references). Generated and legacy group IDs share the same suffix; member sets have not been compared.
- `light.fht_outside_perimeter_side_yard_lights` (3 references) / `light.outside_perimeter_side_yard_lights` (0 references). Generated and legacy group IDs share the same suffix; member sets have not been compared.
- `light.fht_outside_perimeter_yard_lights` (1 references) / `light.outside_perimeter_yard_lights` (0 references). Generated and legacy group IDs share the same suffix; member sets have not been compared.
- `light.bathroom_3_all_lights` (0 references) / `light.fht_bathroom_3_all_lights` (13 references). Generated and legacy group IDs share the same suffix; member sets have not been compared.
- `light.bedroom_1_all_lights` (0 references) / `light.fht_bedroom_1_all_lights` (1 references). Generated and legacy group IDs share the same suffix; member sets have not been compared.
- `light.bedroom_4_all_lights` (0 references) / `light.fht_bedroom_4_all_lights` (1 references). Generated and legacy group IDs share the same suffix; member sets have not been compared.
- `light.bedroom_5_all_lights` (0 references) / `light.fht_bedroom_5_all_lights` (1 references). Generated and legacy group IDs share the same suffix; member sets have not been compared.
- `light.closet_1_all_lights` (0 references) / `light.fht_closet_1_all_lights` (9 references). Generated and legacy group IDs share the same suffix; member sets have not been compared.
- `light.dining_room_all_lights` (0 references) / `light.fht_dining_room_all_lights` (12 references). Generated and legacy group IDs share the same suffix; member sets have not been compared.
- `light.downstairs_hallway_all_lights` (0 references) / `light.fht_downstairs_hallway_all_lights` (19 references). Generated and legacy group IDs share the same suffix; member sets have not been compared.
- `light.entry_all_lights` (1 references) / `light.fht_entry_all_lights` (7 references). Generated and legacy group IDs share the same suffix; member sets have not been compared.
- `light.fht_pantry_all_lights` (21 references) / `light.pantry_all_lights` (0 references). Generated and legacy group IDs share the same suffix; member sets have not been compared.
- `light.fht_stairway_all_lights` (31 references) / `light.stairway_all_lights` (0 references). Generated and legacy group IDs share the same suffix; member sets have not been compared.
- `light.fht_upstairs_hallway_all_lights` (12 references) / `light.upstairs_hallway_all_lights` (0 references). Generated and legacy group IDs share the same suffix; member sets have not been compared.
- `light.bedroom_1_fan_lights` (0 references) / `light.fht_bedroom_1_fan_lights` (9 references). Generated and legacy group IDs share the same suffix; member sets have not been compared.

## Managed group definitions

Absence from this one package is not proof of deletion; external YAML includes still need review.

- `light.bathroom_1_all_lights`: not defined in the current managed light-group package; 0 references.
- `light.bathroom_1_bath_lights`: not defined in the current managed light-group package; 0 references.
- `light.bathroom_1_her_vanity_lights`: not defined in the current managed light-group package; 0 references.
- `light.bathroom_1_his_vanity_lights`: not defined in the current managed light-group package; 0 references.
- `light.bathroom_1_shower_lights`: not defined in the current managed light-group package; 0 references.
- `light.bathroom_1_toilet_lights`: not defined in the current managed light-group package; 0 references.
- `light.bathroom_1_vanity_lights`: not defined in the current managed light-group package; 0 references.
- `light.bathroom_2_all_lights`: not defined in the current managed light-group package; 0 references.
- `light.bathroom_2_shower_lights`: not defined in the current managed light-group package; 0 references.
- `light.bathroom_2_vanity_lights`: not defined in the current managed light-group package; 0 references.
- `light.bathroom_3_all_lights`: not defined in the current managed light-group package; 0 references.
- `light.bathroom_3_lights`: not defined in the current managed light-group package; 0 references.
- `light.bedroom_1_all_lights`: not defined in the current managed light-group package; 0 references.
- `light.bedroom_1_fan_lights`: not defined in the current managed light-group package; 0 references.
- `light.bedroom_2_all_lights`: not defined in the current managed light-group package; 0 references.
- `light.bedroom_2_fan_lights`: not defined in the current managed light-group package; 0 references.
- `light.bedroom_2_headboard_lights`: not defined in the current managed light-group package; 0 references.
- `light.bedroom_3_all_lights`: not defined in the current managed light-group package; 0 references.
- `light.bedroom_3_bed_lights`: not defined in the current managed light-group package; 0 references.
- `light.bedroom_3_closet_lights`: not defined in the current managed light-group package; 0 references.
- `light.bedroom_3_fan_lights`: not defined in the current managed light-group package; 0 references.
- `light.bedroom_4_all_lights`: not defined in the current managed light-group package; 0 references.
- `light.bedroom_4_fan_lights`: not defined in the current managed light-group package; 0 references.
- `light.bedroom_5_all_lights`: not defined in the current managed light-group package; 0 references.
- `light.bedroom_5_fan_lights`: not defined in the current managed light-group package; 0 references.
- `light.bedroom_6_all_lights`: not defined in the current managed light-group package; 0 references.
- `light.bedroom_6_desk_lights`: not defined in the current managed light-group package; 0 references.
- `light.bedroom_6_fan_lights`: not defined in the current managed light-group package; 0 references.
- `light.closet_1_all_lights`: not defined in the current managed light-group package; 0 references.
- `light.closet_1_lights`: not defined in the current managed light-group package; 0 references.
- `light.dining_room_all_lights`: not defined in the current managed light-group package; 0 references.
- `light.dining_room_lights`: not defined in the current managed light-group package; 0 references.
- `light.downstairs_hallway_all_lights`: not defined in the current managed light-group package; 0 references.
- `light.downstairs_hallway_lights`: not defined in the current managed light-group package; 0 references.
- `light.entry_all_lights`: not defined in the current managed light-group package; 1 references.
- `light.entry_lights`: not defined in the current managed light-group package; 0 references.
- `light.kitchen_all_lights`: not defined in the current managed light-group package; 1 references.
- `light.kitchen_1g_lights`: not defined in the current managed light-group package; 0 references.
- `light.kitchen_bar_lights`: not defined in the current managed light-group package; 0 references.
- `light.kitchen_lights`: not defined in the current managed light-group package; 0 references.
- `light.kitchen_switch_1g_load_control_lights`: not defined in the current managed light-group package; 0 references.
- `light.kitchen_switch_1g_rgb_indicator_lights`: not defined in the current managed light-group package; 0 references.
- `light.living_room_all_lights`: not defined in the current managed light-group package; 0 references.
- `light.living_room_can_lights`: not defined in the current managed light-group package; 0 references.
- `light.living_room_fan_lights`: not defined in the current managed light-group package; 0 references.
- `light.office_all_lights`: not defined in the current managed light-group package; 0 references.
- `light.outside_perimeter_all_lights`: not defined in the current managed light-group package; 0 references.
- `light.outside_perimeter_backyard_lights`: not defined in the current managed light-group package; 0 references.
- `light.outside_perimeter_coach_left_lights`: not defined in the current managed light-group package; 0 references.
- `light.outside_perimeter_coach_right_lights`: not defined in the current managed light-group package; 0 references.
- `light.outside_perimeter_porch_lights`: not defined in the current managed light-group package; 0 references.
- `light.outside_perimeter_side_yard_lights`: not defined in the current managed light-group package; 0 references.
- `light.outside_perimeter_yard_lights`: not defined in the current managed light-group package; 0 references.
- `light.pantry_all_lights`: not defined in the current managed light-group package; 0 references.
- `light.pantry_lights`: not defined in the current managed light-group package; 0 references.
- `light.stairway_all_lights`: not defined in the current managed light-group package; 0 references.
- `light.stairway_lights`: not defined in the current managed light-group package; 0 references.
- `light.upstairs_hallway_all_lights`: not defined in the current managed light-group package; 0 references.
- `light.upstairs_hallway_lights`: not defined in the current managed light-group package; 0 references.
- `light.bathroom_1_all_bathroom_lights`: not defined in the current managed light-group package; 0 references.
- `light.bathroom_2_all_bathroom_lights`: not defined in the current managed light-group package; 0 references.
- `light.bathroom_3_all_bathroom_lights`: not defined in the current managed light-group package; 0 references.
- `light.fht_bathroom_1_all_lights`: defined here, 10 direct members; 3 references.
- `light.fht_bathroom_1_all_bathroom_lights`: defined here, 8 direct members; 13 references.
- `light.fht_bathroom_1_bath_lights`: defined here, 1 direct members; 1 references.
- `light.fht_bathroom_1_her_vanity_lights`: defined here, 3 direct members; 1 references.
- `light.fht_bathroom_1_his_vanity_lights`: defined here, 3 direct members; 1 references.
- `light.fht_bathroom_1_shower_lights`: defined here, 1 direct members; 1 references.
- `light.fht_bathroom_1_toilet_lights`: defined here, 2 direct members; 13 references.
- `light.fht_bathroom_1_vanity_lights`: defined here, 6 direct members; 1 references.
- `light.fht_bathroom_2_all_lights`: defined here, 4 direct members; 1 references.
- `light.fht_bathroom_2_shower_lights`: defined here, 1 direct members; 16 references.
- `light.fht_bathroom_2_vanity_lights`: defined here, 3 direct members; 16 references.
- `light.fht_bedroom_2_all_lights`: defined here, 4 direct members; 1 references.
- `light.fht_bedroom_2_fan_lights`: defined here, 2 direct members; 10 references.
- `light.fht_bedroom_3_all_lights`: defined here, 5 direct members; 1 references.
- `light.fht_bedroom_3_bed_lights`: defined here, 1 direct members; 7 references.
- `light.fht_bedroom_3_closet_lights`: defined here, 2 direct members; 9 references.
- `light.fht_bedroom_3_fan_lights`: defined here, 2 direct members; 9 references.
- `light.fht_bedroom_6_all_lights`: defined here, 2 direct members; 1 references.
- `light.fht_kitchen_all_lights`: defined here, 11 direct members; 1 references.
- `light.fht_kitchen_bar_lights`: defined here, 3 direct members; 9 references.
- `light.fht_kitchen_lights`: defined here, 5 direct members; 15 references.
- `light.fht_living_room_all_lights`: defined here, 4 direct members; 1 references.
- `light.fht_living_room_can_lights`: defined here, 2 direct members; 9 references.
- `light.fht_living_room_fan_lights`: defined here, 2 direct members; 9 references.
- `light.fht_outside_perimeter_all_lights`: defined here, 5 direct members; 4 references.
- `light.fht_outside_perimeter_backyard_lights`: defined here, 1 direct members; 3 references.
- `light.fht_outside_perimeter_coach_left_lights`: defined here, 1 direct members; 1 references.
- `light.fht_outside_perimeter_coach_right_lights`: defined here, 1 direct members; 1 references.
- `light.fht_outside_perimeter_porch_lights`: defined here, 1 direct members; 7 references.
- `light.fht_outside_perimeter_side_yard_lights`: defined here, 1 direct members; 3 references.
- `light.fht_outside_perimeter_yard_lights`: defined here, 1 direct members; 1 references.
- `light.fht_bathroom_3_all_lights`: defined here, 3 direct members; 13 references.
- `light.fht_bedroom_1_all_lights`: defined here, 3 direct members; 1 references.
- `light.fht_bedroom_4_all_lights`: defined here, 2 direct members; 1 references.
- `light.fht_bedroom_5_all_lights`: defined here, 2 direct members; 1 references.
- `light.fht_closet_1_all_lights`: defined here, 3 direct members; 9 references.
- `light.fht_dining_room_all_lights`: defined here, 5 direct members; 12 references.
- `light.fht_downstairs_hallway_all_lights`: defined here, 1 direct members; 19 references.
- `light.fht_entry_all_lights`: defined here, 1 direct members; 7 references.
- `light.fht_pantry_all_lights`: defined here, 2 direct members; 21 references.
- `light.fht_stairway_all_lights`: defined here, 1 direct members; 31 references.
- `light.fht_upstairs_hallway_all_lights`: defined here, 2 direct members; 12 references.
- `light.fht_bathroom_3_shower_lights`: defined here, 1 direct members; 1 references.
- `light.fht_bathroom_3_vanity_lights`: defined here, 2 direct members; 1 references.
- `light.fht_bedroom_1_fan_lights`: defined here, 2 direct members; 9 references.
- `light.fht_bedroom_2_closet_lights`: defined here, 2 direct members; 10 references.
- `light.fht_outside_perimeter_coach_lights`: defined here, 2 direct members; 7 references.
- `light.fht_bedroom_1_closet_lights`: defined here, 1 direct members; 1 references.
- `light.fht_laundry_room_all_lights`: defined here, 1 direct members; 4 references.
- `light.fht_kitchen_cabinet_lights`: defined here, 2 direct members; 1 references.
- `light.fht_kitchen_rgb_lights`: defined here, 1 direct members; 1 references.
- `light.fht_kitchen_switch_rgb_lights`: defined here, 1 direct members; 1 references.
- `light.fht_kitchen_switch_under_cabinet_lights`: defined here, 1 direct members; 1 references.
- `light.fht_kitchen_under_cabinet_lights`: defined here, 1 direct members; 1 references.

## Safe migration sequence

1. Confirm the currently loaded entity IDs in Home Assistant; never delete or replace an entity solely because it is offline.
2. Compare proposed old/new groups' member sets and behavior. Retain any intentionally distinct groups.
3. Review a specific old-ID → new-ID mapping and its affected reference locations with the homeowner.
4. Back up the affected live files and private saved settings separately from the stable app archive.
5. Apply only approved references through supported dashboard/settings editors; do not write active `.storage` files directly.
6. Validate saved actions and generated YAML, then verify controls without unexpectedly activating lights, sirens, or armed modes.
