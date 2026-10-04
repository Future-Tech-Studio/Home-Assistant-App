"""Future Tech Portal reporting: Home Assistant pushes device status to the portal.

The App writes one Home Assistant package, ``packages/future_tech_portal.yaml``.
It reports with ``rest_command.future_tech_report`` only:

* ``script.future_tech_send_inventory`` sends every reported device in one request;
* "Future Tech - inventory" runs it 60 seconds after start and hourly at :07;
* "Future Tech - offline/online" sends device.offline after two minutes
  unavailable and device.recovered when the device returns;
* "Future Tech - low battery" sends battery.low below 20%, once per device a day;
* "Future Tech - heartbeat" sends a heartbeat every 10 minutes;
* the inventory also sends the home's automations, and "Future Tech - activity"
  reports each automation run (automation.triggered) as it happens.

Home Assistant only sends. The portal never controls a device and nothing is
opened to the internet. The portal token lives only in secrets.yaml as
``future_tech_token`` and the package reads it with ``!secret``. The App never
stores the token under /data, never logs it, and never sends it back to the
browser.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from typing import Any, Iterable

INGEST_URL = "https://futuretech.studio/api/beta/ingest"
SECRET_NAME = "future_tech_token"
PACKAGE_FILENAME = "future_tech_portal.yaml"
INVENTORY_SCRIPT = "script.future_tech_send_inventory"
STATUS_SENSOR = "sensor.future_tech_portal"
DEVICES_SENSOR = "sensor.future_tech_portal_devices"
INCLUDE_LABEL = "future_tech_report"
EXCLUDE_LABEL = "future_tech_exclude"
DEFAULT_INTEGRATIONS = (
    "unifi",
    "unifiprotect",
    "zha",
    "zwave_js",
    "matter",
    "mqtt",
    "esphome",
)
# The portal treats one inventory request as the whole device list, so all
# devices go in one request: up to its 500-device limit, and split only if
# the body would near its 256 KB limit (measured as ASCII-escaped JSON, which
# is never shorter than the UTF-8 body).
INVENTORY_CHUNK = 500
INVENTORY_MAX_CHARS = 200_000
LOW_BATTERY_PERCENT = 20
OFFLINE_DEBOUNCE_SECONDS = 120
# Changes in the first five minutes after start are start-up churn; the
# inventory sent 60 seconds after start reports those devices instead.
STARTUP_SECONDS = 300
# A burst of offline events (a Zigbee stick restarting) is spread over a
# minute per device so the portal's 120 requests a minute are not exceeded.
SPREAD_SECONDS = 60
# The status card turns red when nothing has been delivered for this long;
# heartbeats go out every 10 minutes.
STALE_AFTER_MINUTES = 15
# Integrations whose devices are Home Assistant's own, never field hardware.
INTERNAL_INTEGRATIONS = frozenset(
    {
        "automation",
        "backup",
        "group",
        "hassio",
        "homeassistant",
        "input_boolean",
        "input_button",
        "input_datetime",
        "input_number",
        "input_select",
        "input_text",
        "person",
        "scene",
        "script",
        "sun",
        "template",
        "timer",
        "zone",
    }
)
# The device's main entity, in priority order. Configuration entities
# (update, button, number, select, ...) are never the main entity.
PRIMARY_DOMAINS = (
    "lock",
    "camera",
    "alarm_control_panel",
    "climate",
    "water_heater",
    "cover",
    "valve",
    "fan",
    "humidifier",
    "vacuum",
    "lawn_mower",
    "light",
    "switch",
    "siren",
    "media_player",
    "remote",
    "binary_sensor",
    "sensor",
    "device_tracker",
)

# A device is offline when its main entity is unavailable, or, for UniFi
# Network gear whose entities stay available, when its state sensor says so.
OFFLINE_STATES = ("unavailable", "disconnected", "heartbeat_missed")
UNIFI_DEVICE_STATES = (
    "connected", "disconnected", "heartbeat_missed", "pending", "firmware_mismatch",
    "upgrading", "provisioning", "adopting", "deleting", "inform_error",
    "adoption_failed", "isolated",
)
# Helpers that wrap another integration's entity on the same device; they are
# never the device's integration.
HELPER_INTEGRATIONS = ("switch_as_x", "group", "template", "derivative", "integration",
                       "utility_meter", "min_max", "threshold", "filter", "statistics",
                       "trend", "mold_indicator", "homekit", "alexa", "google_assistant")

_TOKEN_PATTERN = re.compile(r"fts_[A-Za-z0-9_-]{8,240}")
# The URL lands in a rest_command template: no spaces, quotes or braces.
_URL_PATTERN = re.compile(r"https://[A-Za-z0-9.-]+(?::[0-9]{1,5})?(?:/[A-Za-z0-9._~%!$&'()*+,;=:@/-]*)?")
_INTEGRATION_PATTERN = re.compile(r"[a-z0-9_]{1,64}")
_SECRET_LINE = re.compile(rf"^{SECRET_NAME}\s*:(.*)$")


class PortalError(Exception):
    """A portal setup step failed; the message never contains the token."""


def normalize_token(raw: Any) -> str:
    """Return the secrets.yaml value, ``Bearer fts_...``, for a pasted token.

    The token may be pasted alone, with ``Bearer``, quoted, or as the whole
    ``future_tech_token: "Bearer fts_..."`` line. Errors never repeat it.
    """
    text = str(raw or "").strip()
    if text.startswith(f"{SECRET_NAME}:"):
        text = text[len(SECRET_NAME) + 1:].strip()
    text = text.strip("\"'").strip()
    if text[:7].casefold() == "bearer ":
        text = text[7:].strip()
    if not _TOKEN_PATTERN.fullmatch(text):
        raise PortalError(
            "Paste the token exactly as the portal shows it; it starts with fts_."
        )
    return f"Bearer {text}"


def normalize_url(raw: Any) -> str:
    """Return the report URL; blank means the portal's default address."""
    text = str(raw or "").strip()
    if not text:
        return INGEST_URL
    if len(text) > 300 or not _URL_PATTERN.fullmatch(text):
        raise PortalError("The Future Tech Portal URL must be a plain https:// address.")
    return text


def last_seen_from_history(rows: list[dict[str, Any]]) -> str | None:
    """Return when an entity was last seen online from its history rows.

    That is the moment it went unavailable after its last real state, or None
    when the history window holds no real state at all.
    """
    last_good = None
    for index, row in enumerate(rows):
        if str(row.get("state")) not in {*OFFLINE_STATES, "unknown"}:
            last_good = index
    if last_good is None:
        return None
    if last_good + 1 < len(rows):
        return str(rows[last_good + 1].get("last_changed") or "") or None
    return None


# Matter: the Network Commissioning cluster's feature flags (endpoint 0,
# cluster 49) say which network a node uses; the per-network diagnostics
# clusters (Thread 53, Wi-Fi 54, Ethernet 55) are the fallback.
_MATTER_NETWORK_BITS = ((2, "thread"), (1, "wifi"), (4, "ethernet"))
_MATTER_NETWORK_CLUSTERS = (("53", "thread"), ("54", "wifi"), ("55", "ethernet"))
_MATTER_DEVICE_IDENTIFIER = re.compile(r"deviceid_([0-9A-Fa-f]{16})-([0-9A-Fa-f]{16})-")


def matter_network(attributes: dict[str, Any]) -> str | None:
    """Return "thread", "wifi" or "ethernet" for a Matter node, if it says."""
    flags = attributes.get("0/49/65532")
    if isinstance(flags, int) and not isinstance(flags, bool):
        for bit, network in _MATTER_NETWORK_BITS:
            if flags & bit:
                return network
    for cluster, network in _MATTER_NETWORK_CLUSTERS:
        if any(str(path).startswith(f"0/{cluster}/") for path in attributes):
            return network
    return None


def matter_networks(device_registry: dict[str, Any], diagnostics: dict[str, Any]) -> dict[str, str]:
    """Map Home Assistant Matter device IDs to their network from diagnostics."""
    server = ((diagnostics.get("data") or {}).get("server") or {}) if isinstance(diagnostics, dict) else {}
    by_node: dict[int, str] = {}
    for node in server.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        network = matter_network(node.get("attributes") or {})
        if network is not None and isinstance(node.get("node_id"), int):
            by_node[node["node_id"]] = network
    result: dict[str, str] = {}
    for device in (device_registry.get("data") or {}).get("devices") or []:
        for identifier in device.get("identifiers") or []:
            if not (isinstance(identifier, list) and len(identifier) == 2 and identifier[0] == "matter"):
                continue
            match = _MATTER_DEVICE_IDENTIFIER.match(str(identifier[1]))
            # Bridged devices share their bridge's node, and so its network.
            if match and int(match.group(2), 16) in by_node:
                result[str(device.get("id"))] = by_node[int(match.group(2), 16)]
                break
    return result


def token_configured(secrets: str) -> bool:
    """Return whether secrets.yaml holds a non-empty portal token."""
    for line in secrets.splitlines():
        match = _SECRET_LINE.match(line)
        if match:
            value = match.group(1).split(" #", 1)[0].strip().strip("\"'").strip()
            return bool(value)
    return False


def _secret_lines(secrets: str) -> tuple[list[str], list[int]]:
    lines = secrets.splitlines(keepends=True)
    matches = [index for index, line in enumerate(lines) if _SECRET_LINE.match(line)]
    if len(matches) > 1:
        raise PortalError(f"secrets.yaml has more than one {SECRET_NAME} entry.")
    for index in matches:
        value = _SECRET_LINE.match(lines[index]).group(1).strip()
        if value[:1] in {"|", ">"}:
            raise PortalError(
                f"secrets.yaml stores {SECRET_NAME} on several lines; "
                "replace it with one line before saving here."
            )
    return lines, matches


def with_token(secrets: str, value: str) -> str:
    """Add or replace the portal token line; every other line is kept."""
    lines, matches = _secret_lines(secrets)
    # A JSON string is a valid YAML double-quoted scalar.
    line = f"{SECRET_NAME}: {json.dumps(value)}\n"
    if matches:
        lines[matches[0]] = line
        return "".join(lines)
    separator = "" if not secrets or secrets.endswith("\n") else "\n"
    return f"{secrets}{separator}{line}"


def without_token(secrets: str) -> str:
    """Remove the portal token line; every other line is kept."""
    lines, matches = _secret_lines(secrets)
    for index in reversed(matches):
        del lines[index]
    return "".join(lines)


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def write_private_text(path: Path, content: str) -> None:
    """Atomically replace secrets.yaml, keeping its mode (new files are 0600).

    No backup copy is kept, so an old or revoked token is not left behind.
    """
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except FileNotFoundError:
        mode = 0o600
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_path, mode)
        os.replace(temporary_path, path)
    except OSError as err:
        # The error names the file only; the content is never part of it.
        raise PortalError(f"Unable to write {path.name}.") from err
    finally:
        temporary_path.unlink(missing_ok=True)


def normalize_integrations(values: Any) -> list[str]:
    """Return valid, unique integration domains in the given order."""
    if values is None:
        return list(DEFAULT_INTEGRATIONS)
    if not isinstance(values, list):
        raise ValueError("Integrations must be a list.")
    result: list[str] = []
    for value in values:
        domain = str(value or "").strip().casefold()
        if not domain:
            continue
        if not _INTEGRATION_PATTERN.fullmatch(domain):
            raise ValueError("Integrations must be Home Assistant integration names.")
        if domain not in result:
            result.append(domain)
    return result


def integrations_with_devices(config_directory: Path) -> dict[str, int]:
    """Count enabled devices per integration from Home Assistant's registries."""
    try:
        payload = json.loads(
            (config_directory / ".storage" / "core.entity_registry").read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return {}
    devices: dict[str, set[str]] = {}
    for entry in payload.get("data", {}).get("entities", []) if isinstance(payload, dict) else []:
        if not isinstance(entry, dict) or entry.get("disabled_by"):
            continue
        platform = str(entry.get("platform") or "")
        device_id = str(entry.get("device_id") or "")
        if not device_id or not _INTEGRATION_PATTERN.fullmatch(platform):
            continue
        if platform in INTERNAL_INTEGRATIONS:
            continue
        devices.setdefault(platform, set()).add(device_id)
    return {platform: len(ids) for platform, ids in sorted(devices.items())}


def _parse_time(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or ""))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def describe_status(
    status_state: dict[str, Any] | None,
    devices_state: dict[str, Any] | None,
    *,
    token_saved: bool,
    enabled: bool,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Summarize the package's status sensors for the settings page."""
    now = now or datetime.now(timezone.utc)
    attributes = (status_state or {}).get("attributes") or {}
    state = str((status_state or {}).get("state") or "")
    if state in {"", "unknown", "unavailable"}:
        state = ""
    last_success = _parse_time(attributes.get("last_success"))
    last_attempt = _parse_time(attributes.get("last_attempt"))
    devices_attributes = (devices_state or {}).get("attributes") or {}
    try:
        device_count = int((devices_state or {}).get("state"))
    except (TypeError, ValueError):
        device_count = None
    fresh = bool(
        last_success
        and (now - last_success).total_seconds() <= STALE_AFTER_MINUTES * 60
    )
    if not token_saved:
        connection = "not_set_up"
    elif not enabled:
        connection = "paused"
    elif bool(attributes.get("paused")):
        connection = "rejected"
    elif not state:
        connection = "waiting"
    elif fresh and bool(attributes.get("ok")):
        connection = "connected"
    else:
        connection = "disconnected"
    http_status = int(state) if state.isdigit() else None
    return {
        "connection": connection,
        "http_status": http_status,
        "last_result": state,
        "last_kind": str(attributes.get("kind") or ""),
        "last_attempt": last_attempt.isoformat() if last_attempt else "",
        "last_success": last_success.isoformat() if last_success else "",
        "last_inventory": str(attributes.get("last_inventory") or ""),
        "device_count": device_count,
        "monitored_count": len(devices_attributes.get("monitored") or []),
    }


# --- Home Assistant package ------------------------------------------------
#
# Jinja braces make f-strings unreadable, so the YAML below uses __NAME__
# placeholders. Every result step is generated by _send_steps so the
# inventory, events, battery and heartbeat paths report errors the same way.

_SEND_STEPS = """\
- variables:
    portal_response: null
- action: rest_command.future_tech_report
  data:
    payload: >-
      __PAYLOAD__
  response_variable: portal_response
  continue_on_error: true
- variables:
    portal_status: >-
      {{ portal_response.status if portal_response is mapping
         and portal_response.status is number else 'no response' }}
__AFTER_SEND__- event: future_tech_portal_result
  event_data:
    kind: __KIND__
    status: "{{ portal_status }}"
- if:
    - condition: template
      value_template: "{{ portal_status is number and 200 <= portal_status < 300 }}"
  then:
    - action: persistent_notification.dismiss
      data:
        notification_id: future_tech_portal_error
  else:
    # Status code only: never the token and never the payload.
    - action: persistent_notification.create
      data:
        notification_id: future_tech_portal_error
        title: Future Tech Portal
        message: >-
          {{ 'Report failed: HTTP ' ~ portal_status if portal_status is number
             else 'Report failed: no response from the portal' }}
    - stop: Future Tech Portal report failed
"""

_EVENT_PAYLOAD = "{{ {'kind': 'events', 'events': [portal_event]} | to_json }}"
_AUTOMATIONS_PAYLOAD = "{{ {'kind': 'automations', 'automations': repeat.item} | to_json }}"
_INVENTORY_PAYLOAD = "{{ {'kind': 'inventory', 'devices': repeat.item} | to_json }}"

# Battery and offline reports are not repeated after a 4xx answer. A 429, a
# 5xx or no answer leaves the battery unmarked so the next reading tries again.
_MARK_BATTERY = """\
- if:
    - condition: template
      value_template: >-
        {{ portal_status is number and portal_status != 429 and portal_status < 500 }}
  then:
    - event: future_tech_portal_battery_reported
      event_data:
        external_id: "{{ device }}"
    - wait_template: "{{ battery_key in (state_attr('__DEVICES_SENSOR__', 'battery_reported') or []) }}"
      timeout: 5
      continue_on_timeout: true
"""

_NOT_PAUSED = (
    "{{ not is_state_attr('__STATUS_SENSOR__', 'paused', true) }}"
)


def _indent(text: str, spaces: int) -> str:
    prefix = " " * spaces
    return "".join(
        f"{prefix}{line}" if line.strip() else line
        for line in text.splitlines(keepends=True)
    )


def _send_steps(kind: str, payload: str, spaces: int, after_send: str = "") -> str:
    steps = (
        _SEND_STEPS.replace("__PAYLOAD__", payload)
        .replace("__KIND__", kind)
        .replace("__AFTER_SEND__", after_send)
    )
    return _indent(steps, spaces)


_PRIMARY_PICK = """\
{%- set pick = namespace(entity=none) -%}
{%- set own = entities | reject('in', helper_entities) | list -%}
{%- set entities = own if own else entities -%}
{%- set unifi_state = entities | select('match', 'sensor[.].*_state$') | select('is_state', unifi_device_states) | list -%}
{%- if unifi_state -%}{%- set pick.entity = unifi_state[0] -%}{%- endif -%}
{%- for domain in primary_domains -%}
  {%- if pick.entity is none -%}
    {%- set matches = entities | select('match', domain ~ '[.]') | list -%}
    {%- if domain == 'sensor' -%}
      {%- set matches = (matches | reject('is_state_attr', 'device_class', 'battery') | list)
        + (matches | select('is_state_attr', 'device_class', 'battery') | list) -%}
    {%- endif -%}
    {%- if matches -%}{%- set pick.entity = matches[0] -%}{%- endif -%}
  {%- endif -%}
{%- endfor -%}"""

_PACKAGE = """\
# Managed by Future Homes Tech App: Future Tech Portal reporting.
# Change it in the App under Settings > Home Configurator > Future Tech Portal; edits here are
# replaced. Home Assistant only pushes device status to the portal over HTTPS.
# It accepts no commands from the portal and opens nothing to the internet.
# The token is read from secrets.yaml (future_tech_token) and is never here.
# Reported: devices of __INTEGRATION_LIST__,
# plus devices labeled __INCLUDE_LABEL__; devices or entities labeled
# __EXCLUDE_LABEL__ are left out. Disabled devices and entities are skipped.

rest_command:
  future_tech_report:
    url: "__INGEST_URL__"
    method: post
    headers:
      authorization: !secret __SECRET_NAME__
    content_type: "application/json"
    # Callers pass JSON text; a mapping is encoded here as a fallback.
    payload: "{{ payload if payload is string else payload | to_json }}"
    timeout: 20
    verify_ssl: true

template:
  - triggers:
      - trigger: event
        event_type: future_tech_portal_result
    sensor:
      - name: "Future Tech Portal"
        unique_id: future_tech_portal_status
        icon: mdi:cloud-upload-outline
        state: "{{ trigger.event.data.status }}"
        attributes:
          kind: "{{ trigger.event.data.kind }}"
          ok: >-
            {{ trigger.event.data.status is number
               and 200 <= trigger.event.data.status < 300 }}
          # A rejected token (401/403) pauses automatic reports until a new
          # token is saved or an inventory is sent by hand.
          paused: >-
            {%- set status = trigger.event.data.status -%}
            {{ status in [401, 403]
               or (not (status is number and 200 <= status < 300)
                   and this.attributes.paused | default(false) is true) }}
          last_attempt: "{{ now().isoformat() }}"
          last_success: >-
            {%- set status = trigger.event.data.status -%}
            {{ now().isoformat() if status is number and 200 <= status < 300
               else this.attributes.last_success | default('') }}
          last_inventory: >-
            {%- set status = trigger.event.data.status -%}
            {{ now().isoformat() if trigger.event.data.kind == 'inventory'
               and status is number and 200 <= status < 300
               else this.attributes.last_inventory | default('') }}
  - triggers:
      - trigger: event
        event_type: future_tech_portal_devices
        id: devices
      - trigger: event
        event_type: future_tech_portal_battery_reported
        id: battery
      - trigger: event
        event_type: future_tech_portal_last_seen
        id: last_seen
      - trigger: event
        event_type: future_tech_portal_networks
        id: networks
    sensor:
      # The main entity of every reported device, refreshed by each inventory,
      # so the offline/online automation follows new and removed devices.
      - name: "Future Tech Portal devices"
        unique_id: future_tech_portal_devices
        icon: mdi:devices
        state: >-
          {{ trigger.event.data.monitored | count if trigger.id == 'devices'
             else this.state | int(0) }}
        attributes:
          monitored: >-
            {{ trigger.event.data.monitored if trigger.id == 'devices'
               else this.attributes.monitored | default([]) }}
          battery_reported: >-
            {%- set today = now().date() | string -%}
            {%- set kept = this.attributes.battery_reported | default([])
                | select('search', '@' ~ today ~ '$') | list -%}
            {{ kept + [trigger.event.data.external_id ~ '@' ~ today]
               if trigger.id == 'battery' else kept }}
          # Matter devices' network (thread, wifi, ethernet), from the App.
          networks: >-
            {{ trigger.event.data.networks | default({}) if trigger.id == 'networks'
               else this.attributes.networks | default({}) }}
          # When each offline device was last seen online. Kept across
          # restarts (a restart resets "last changed"); filled when a device
          # drops off and, for devices already offline, from Home Assistant's
          # history by the App. Each inventory drops devices back online.
          last_seen: >-
            {%- set current = this.attributes.last_seen | default({}) -%}
            {%- if trigger.id == 'devices' -%}
              {%- set keep = trigger.event.data.offline | default([]) -%}
              {%- set kept = namespace(map={}) -%}
              {%- for key, value in current.items() if key in keep -%}
                {%- set kept.map = dict(kept.map, **{key: value}) -%}
              {%- endfor -%}
              {{ kept.map }}
            {%- elif trigger.id == 'last_seen' -%}
              {{ dict(current, **(trigger.event.data.last_seen | default({}))) }}
            {%- else -%}
              {{ current }}
            {%- endif -%}

script:
  future_tech_send_inventory:
    alias: "Future Tech - send inventory"
    description: >-
      Sends the device inventory to the Future Tech Portal. Report only: it
      never controls a device.
    icon: mdi:cloud-upload-outline
    mode: single
    max_exceeded: silent
    sequence:
      - variables:
          monitored: >-
            {%- set integrations = __INTEGRATIONS__ -%}
            {%- set primary_domains = __PRIMARY_DOMAINS__ -%}
            {%- set excluded_devices = label_devices('__EXCLUDE_LABEL__') -%}
            {%- set excluded_entities = label_entities('__EXCLUDE_LABEL__') -%}
            {%- set unifi_device_states = __UNIFI_DEVICE_STATES__ -%}
            {%- set helper_entities = namespace(ids=[]) -%}
            {%- for helper in __HELPER_INTEGRATIONS__ -%}
              {%- set helper_entities.ids = helper_entities.ids + (integration_entities(helper) | list) -%}
            {%- endfor -%}
            {%- set helper_entities = helper_entities.ids -%}
            {%- set found = namespace(devices=[]) -%}
            {%- for integration in integrations -%}
              {%- for entity_id in integration_entities(integration) -%}
                {%- set device = device_id(entity_id) -%}
                {#- UniFi Network also creates a device for every client; report only Ubiquiti gear. -#}
                {%- if device and device not in found.devices
                    and (integration != 'unifi'
                         or 'ubiquiti' in (device_attr(device, 'manufacturer') or '') | lower) -%}
                  {%- set found.devices = found.devices + [device] -%}
                {%- endif -%}
              {%- endfor -%}
            {%- endfor -%}
            {%- for device in label_devices('__INCLUDE_LABEL__') -%}
              {%- if device not in found.devices -%}
                {%- set found.devices = found.devices + [device] -%}
              {%- endif -%}
            {%- endfor -%}
            {%- set result = namespace(entities=[]) -%}
            {%- for device in found.devices -%}
              {%- if device not in excluded_devices and device_attr(device, 'disabled_by') is none -%}
                {%- set entities = device_entities(device) | reject('in', excluded_entities) | list -%}
__PRIMARY_PICK__
                {%- if pick.entity is not none -%}
                  {%- set result.entities = result.entities + [pick.entity] -%}
                {%- endif -%}
              {%- endif -%}
            {%- endfor -%}
            {#- An entity without a device is reported only when labeled. -#}
            {%- for entity_id in label_entities('__INCLUDE_LABEL__') -%}
              {%- if device_id(entity_id) is none and entity_id not in excluded_entities
                  and states[entity_id] is not none and entity_id not in result.entities -%}
                {%- set result.entities = result.entities + [entity_id] -%}
              {%- endif -%}
            {%- endfor -%}
            {{ result.entities }}
      - event: future_tech_portal_devices
        event_data:
          monitored: "{{ monitored }}"
          offline: "{{ monitored | select('is_state', __OFFLINE_STATES__) | list }}"
      - variables:
          devices: >-
            {%- set primary_domains = __PRIMARY_DOMAINS__ -%}
            {%- set last_seen_map = state_attr('__DEVICES_SENSOR__', 'last_seen') or {} -%}
            {%- set network_map = state_attr('__DEVICES_SENSOR__', 'networks') or {} -%}
            {%- set network = integration_entities('unifi') | map('device_id') | reject('none') | unique | list -%}
            {%- set hubs = monitored | map('device_id') | reject('none')
                | map('device_attr', 'via_device_id') | reject('none') | unique | list -%}
            {%- set out = namespace(items=[]) -%}
            {%- for entity_id in monitored -%}
              {%- set device = device_id(entity_id) -%}
              {%- set entities = device_entities(device) if device else [entity_id] -%}
              {%- set name = (device_attr(device, 'name_by_user') or device_attr(device, 'name')) if device else none -%}
              {%- set name = (name or state_attr(entity_id, 'friendly_name') or entity_id) | string -%}
              {%- set model = ((device_attr(device, 'model') or '') if device else '') | string -%}
              {%- set domains = entities | map('regex_replace', '[.].*$', '') | unique | select('in', primary_domains) | list -%}
              {%- set text = (name ~ ' ' ~ model) | lower -%}
              {%- if device and device in network -%}
                {%- set category = 'network' -%}
              {%- elif 'lock' in domains or text is search('doorbell|intercom|door ?station|keypad|access(?! ?point)') -%}
                {%- set category = 'access' -%}
              {%- elif 'camera' in domains -%}
                {%- set category = 'camera' -%}
              {%- elif (device and device in hubs)
                  or text is search('\\\\bhub\\\\b|bridge|coordinator|gateway|\\\\bnvr\\\\b|cloud ?key|dream ?machine|base ?station') -%}
                {%- set category = 'hub' -%}
              {%- elif domains and domains | reject('in', ['sensor', 'binary_sensor']) | list | count == 0 -%}
                {%- set category = 'sensor' -%}
              {%- else -%}
                {%- set category = 'other' -%}
              {%- endif -%}
              {%- set entry = namespace(item={
                  'externalId': device or entity_id,
                  'name': name[:100],
                  'category': category,
                  'online': not is_state(entity_id, __OFFLINE_STATES__),
                }) -%}
              {#- Online: seen now. Offline: when it was last seen online, if known. -#}
              {%- if not is_state(entity_id, __OFFLINE_STATES__) -%}
                {%- set entry.item = dict(entry.item, lastSeenAt=now().isoformat()) -%}
              {%- elif last_seen_map[entity_id] is defined -%}
                {%- set entry.item = dict(entry.item, lastSeenAt=last_seen_map[entity_id]) -%}
              {%- endif -%}
              {%- for key, attribute, size in [('manufacturer', 'manufacturer', 60), ('model', 'model', 60),
                  ('hardware', 'hw_version', 40), ('firmware', 'sw_version', 40)] -%}
                {%- set value = device_attr(device, attribute) if device else none -%}
                {%- if value -%}
                  {%- set entry.item = dict(entry.item, **{key: (value | string)[:size]}) -%}
                {%- endif -%}
              {%- endfor -%}
              {#- The integration that created the device (never a helper such as Switch as X
                  wrapping its switch), plus every other integration on the device. -#}
              {%- set helpers = __HELPER_INTEGRATIONS__ -%}
              {%- set entries = (device_attr(device, 'config_entries') or []) | list if device else [] -%}
              {%- set primary_entry = config_entry_id(entity_id) -%}
              {%- if not device and primary_entry -%}{%- set entries = [primary_entry] -%}{%- endif -%}
              {%- set candidates = [device_attr(device, 'primary_config_entry') if device else none, primary_entry] + entries -%}
              {%- set chosen = namespace(entry=none) -%}
              {%- for candidate in candidates -%}
                {%- if chosen.entry is none and candidate and config_entry_attr(candidate, 'domain')
                    and config_entry_attr(candidate, 'domain') not in helpers -%}
                  {%- set chosen.entry = candidate -%}
                {%- endif -%}
              {%- endfor -%}
              {%- set integrations = entries | map('config_entry_attr', 'domain') | reject('none') | reject('in', helpers) | unique | sort | list -%}
              {%- if chosen.entry -%}
                {%- set entry.item = dict(entry.item, integration=config_entry_attr(chosen.entry, 'domain')) -%}
                {%- set title = config_entry_attr(chosen.entry, 'title') -%}
                {%- if title -%}
                  {%- set entry.item = dict(entry.item, integrationName=(title | string)[:80]) -%}
                {%- endif -%}
              {%- endif -%}
              {%- if device and network_map[device] is defined -%}
                {%- set entry.item = dict(entry.item, network=network_map[device]) -%}
              {%- endif -%}
              {%- if integrations | count > 1 -%}
                {%- set entry.item = dict(entry.item, integrations=integrations) -%}
              {%- endif -%}
              {%- set updates = entities | select('match', 'update[.]') | list -%}
              {%- if updates | select('is_state', 'on') | list -%}
                {%- set entry.item = dict(entry.item, firmwareUpdateAvailable=true) -%}
              {%- elif updates | select('is_state', 'off') | list -%}
                {%- set entry.item = dict(entry.item, firmwareUpdateAvailable=false) -%}
              {%- endif -%}
              {%- set battery = namespace(value=none) -%}
              {%- for sensor in entities | select('match', 'sensor[.]') | select('is_state_attr', 'device_class', 'battery') -%}
                {%- if battery.value is none and states(sensor) | is_number -%}
                  {%- set battery.value = [[states(sensor) | float, 0] | max, 100] | min | round | int -%}
                {%- endif -%}
              {%- endfor -%}
              {%- if battery.value is not none -%}
                {%- set entry.item = dict(entry.item, battery=battery.value) -%}
              {%- endif -%}
              {%- set out.items = out.items + [entry.item] -%}
            {%- endfor -%}
            {{ out.items }}
      - repeat:
          for_each: >-
            {%- set acc = namespace(chunks=[], current=[], size=0) -%}
            {%- for item in devices -%}
              {%- set length = (item | to_json(ensure_ascii=true) | length) + 1 -%}
              {%- if acc.current and (acc.current | count >= __CHUNK__ or acc.size + length > __MAX_CHARS__) -%}
                {%- set acc.chunks = acc.chunks + [acc.current] -%}
                {%- set acc.current = [] -%}
                {%- set acc.size = 0 -%}
              {%- endif -%}
              {%- set acc.current = acc.current + [item] -%}
              {%- set acc.size = acc.size + length -%}
            {%- endfor -%}
            {{ acc.chunks + ([acc.current] if acc.current else []) }}
          sequence:
__INVENTORY_SEND__
            - if:
                - condition: template
                  value_template: "{{ not repeat.last }}"
              then:
                - delay: 1
      # The automations in this home, for the portal's activity view. Each
      # run is reported as it happens by "Future Tech - activity".
      - variables:
          automations: >-
            {%- set out = namespace(items=[]) -%}
            {%- for automation in states.automation | sort(attribute='entity_id') -%}
              {%- set config_id = (automation.attributes.id | default('')) | string -%}
              {%- if not config_id.startswith('future_tech_portal_') -%}
                {%- set entry = namespace(item={
                    'automationId': automation.entity_id,
                    'name': (automation.attributes.friendly_name | default(automation.entity_id) | string)[:120],
                    'enabled': automation.state == 'on',
                  }) -%}
                {%- if config_id -%}
                  {%- set entry.item = dict(entry.item, configId=config_id[:80]) -%}
                {%- endif -%}
                {%- if automation.attributes.last_triggered -%}
                  {%- set entry.item = dict(entry.item, lastTriggeredAt=as_datetime(automation.attributes.last_triggered).isoformat()) -%}
                {%- endif -%}
                {%- set out.items = out.items + [entry.item] -%}
              {%- endif -%}
            {%- endfor -%}
            {{ out.items }}
      - repeat:
          for_each: "{{ automations | batch(__CHUNK__) | list }}"
          sequence:
__AUTOMATIONS_SEND__

automation:
  - id: future_tech_portal_inventory
    alias: "Future Tech - inventory"
    description: Sends the device inventory to the Future Tech Portal at start and hourly.
    mode: single
    max_exceeded: silent
    triggers:
      - trigger: homeassistant
        event: start
        id: start
      - trigger: time_pattern
        minutes: 7
        id: hourly
    conditions:
      - condition: template
        value_template: >-
          {{ trigger.id == 'start' or not is_state_attr('__STATUS_SENSOR__', 'paused', true) }}
    actions:
      - if:
          - condition: trigger
            id: start
        then:
          - delay: 60
      - action: script.future_tech_send_inventory

  - id: future_tech_portal_offline_online
    alias: "Future Tech - offline/online"
    description: >-
      Reports a reported device's main entity going unavailable for two
      minutes (device.offline) and coming back (device.recovered). The device
      list maintains itself from each inventory.
    mode: parallel
    max: 500
    max_exceeded: silent
    trace:
      stored_traces: 3
    triggers:
      - trigger: event
        event_type: state_changed
    conditions:
      - condition: template
        value_template: >-
          {%- set old = trigger.event.data.old_state -%}
          {%- set new = trigger.event.data.new_state -%}
          {{ old is not none and new is not none
             and (old.state in __OFFLINE_STATES__) != (new.state in __OFFLINE_STATES__)
             and trigger.event.data.entity_id
                 in (state_attr('__DEVICES_SENSOR__', 'monitored') or [])
             and __NOT_PAUSED_EXPR__ }}
    actions:
      - variables:
          entity_id: "{{ trigger.event.data.entity_id }}"
          external_id: "{{ device_id(trigger.event.data.entity_id) or trigger.event.data.entity_id }}"
          went_offline: "{{ trigger.event.data.new_state.state in __OFFLINE_STATES__ }}"
          # Start-up churn: ignore changes in the first five minutes after the
          # automation started; the inventory sent at start reports them.
          started: "{{ as_timestamp(this.last_changed) }}"
          changed: "{{ as_timestamp(trigger.event.data.new_state.last_changed) }}"
          since: "{{ as_timestamp(trigger.event.data.old_state.last_changed) }}"
          spread: >-
            {{ (external_id[-2:] | int(0, 16)) % __SPREAD__
               if external_id is match('[0-9a-f]{32}$') else 0 }}
          portal_event:
            eventId: "{{ (trigger.event.data.new_state.context.id ~ '-' ~ external_id)[:128] }}"
            type: "{{ 'device.offline' if went_offline else 'device.recovered' }}"
            externalId: "{{ external_id }}"
            occurredAt: "{{ trigger.event.data.new_state.last_changed.isoformat() }}"
            # The last time the device reported before it dropped off; for a
            # recovery, now.
            lastSeenAt: >-
              {{ (trigger.event.data.old_state.last_reported
                  | default(trigger.event.data.old_state.last_updated)).isoformat()
                 if went_offline else trigger.event.data.new_state.last_changed.isoformat() }}
      - choose:
          - conditions:
              - condition: template
                value_template: "{{ went_offline and changed - started > __STARTUP__ }}"
            sequence:
              # Debounce: report only after two minutes still unavailable.
              - wait_template: "{{ not is_state(entity_id, __OFFLINE_STATES__) }}"
                timeout: __DEBOUNCE__
                continue_on_timeout: true
              - condition: template
                value_template: "{{ not wait.completed }}"
              - delay:
                  seconds: "{{ spread }}"
              - condition: template
                value_template: "{{ is_state(entity_id, __OFFLINE_STATES__) }}"
              - event: future_tech_portal_last_seen
                event_data:
                  last_seen: "{{ {entity_id: portal_event.lastSeenAt} }}"
__OFFLINE_SEND__
          - conditions:
              # Only devices that were reported offline: unavailable for at
              # least two minutes, starting after the start-up window.
              - condition: template
                value_template: >-
                  {{ not went_offline and changed - since >= __DEBOUNCE__
                     and since - started > __STARTUP__ }}
            sequence:
              - delay:
                  seconds: "{{ spread }}"
__RECOVERED_SEND__

  - id: future_tech_portal_low_battery
    alias: "Future Tech - low battery"
    description: >-
      Reports a battery below __LOW_BATTERY__% on a reported device, at most once
      per device per day.
    mode: queued
    max: 100
    max_exceeded: silent
    trace:
      stored_traces: 3
    triggers:
      - trigger: event
        event_type: state_changed
    conditions:
      - condition: template
        value_template: >-
          {%- set new = trigger.event.data.new_state -%}
          {{ trigger.event.data.entity_id.startswith('sensor.')
             and new is not none
             and new.attributes.device_class | default('') == 'battery'
             and new.state | is_number
             and new.state | float < __LOW_BATTERY__
             and device_id(trigger.event.data.entity_id) is not none
             and device_id(trigger.event.data.entity_id)
                 in (state_attr('__DEVICES_SENSOR__', 'monitored') or []) | map('device_id') | list
             and __NOT_PAUSED_EXPR__ }}
    actions:
      - variables:
          device: "{{ device_id(trigger.event.data.entity_id) }}"
          battery_key: "{{ device ~ '@' ~ (now().date() | string) }}"
          portal_event:
            eventId: "{{ (trigger.event.data.new_state.context.id ~ '-' ~ device)[:128] }}"
            type: battery.low
            externalId: "{{ device }}"
            occurredAt: "{{ trigger.event.data.new_state.last_changed.isoformat() }}"
            batteryPercent: >-
              {{ [[trigger.event.data.new_state.state | float, 0] | max, 100] | min | round | int }}
      # Checked again here: queued runs wait for the one before to finish.
      - condition: template
        value_template: >-
          {{ battery_key not in (state_attr('__DEVICES_SENSOR__', 'battery_reported') or []) }}
__BATTERY_SEND__

  - id: future_tech_portal_activity
    alias: "Future Tech - activity"
    description: >-
      Reports every automation run to the Future Tech Portal as it happens
      (automation.triggered). The portal's own automations are left out.
    # One at a time with a short gap: at most about 120 reports a minute.
    mode: queued
    max: 200
    max_exceeded: silent
    trace:
      stored_traces: 3
    triggers:
      - trigger: event
        event_type: automation_triggered
    conditions:
      - condition: template
        value_template: >-
          {{ not ((state_attr(trigger.event.data.entity_id, 'id') or '') | string).startswith('future_tech_portal_')
             and __NOT_PAUSED_EXPR__ }}
    actions:
      - variables:
          portal_event:
            eventId: "{{ trigger.event.context.id }}"
            type: automation.triggered
            occurredAt: "{{ trigger.event.time_fired.isoformat() }}"
            automationId: "{{ trigger.event.data.entity_id }}"
            name: "{{ (trigger.event.data.name | default(trigger.event.data.entity_id) | string)[:120] }}"
            source: "{{ (trigger.event.data.source | default('') | string)[:200] }}"
__ACTIVITY_SEND__
      - delay:
          milliseconds: 500

  - id: future_tech_portal_heartbeat
    alias: "Future Tech - heartbeat"
    description: Tells the Future Tech Portal every 10 minutes that this Home Assistant is reporting.
    mode: single
    max_exceeded: silent
    triggers:
      - trigger: time_pattern
        minutes: /10
    conditions:
      - condition: template
        value_template: "__NOT_PAUSED__"
    actions:
      - variables:
          portal_event:
            eventId: "hb-{{ now().timestamp() | int }}"
            type: heartbeat
            occurredAt: "{{ now().isoformat() }}"
__HEARTBEAT_SEND__
"""


def render_package(integrations: Iterable[str], url: str = INGEST_URL) -> str:
    """Return the Home Assistant package for the chosen integrations."""
    domains = normalize_integrations(list(integrations))
    url = normalize_url(url)
    not_paused = _NOT_PAUSED.replace("__STATUS_SENSOR__", STATUS_SENSOR)
    not_paused_expr = not_paused[3:-3].strip()
    replacements = {
        "__INVENTORY_SEND__": _send_steps("inventory", _INVENTORY_PAYLOAD, 12).rstrip("\n"),
        "__OFFLINE_SEND__": _send_steps("events", _EVENT_PAYLOAD, 14).rstrip("\n"),
        "__RECOVERED_SEND__": _send_steps("events", _EVENT_PAYLOAD, 14).rstrip("\n"),
        "__BATTERY_SEND__": _send_steps("events", _EVENT_PAYLOAD, 6, _MARK_BATTERY).rstrip("\n"),
        "__HEARTBEAT_SEND__": _send_steps("events", _EVENT_PAYLOAD, 6).rstrip("\n"),
        "__ACTIVITY_SEND__": _send_steps("events", _EVENT_PAYLOAD, 6).rstrip("\n"),
        "__AUTOMATIONS_SEND__": _send_steps("automations", _AUTOMATIONS_PAYLOAD, 12).rstrip("\n"),
        "__PRIMARY_PICK__": _indent(_PRIMARY_PICK, 16),
        "__INTEGRATION_LIST__": ", ".join(domains) if domains else "no integrations",
        "__INTEGRATIONS__": json.dumps(domains),
        "__PRIMARY_DOMAINS__": json.dumps(list(PRIMARY_DOMAINS)),
        "__NOT_PAUSED_EXPR__": not_paused_expr,
        "__NOT_PAUSED__": not_paused,
        "__STATUS_SENSOR__": STATUS_SENSOR,
        "__DEVICES_SENSOR__": DEVICES_SENSOR,
        "__INCLUDE_LABEL__": INCLUDE_LABEL,
        "__EXCLUDE_LABEL__": EXCLUDE_LABEL,
        "__INGEST_URL__": url,
        "__SECRET_NAME__": SECRET_NAME,
        "__CHUNK__": str(INVENTORY_CHUNK),
        "__MAX_CHARS__": str(INVENTORY_MAX_CHARS),
        "__SPREAD__": str(SPREAD_SECONDS),
        "__DEBOUNCE__": str(OFFLINE_DEBOUNCE_SECONDS),
        "__STARTUP__": str(STARTUP_SECONDS),
        "__OFFLINE_STATES__": json.dumps(list(OFFLINE_STATES)).replace('"', "'"),
        "__UNIFI_DEVICE_STATES__": json.dumps(list(UNIFI_DEVICE_STATES)),
        "__HELPER_INTEGRATIONS__": json.dumps(list(HELPER_INTEGRATIONS)),
        "__LOW_BATTERY__": str(LOW_BATTERY_PERCENT),
    }
    text = _PACKAGE
    # Send steps first: they carry placeholders of their own.
    for key, value in replacements.items():
        text = text.replace(key, value)
    leftover = re.search(r"__[A-Z_]+__", text)
    if leftover:
        raise AssertionError(f"Unfilled package placeholder {leftover.group(0)}")
    return text
