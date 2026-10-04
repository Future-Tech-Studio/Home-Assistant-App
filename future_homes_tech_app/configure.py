#!/usr/bin/env python3
"""Manage the Future Homes Tech Home Assistant YAML configuration."""

from __future__ import annotations

import importlib.util
import json
import ipaddress
import os
from pathlib import Path
import re
import secrets as secret_generator
import shutil
import stat
import tempfile
from urllib.parse import urlsplit

_site_spec = importlib.util.spec_from_file_location("fht_site", Path(__file__).with_name("fht_site.py"))
SITE = importlib.util.module_from_spec(_site_spec)
_site_spec.loader.exec_module(SITE)
SITE_PROFILE = SITE.load_site_profile()

COMMAND_NAME = "unifi_device_offline"
ARMED_SIREN_COMMAND_NAME = "future_homes_tech_armed_siren"
BEDROOM_ARMED_AWAY_COMMAND_NAME = "future_homes_tech_bedroom_armed_away"
BEDROOM_ARMED_STAY_KIDS_COMMAND_NAME = (
    "future_homes_tech_bedroom_armed_stay_kids"
)
SECRET_NAME = "future_homes_tech_protect_api_key"
ENTRY_DELAY_WEBHOOK_SECRET_NAME = (
    "future_homes_tech_entry_delay_webhook_id"
)
PACKAGE_FILENAME = "future_homes_tech_app.yaml"
HELPER_NAME = "future_homes_tech_protect_arm_mode"
ENTRY_DELAY_TIMER_NAME = "future_homes_tech_exterior_door_entry_delay"
ENTRY_DELAY_PENDING_NAME = "future_homes_tech_entry_delay_pending"
ENTRY_DELAY_DEADLINE_NAME = "future_homes_tech_entry_delay_deadline"
DEFAULT_ENTRY_DELAY_SECONDS = 30
# This home's Protect console lives in the site profile (docs/SITE_PROFILE.md).
PROTECT_DEVICE_OFFLINE_WEBHOOK = SITE_PROFILE.protect_webhook_url("device_offline")
PROTECT_ARMED_SIREN_WEBHOOK = SITE_PROFILE.protect_webhook_url("armed_siren")
DEFAULT_DEVICE_ALARM_WEBHOOK = SITE_PROFILE.protect_webhook_url("device_alarm")


class ConfigurationError(Exception):
    """Indicate an invalid or unsupported Home Assistant configuration."""


def _yaml_string(value: str) -> str:
    """Return a JSON-quoted string, which is also valid YAML."""
    return json.dumps(value, ensure_ascii=False)


def _validate(
    api_key: str,
    entry_delay_seconds: int | str,
    bedroom_armed_away_webhook: str = "",
    bedroom_armed_stay_kids_webhook: str = "",
) -> tuple[str, int, str, str]:
    """Validate and normalize App configuration."""
    api_key = api_key.strip()

    try:
        entry_delay = int(entry_delay_seconds)
    except (TypeError, ValueError) as err:
        raise ConfigurationError(
            "Entry delay seconds must be a whole number."
        ) from err
    if not 0 <= entry_delay <= 600:
        raise ConfigurationError(
            "Entry delay seconds must be between 0 and 600."
        )

    def valid_webhook(value: str, label: str) -> str:
        webhook = value.strip()
        if not webhook:
            return ""
        parsed = urlsplit(webhook)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.fragment
            or any(character.isspace() for character in webhook)
        ):
            raise ConfigurationError(
                f"{label} must be a credential-free HTTP or HTTPS URL without a fragment."
            )
        if parsed.scheme == "http":
            hostname = parsed.hostname.casefold()
            private_host = hostname in {"localhost", "supervisor"} or hostname.endswith(
                (".local", ".internal", ".lan", ".home.arpa")
            )
            try:
                private_host = private_host or ipaddress.ip_address(hostname).is_private
            except ValueError:
                pass
            if not private_host:
                raise ConfigurationError(
                    f"{label} must use HTTPS unless it targets a private or local host."
                )
        return webhook

    return (
        api_key,
        entry_delay,
        valid_webhook(
            bedroom_armed_away_webhook,
            "Armed Away Interior Door Webhook",
        ),
        valid_webhook(
            bedroom_armed_stay_kids_webhook,
            "Armed Stay Kids Interior Door Webhook",
        ),
    )


def _line_indent(line: str) -> int:
    """Return the number of leading spaces in a line."""
    return len(line) - len(line.lstrip(" "))


def _block_end(lines: list[str], start: int, indent: int) -> int:
    """Return the exclusive end of an indented YAML block."""
    for index in range(start + 1, len(lines)):
        stripped = lines[index].strip()
        if not stripped or stripped.startswith("#"):
            continue
        if _line_indent(lines[index]) <= indent:
            return index
    return len(lines)


def _find_top_level_key(lines: list[str], key: str) -> int | None:
    """Find an exact top-level YAML key."""
    pattern = re.compile(rf"^{re.escape(key)}\s*:\s*(?:#.*)?$")
    for index, line in enumerate(lines):
        if pattern.match(line.rstrip("\r\n")):
            return index
    return None


def _render_command(
    indent: int,
    webhook_url: str,
    verify_ssl: bool = True,
) -> list[str]:
    """Render the managed REST command at the requested indentation."""
    base = " " * indent
    nested = " " * (indent + 2)
    header = " " * (indent + 4)
    return [
        f"{base}{COMMAND_NAME}:\n",
        f"{nested}url: {_yaml_string(webhook_url)}\n",
        f"{nested}method: POST\n",
        f"{nested}headers:\n",
        f"{header}X-API-KEY: !secret {SECRET_NAME}\n",
        f'{header}Accept: "application/json"\n',
        f"{nested}verify_ssl: {str(verify_ssl).lower()}\n",
        f"{nested}timeout: 10\n",
    ]


def _render_armed_siren_command(
    indent: int,
    webhook_url: str,
    verify_ssl: bool = True,
) -> list[str]:
    """Render the managed Armed Siren REST command."""
    base = " " * indent
    nested = " " * (indent + 2)
    header = " " * (indent + 4)
    return [
        f"{base}{ARMED_SIREN_COMMAND_NAME}:\n",
        f"{nested}url: {_yaml_string(webhook_url)}\n",
        f"{nested}method: POST\n",
        f"{nested}headers:\n",
        f"{header}X-API-KEY: !secret {SECRET_NAME}\n",
        f'{header}Accept: "application/json"\n',
        f"{nested}verify_ssl: {str(verify_ssl).lower()}\n",
        f"{nested}timeout: 10\n",
    ]


def _render_protect_webhook_command(
    indent: int,
    command_name: str,
    webhook_url: str,
    verify_ssl: bool = True,
) -> list[str]:
    """Render one optional authenticated Protect webhook command."""
    base = " " * indent
    nested = " " * (indent + 2)
    header = " " * (indent + 4)
    return [
        f"{base}{command_name}:\n",
        f"{nested}url: {_yaml_string(webhook_url)}\n",
        f"{nested}method: POST\n",
        f"{nested}headers:\n",
        f"{header}X-API-KEY: !secret {SECRET_NAME}\n",
        f'{header}Accept: "application/json"\n',
        f"{nested}verify_ssl: {str(verify_ssl).lower()}\n",
        f"{nested}timeout: 10\n",
    ]


def _update_existing_command(
    configuration: str,
    webhook_url: str,
    verify_ssl: bool = True,
) -> tuple[str, bool]:
    """Update an existing REST command while preserving surrounding YAML."""
    lines = configuration.splitlines(keepends=True)
    rest_command_index = _find_top_level_key(lines, "rest_command")
    if rest_command_index is None:
        return configuration, False

    rest_command_end = _block_end(lines, rest_command_index, 0)
    command_pattern = re.compile(
        rf"^(\s+){re.escape(COMMAND_NAME)}\s*:\s*(?:#.*)?$"
    )

    for index in range(rest_command_index + 1, rest_command_end):
        match = command_pattern.match(lines[index].rstrip("\r\n"))
        if match is None:
            continue

        command_indent = len(match.group(1))
        command_end = _block_end(lines, index, command_indent)
        lines[index:command_end] = _render_command(
            command_indent,
            webhook_url,
            verify_ssl,
        )
        return "".join(lines), True

    return configuration, False


def _ensure_packages_include(configuration: str) -> str:
    """Ensure Home Assistant loads the managed packages directory."""
    lines = configuration.splitlines(keepends=True)
    homeassistant_index = _find_top_level_key(lines, "homeassistant")
    package_line = "  packages: !include_dir_named packages\n"

    if homeassistant_index is None:
        separator = "" if not configuration or configuration.endswith("\n") else "\n"
        return f"{configuration}{separator}\nhomeassistant:\n{package_line}"

    homeassistant_end = _block_end(lines, homeassistant_index, 0)
    packages_pattern = re.compile(r"^\s+packages\s*:\s*(.*?)\s*(?:#.*)?$")

    for index in range(homeassistant_index + 1, homeassistant_end):
        match = packages_pattern.match(lines[index].rstrip("\r\n"))
        if match is None:
            continue
        if match.group(1) == "!include_dir_named packages":
            return configuration
        raise ConfigurationError(
            "The existing homeassistant.packages configuration is not "
            "'!include_dir_named packages'. Configure the package manually."
        )

    lines.insert(homeassistant_index + 1, package_line)
    return "".join(lines)


def _retire_legacy_climate_registrations(configuration: str) -> str:
    """Remove old Climate dashboard and generator registrations only."""
    lines = configuration.splitlines(keepends=True)
    dashboards_index = next(
        (
            index
            for index, line in enumerate(lines)
            if re.match(r"^\s+dashboards\s*:\s*(?:#.*)?$", line)
        ),
        None,
    )
    if dashboards_index is not None:
        dashboards_indent = _line_indent(lines[dashboards_index])
        dashboards_end = _block_end(lines, dashboards_index, dashboards_indent)
        dashboard_pattern = re.compile(r"^(\s+)climate-dashboard\s*:\s*(?:#.*)?$")
        for index in range(dashboards_index + 1, dashboards_end):
            match = dashboard_pattern.match(lines[index].rstrip("\r\n"))
            if match is None:
                continue
            dashboard_end = _block_end(lines, index, len(match.group(1)))
            del lines[index:dashboard_end]
            break

    shell_command_index = _find_top_level_key(lines, "shell_command")
    if shell_command_index is None:
        return "".join(lines)
    shell_command_end = _block_end(lines, shell_command_index, 0)
    generator_pattern = re.compile(
        r"^\s+fht_generate_climate_(?:rate_times|billing_months)\s*:"
    )
    lines = [
        line
        for index, line in enumerate(lines)
        if not (
            shell_command_index < index < shell_command_end
            and generator_pattern.match(line)
        )
    ]
    return "".join(lines)


def _render_package(
    include_command: bool,
    entry_delay_seconds: int,
    bedroom_armed_away_webhook: str = "",
    bedroom_armed_stay_kids_webhook: str = "",
    protect_verify_ssl: bool = True,
    device_alarm_webhook: str = "",
) -> str:
    """Render the managed Home Assistant package."""
    sections = [
        "# Managed by Future Homes Tech App. Changes may be overwritten.\n"
    ]
    sections.append("rest_command:\n")
    if include_command:
        command = "".join(
            _render_command(
                2,
                PROTECT_DEVICE_OFFLINE_WEBHOOK,
                protect_verify_ssl,
            )
        )
        sections.append(command)
    sections.extend(
        _render_armed_siren_command(
            2,
            PROTECT_ARMED_SIREN_WEBHOOK,
            protect_verify_ssl,
        )
    )
    for command_name, webhook_url in (
        ("fht_device_alarm_webhook", device_alarm_webhook),
        (BEDROOM_ARMED_AWAY_COMMAND_NAME, bedroom_armed_away_webhook),
        (
            BEDROOM_ARMED_STAY_KIDS_COMMAND_NAME,
            bedroom_armed_stay_kids_webhook,
        ),
    ):
        if webhook_url:
            sections.extend(
                _render_protect_webhook_command(
                    2,
                    command_name,
                    webhook_url,
                    protect_verify_ssl,
                )
            )
    sections.append("\n")
    sections.extend(
        [
            "input_text:\n",
            f"  {HELPER_NAME}:\n",
            '    name: "Future Homes Tech Protect Arm Mode"\n',
            "    icon: mdi:shield-home\n",
            "    max: 100\n",
            "\n",
            "input_boolean:\n",
            f"  {ENTRY_DELAY_PENDING_NAME}:\n",
            '    name: "Future Homes Tech Entry Delay Pending"\n',
            "    icon: mdi:shield-timer-outline\n",
            "\n",
            "input_datetime:\n",
            f"  {ENTRY_DELAY_DEADLINE_NAME}:\n",
            '    name: "Future Homes Tech Entry Delay Deadline"\n',
            "    has_date: true\n",
            "    has_time: true\n",
            "\n",
            "timer:\n",
            f"  {ENTRY_DELAY_TIMER_NAME}:\n",
            '    name: "Future Homes Tech Exterior Door Entry Delay"\n',
            f"    duration: {entry_delay_seconds}\n",
            "    restore: true\n",
            "\n",
            "template:\n",
            "  - sensor:\n",
            '      - name: "Future Homes Tech Protect Arm Mode"\n',
            "        unique_id: future_homes_tech_protect_arm_mode\n",
            "        state: >-\n",
            "          {{ states("
            "'input_text.future_homes_tech_protect_arm_mode'"
            ") }}\n",
            "        icon: mdi:shield-home\n",
            "\n",
            "automation:\n",
            "  - id: future_homes_tech_alarm_exterior_door_entry_delay\n",
            "    alias: >-\n",
            "      Future Homes Tech - Alarm Exterior Door Entry Delay\n",
            "    mode: restart\n",
            "    triggers:\n",
            "      - trigger: webhook\n",
            f"        webhook_id: !secret {ENTRY_DELAY_WEBHOOK_SECRET_NAME}\n",
            "        allowed_methods:\n",
            "          - POST\n",
            "        local_only: true\n",
            "        id: entry\n",
            "      - trigger: state\n",
            f"        entity_id: input_text.{HELPER_NAME}\n",
            "        id: arm_state\n",
            "    actions:\n",
            "      - choose:\n",
            "          - conditions:\n",
            "              - condition: trigger\n",
            "                id: entry\n",
            "            sequence:\n",
            "              - condition: template\n",
            "                alias: fht_entry_delay_is_armed_before_wait\n",
            "                value_template: >-\n",
            "                  {% set mode = states(\n",
            f"                    'input_text.{HELPER_NAME}'\n",
            "                  ) | lower %}\n",
            "                  {{ mode not in ['', 'disarmed', 'unknown',\n",
            "                    'unavailable'] }}\n",
            "              - action: input_boolean.turn_on\n",
            f"                target: {{entity_id: input_boolean.{ENTRY_DELAY_PENDING_NAME}}}\n",
            "              - action: input_datetime.set_datetime\n",
            f"                target: {{entity_id: input_datetime.{ENTRY_DELAY_DEADLINE_NAME}}}\n",
            "                data:\n",
            "                  datetime: >-\n",
            f"                    {{{{ (now() + timedelta(seconds={entry_delay_seconds})).strftime('%Y-%m-%d %H:%M:%S') }}}}\n",
            "              - action: timer.start\n",
            f"                target: {{entity_id: timer.{ENTRY_DELAY_TIMER_NAME}}}\n",
            "                data:\n",
            f"                  duration: {entry_delay_seconds}\n",
            "          - conditions:\n",
            "              - condition: trigger\n",
            "                id: arm_state\n",
            "              - condition: template\n",
            "                value_template: >-\n",
            f"                  {{{{ states('input_text.{HELPER_NAME}') | lower in ['', 'disarmed', 'unknown', 'unavailable'] }}}}\n",
            "            sequence:\n",
            "              - action: timer.cancel\n",
            f"                target: {{entity_id: timer.{ENTRY_DELAY_TIMER_NAME}}}\n",
            "              - action: input_boolean.turn_off\n",
            f"                target: {{entity_id: input_boolean.{ENTRY_DELAY_PENDING_NAME}}}\n",
            "  - id: future_homes_tech_alarm_exterior_door_escalation\n",
            "    alias: Future Homes Tech - Alarm Exterior Door Escalation\n",
            "    mode: single\n",
            "    triggers:\n",
            "      - trigger: event\n",
            "        event_type: timer.finished\n",
            "        event_data:\n",
            f"          entity_id: timer.{ENTRY_DELAY_TIMER_NAME}\n",
            "        id: timer_finished\n",
            "      - trigger: time_pattern\n",
            '        minutes: "/1"\n',
            "        id: recovery_check\n",
            "      - trigger: homeassistant\n",
            "        event: start\n",
            "        id: startup_check\n",
            "    conditions:\n",
            "      - condition: state\n",
            f"        entity_id: input_boolean.{ENTRY_DELAY_PENDING_NAME}\n",
            '        state: "on"\n',
            "      - condition: template\n",
            "        alias: fht_entry_delay_deadline_reached\n",
            "        value_template: >-\n",
            f"          {{{{ as_timestamp(states('input_datetime.{ENTRY_DELAY_DEADLINE_NAME}'), 0) <= now().timestamp() }}}}\n",
            "      - condition: template\n",
            "        alias: fht_entry_delay_is_still_armed\n",
            "        value_template: >-\n",
            "          {% set mode = states(\n",
            f"            'input_text.{HELPER_NAME}'\n",
            "          ) | lower %}\n",
            "          {{ mode not in ['', 'disarmed', 'unknown',\n",
            "            'unavailable'] }}\n",
            "    actions:\n",
            f"      - action: rest_command.{ARMED_SIREN_COMMAND_NAME}\n",
            "      - action: input_boolean.turn_off\n",
            f"        target: {{entity_id: input_boolean.{ENTRY_DELAY_PENDING_NAME}}}\n",
        ]
    )
    return "".join(sections)


def _secret_value(secrets: str, name: str) -> str:
    """Read one JSON-quoted scalar previously managed in secrets.yaml."""
    pattern = re.compile(rf"^{re.escape(name)}\s*:\s*(.+?)\s*$", re.MULTILINE)
    match = pattern.search(secrets)
    if not match:
        return ""
    try:
        value = json.loads(match.group(1))
    except json.JSONDecodeError:
        return ""
    return str(value or "").strip()


def _updated_secret(secrets: str, name: str, value: str) -> str:
    """Add or update one managed secret without touching other values."""
    line = f"{name}: {_yaml_string(value)}\n"
    lines = secrets.splitlines(keepends=True)
    pattern = re.compile(rf"^{re.escape(name)}\s*:")
    matches = [
        index
        for index, existing_line in enumerate(lines)
        if pattern.match(existing_line)
    ]

    if len(matches) > 1:
        raise ConfigurationError(
            f"secrets.yaml contains duplicate '{name}' entries."
        )

    if matches:
        lines[matches[0]] = line
        return "".join(lines)

    separator = "" if not secrets or secrets.endswith("\n") else "\n"
    return f"{secrets}{separator}{line}"


def _updated_secrets(
    secrets: str,
    api_key: str,
    entry_delay_webhook_id: str = "",
) -> str:
    """Persist the Protect key and an installation-specific webhook ID."""
    updated = _updated_secret(secrets, SECRET_NAME, api_key)
    webhook_id = (
        entry_delay_webhook_id.strip()
        or _secret_value(updated, ENTRY_DELAY_WEBHOOK_SECRET_NAME)
        or secret_generator.token_urlsafe(32)
    )
    if not re.fullmatch(r"[A-Za-z0-9_-]{24,128}", webhook_id):
        raise ConfigurationError(
            "Entry delay webhook ID must contain 24 to 128 URL-safe characters."
        )
    return _updated_secret(
        updated,
        ENTRY_DELAY_WEBHOOK_SECRET_NAME,
        webhook_id,
    )


def _backup_once(path: Path) -> None:
    """Create a one-time backup beside a file."""
    if not path.exists():
        return
    backup_path = path.with_name(f"{path.name}.future_homes_tech_app.bak")
    if not backup_path.exists():
        shutil.copy2(path, backup_path)


def _write_atomic(path: Path, content: str, default_mode: int) -> None:
    """Atomically write a UTF-8 file while preserving its mode."""
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = (
        stat.S_IMODE(path.stat().st_mode)
        if path.exists()
        else default_mode
    )
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
    )
    temporary_path = Path(temporary_name)

    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as temporary_file:
            temporary_file.write(content)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.chmod(temporary_path, mode)
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def configure(
    config_directory: Path,
    api_key: str,
    entry_delay_seconds: int | str = DEFAULT_ENTRY_DELAY_SECONDS,
    bedroom_armed_away_webhook: str = "",
    bedroom_armed_stay_kids_webhook: str = "",
    protect_verify_ssl: bool = True,
    entry_delay_webhook_id: str = "",
    device_alarm_webhook: str = "",
) -> str:
    """Apply the managed Home Assistant configuration."""
    (
        api_key,
        entry_delay_seconds,
        bedroom_armed_away_webhook,
        bedroom_armed_stay_kids_webhook,
    ) = _validate(
        api_key,
        entry_delay_seconds,
        bedroom_armed_away_webhook,
        bedroom_armed_stay_kids_webhook,
    )

    device_alarm_webhook = _validate(api_key, entry_delay_seconds, device_alarm_webhook)[2]
    configuration_path = config_directory / "configuration.yaml"
    secrets_path = config_directory / "secrets.yaml"
    package_path = config_directory / "packages" / PACKAGE_FILENAME

    if not configuration_path.exists():
        raise ConfigurationError(
            f"Home Assistant configuration not found at {configuration_path}."
        )

    configuration = configuration_path.read_text(encoding="utf-8")
    secrets = (
        secrets_path.read_text(encoding="utf-8")
        if secrets_path.exists()
        else ""
    )

    updated_configuration, updated_existing = _update_existing_command(
        configuration,
        PROTECT_DEVICE_OFFLINE_WEBHOOK,
        protect_verify_ssl,
    )
    updated_configuration = _ensure_packages_include(
        updated_configuration
    )
    updated_configuration = _retire_legacy_climate_registrations(
        updated_configuration
    )
    package_content = _render_package(
        include_command=not updated_existing,
        entry_delay_seconds=entry_delay_seconds,
        bedroom_armed_away_webhook=bedroom_armed_away_webhook,
        bedroom_armed_stay_kids_webhook=bedroom_armed_stay_kids_webhook,
        protect_verify_ssl=protect_verify_ssl,
        device_alarm_webhook=device_alarm_webhook,
    )

    updated_secrets = _updated_secrets(
        secrets,
        api_key,
        entry_delay_webhook_id,
    )

    if updated_configuration != configuration:
        _backup_once(configuration_path)
        _write_atomic(
            configuration_path,
            updated_configuration,
            default_mode=0o644,
        )

    if updated_secrets != secrets:
        _backup_once(secrets_path)
        _write_atomic(secrets_path, updated_secrets, default_mode=0o600)

    _write_atomic(package_path, package_content, default_mode=0o644)

    return (
        "Updated existing rest_command.unifi_device_offline."
        if updated_existing
        else "Created the managed Future Homes Tech package."
    )


def main() -> int:
    """Run the configuration manager."""
    config_directory = Path(
        os.environ.get("HOMEASSISTANT_CONFIG_DIR", "/homeassistant")
    )
    api_key = os.environ.get("PROTECT_API_KEY", "")
    entry_delay_seconds = os.environ.get(
        "ENTRY_DELAY_SECONDS",
        str(DEFAULT_ENTRY_DELAY_SECONDS),
    )
    bedroom_armed_away_webhook = os.environ.get(
        "BEDROOM_ARMED_AWAY_WEBHOOK",
        "",
    )
    bedroom_armed_stay_kids_webhook = os.environ.get(
        "BEDROOM_ARMED_STAY_KIDS_WEBHOOK",
        "",
    )
    protect_verify_ssl = os.environ.get("PROTECT_VERIFY_SSL", "1") == "1"
    entry_delay_webhook_id = os.environ.get("ENTRY_DELAY_WEBHOOK_ID", "")

    try:
        result = configure(
            config_directory,
            api_key,
            entry_delay_seconds,
            bedroom_armed_away_webhook,
            bedroom_armed_stay_kids_webhook,
            protect_verify_ssl,
            entry_delay_webhook_id,
            # A blank Device Alarm Webhook option means this home's profile value.
            os.environ.get("DEVICE_ALARM_WEBHOOK", "").strip()
            or DEFAULT_DEVICE_ALARM_WEBHOOK,
        )
    except ConfigurationError as err:
        print(f"Configuration failed: {err}", flush=True)
        return 1

    print(result, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
