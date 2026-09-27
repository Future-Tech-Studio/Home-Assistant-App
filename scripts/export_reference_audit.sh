#!/usr/bin/env bash
set -euo pipefail

CONFIG="${1:-/config}"
OUTPUT="${2:?Provide a new output directory}"
mkdir "$OUTPUT"
chmod 700 "$OUTPUT"
umask 077
jq '{entities: [.data.entities[] | {entity_id, unique_id, platform, config_entry_id, device_id, area_id, name, original_name, disabled_by, hidden_by}]}' "$CONFIG/.storage/core.entity_registry" > "$OUTPUT/registry.json"
jq '{devices: [.data.devices[] | {id, name, name_by_user, area_id}]}' "$CONFIG/.storage/core.device_registry" > "$OUTPUT/devices.json"
jq '{entries: [.data.entries[] | select(.domain == "group") | {entry_id, title, members: (.options.entities // .data.entities // [])}]}' "$CONFIG/.storage/core.config_entries" > "$OUTPUT/groups.json"
if test -f "$CONFIG/.storage/core.restore_state"; then
  jq '[.data[] | {entity_id: .state.entity_id, state: .state.state, last_seen, members: (.state.attributes.entity_id // []), friendly_name: .state.attributes.friendly_name}]' "$CONFIG/.storage/core.restore_state" > "$OUTPUT/restored_states.json"
else
  printf '[]\n' > "$OUTPUT/restored_states.json"
fi
PATTERN='(?:light|switch|fan|climate|cover|binary_sensor|sensor|event|button|input_select|input_text|input_boolean|input_number|input_datetime|media_player|siren|scene|automation|script|alarm_control_panel|select|number|lock|timer)\.[a-z0-9_]+'
: > "$OUTPUT/references.jsonl"
for source in "$CONFIG"/.storage/lovelace "$CONFIG"/.storage/lovelace.* "$CONFIG"/packages/future_homes_tech*.json; do
  test -f "$source" || continue
  jq -c --arg source "${source#"$CONFIG"/}" --arg pattern "$PATTERN" '
    paths(scalars) as $path | getpath($path) | select(type == "string") |
    scan($pattern) | {source:$source, path:($path|map(tostring)|join("/")), entity_id:., kind:"json"}
  ' "$source" >> "$OUTPUT/references.jsonl"
done
for source in "$CONFIG"/automations.yaml "$CONFIG"/scripts.yaml "$CONFIG"/scenes.yaml "$CONFIG"/ui-lovelace.yaml "$CONFIG"/packages/future_homes_tech*.yaml; do
  test -f "$source" || continue
  jq -Rnc --arg source "${source#"$CONFIG"/}" --arg pattern "$PATTERN" '
    inputs | {line:input_line_number,text:.} |
    select(.text | test("^\\s*(-\\s*)?(#|service:|action:|unique_id:|id:)") | not) |
    .line as $line | .text | scan($pattern) |
    {source:$source,path:("line:"+($line|tostring)),entity_id:.,kind:"yaml_candidate"}
  ' "$source" >> "$OUTPUT/references.jsonl"
done
if test -f "$CONFIG/packages/future_homes_tech_light_groups.yaml"; then
  jq -Rn '[inputs | select(test("^\\s*(light:|- platform:|unique_id:|entities:|- light\\.)"))]' "$CONFIG/packages/future_homes_tech_light_groups.yaml" > "$OUTPUT/group_definition_lines.json"
fi
printf 'Read-only export complete: %s\n' "$OUTPUT"
