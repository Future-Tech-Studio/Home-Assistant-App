#!/usr/bin/env python3
"""Migrate legacy FHT Climate YAML into one App-managed package."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import tempfile


PACKAGE_NAME = "future_homes_tech_climate.yaml"
CLIMATE_PACKAGE_BACKUP_NAME = "future_homes_tech_climate_base.yaml"
DELIVERY_GUARD_BEGIN = "# BEGIN FHT CLIMATE DELIVERY GUARD"
DELIVERY_GUARD_END = "# END FHT CLIMATE DELIVERY GUARD"
CLIMATE_DELIVERY_GUARD = f'''{DELIVERY_GUARD_BEGIN}
  - id: fht_climate_verify_rate_mode_targets
    alias: FHT - Climate Verify Rate Mode Targets
    mode: restart

    trigger:
      - platform: homeassistant
        event: start
      - platform: state
        entity_id:
          - sensor.fht_climate_rate_mode
          - input_boolean.fht_occupancy_mode
          - input_boolean.fht_vacation_mode

    action:
      - repeat:
          count: 2
          sequence:
            - delay:
                minutes: 5

            - variables:
                rate_mode: "{{{{ states('sensor.fht_climate_rate_mode') }}}}"
                override_to_on_peak: >
                  {{{{ is_state('input_boolean.fht_occupancy_mode', 'on')
                    or is_state('input_boolean.fht_vacation_mode', 'on') }}}}
                cool_target: >
                  {{% if override_to_on_peak %}}
                    {{{{ states('input_number.fht_on_peak_target_cool') | float(76) }}}}
                  {{% elif rate_mode == 'Super Cool' %}}
                    {{{{ states('sensor.fht_super_cool_current_temp_target') | float(60) }}}}
                  {{% elif rate_mode == 'On-Peak' %}}
                    {{{{ states('input_number.fht_on_peak_target_cool') | float(76) }}}}
                  {{% elif rate_mode == 'Super-Off Peak' %}}
                    {{{{ states('input_number.fht_super_off_peak_target_cool') | float(72) }}}}
                  {{% elif rate_mode == 'Holiday' %}}
                    {{{{ states('input_number.fht_holiday_target_cool') | float(76) }}}}
                  {{% elif rate_mode == 'Solar' %}}
                    {{{{ states('input_number.fht_solar_target_cool') | float(72) }}}}
                  {{% else %}}
                    {{{{ states('input_number.fht_off_peak_target_cool') | float(76) }}}}
                  {{% endif %}}
                heat_target: >
                  {{% if override_to_on_peak %}}
                    {{{{ states('input_number.fht_on_peak_target_heat') | float(68) }}}}
                  {{% elif rate_mode == 'Super Cool' or rate_mode == 'On-Peak' %}}
                    {{{{ states('input_number.fht_on_peak_target_heat') | float(68) }}}}
                  {{% elif rate_mode == 'Super-Off Peak' %}}
                    {{{{ states('input_number.fht_super_off_peak_target_heat') | float(68) }}}}
                  {{% elif rate_mode == 'Holiday' %}}
                    {{{{ states('input_number.fht_holiday_target_heat') | float(68) }}}}
                  {{% elif rate_mode == 'Solar' %}}
                    {{{{ states('input_number.fht_solar_target_heat') | float(68) }}}}
                  {{% else %}}
                    {{{{ states('input_number.fht_off_peak_target_heat') | float(68) }}}}
                  {{% endif %}}
                targets_match: >
                  {{% set ns = namespace(matches=true) %}}
                  {{% for thermostat in states.climate %}}
                    {{% set entity_id = thermostat.entity_id %}}
                    {{% set supported_modes = state_attr(entity_id, 'hvac_modes') or [] %}}
                    {{% if thermostat.state in ['unknown', 'unavailable'] %}}
                      {{% set ns.matches = false %}}
                    {{% elif 'heat_cool' in supported_modes %}}
                      {{% if thermostat.state != 'heat_cool'
                        or state_attr(entity_id, 'target_temp_low') | float(-999) != heat_target | float
                        or state_attr(entity_id, 'target_temp_high') | float(-999) != cool_target | float %}}
                        {{% set ns.matches = false %}}
                      {{% endif %}}
                    {{% elif 'cool' in supported_modes %}}
                      {{% if thermostat.state != 'cool'
                        or state_attr(entity_id, 'temperature') | float(-999) != cool_target | float %}}
                        {{% set ns.matches = false %}}
                      {{% endif %}}
                    {{% elif 'heat' in supported_modes %}}
                      {{% if thermostat.state != 'heat'
                        or state_attr(entity_id, 'temperature') | float(-999) != heat_target | float %}}
                        {{% set ns.matches = false %}}
                      {{% endif %}}
                    {{% endif %}}
                  {{% endfor %}}
                  {{{{ ns.matches }}}}

            - if:
                - condition: template
                  value_template: "{{{{ targets_match | bool }}}}"
              then:
                - stop: Climate targets verified.
              else:
                - service: automation.trigger
                  target:
                    entity_id: automation.fht_climate_set_targets_on_rate_mode_change
                  data:
                    skip_condition: true
                - service: logbook.log
                  data:
                    name: FHT Climate Control
                    message: >
                      Target verification found a mismatch on attempt
                      {{{{ repeat.index }}}}; target delivery was retried.
{DELIVERY_GUARD_END}'''
LEGACY_FILES = {
    "input_boolean": ["inputboolean/climate_holidays.yaml", "inputboolean/climate_modes.yaml"],
    "input_number": ["inputnumber/climate_comfort_targets.yaml", "inputnumber/super_cool_learning.yaml"],
    "input_datetime": ["inputdatetime/climate_rate_times.yaml"],
    "input_select": ["inputselect/climate_billing_months.yaml"],
    "input_text": ["inputtext/weather_settings.yaml"],
    "template": [
        "templates/climate_rate_mode.yaml",
        "templates/holiday_next_selected.yaml",
        "templates/super_cool_learning.yaml",
        "templates/weather_forecast_daily.yaml",
    ],
    "automation": [
        "automations/climate_set_targets_on_rate_mode_change.yaml",
        "automations/super_cool_capture_delta.yaml",
        "automations/super_cool_learn_at_on_peak_end.yaml",
        "automations/super_cool_learn_at_on_peak_start.yaml",
        "automations/super_cool_reduce_time_if_ready_early.yaml",
        "automations/super_cool_reset_learning_flags.yaml",
    ],
    "script": ["scripts/super_cool_initilize_delta_table.yaml"],
}


def _indented(content: str) -> str:
    return "".join(f"  {line}\n" for line in content.splitlines())


def render_package(config_directory: Path) -> tuple[str, list[Path]]:
    """Combine every existing legacy Climate file into one package."""
    legacy_root = config_directory / "fht"
    groups: list[tuple[str, list[Path]]] = []
    for domain, relative_paths in LEGACY_FILES.items():
        paths = [legacy_root / relative_path for relative_path in relative_paths]
        if domain == "input_text":
            paths = [path for path in paths if path.is_file()]
            if not paths:
                continue
        if not all(path.is_file() for path in paths):
            missing = next(path for path in paths if not path.is_file())
            raise FileNotFoundError(f"Missing legacy Climate file: {missing}")
        groups.append((domain, paths))

    lines = [
        "# Managed by Future Homes Tech App. Changes may be overwritten.\n",
        "# Migrated from legacy /config/fht Climate configuration.\n",
    ]
    sources: list[Path] = []
    for domain, paths in groups:
        lines.append(f"{domain}:\n")
        for path in paths:
            lines.append(_indented(path.read_text(encoding="utf-8")))
            sources.append(path)
    return "".join(lines), sources


def write_package(package_path: Path, content: str) -> None:
    """Atomically write the managed Climate package."""
    package_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=package_path.parent, delete=False
    ) as temporary_file:
        temporary_file.write(content)
        temporary_path = Path(temporary_file.name)
    temporary_path.replace(package_path)


def package_backup_path(config_directory: Path) -> Path:
    """Return the add-on-owned recovery copy for the Climate package."""
    configured_path = os.environ.get("FHT_CLIMATE_PACKAGE_BACKUP_PATH")
    if configured_path:
        return Path(configured_path)
    return config_directory / ".future_homes_tech_app" / CLIMATE_PACKAGE_BACKUP_NAME


def store_package_backup(package_path: Path, backup_path: Path) -> None:
    """Keep the first complete App-managed Climate package for recovery."""
    if backup_path.is_file():
        return
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(package_path, backup_path)


def migrate_weather_helper(config_directory: Path, package_path: Path) -> bool:
    """Bring the legacy Weather Entity helper under app management."""
    source = config_directory / "fht" / "inputtext/weather_settings.yaml"
    if not source.is_file():
        return False

    content = package_path.read_text(encoding="utf-8")
    if "fht_weather_entity:" not in content:
        content = (
            f"{content.rstrip()}\n\ninput_text:\n"
            f"{_indented(source.read_text(encoding='utf-8'))}"
        )
        write_package(package_path, content)

    destination = (
        config_directory
        / "fht"
        / "retired_climate"
        / "inputtext/weather_settings.yaml"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(destination))
    return True


def upsert_delivery_guard(package_path: Path) -> bool:
    """Add the managed Climate delivery verification automation."""
    content = package_path.read_text(encoding="utf-8")
    existing_start = content.find(DELIVERY_GUARD_BEGIN)
    existing_end = content.find(DELIVERY_GUARD_END)
    if existing_start >= 0 and existing_end >= existing_start:
        existing_end += len(DELIVERY_GUARD_END)
        updated = (
            f"{content[:existing_start]}{CLIMATE_DELIVERY_GUARD}"
            f"{content[existing_end:]}"
        )
    else:
        script_marker = "\nscript:\n"
        script_index = content.find(script_marker)
        if script_index < 0 or "automation:\n" not in content:
            return False
        updated = (
            f"{content[:script_index].rstrip()}\n\n"
            f"{CLIMATE_DELIVERY_GUARD}\n"
            f"{content[script_index + 1:]}"
        )
    if updated == content:
        return False
    write_package(package_path, updated)
    return True


def upgrade_managed_package(
    config_directory: Path,
    package_path: Path,
) -> bool:
    """Apply safe App-owned upgrades to the migrated Climate package."""
    weather_updated = migrate_weather_helper(config_directory, package_path)
    delivery_guard_updated = upsert_delivery_guard(package_path)
    return weather_updated or delivery_guard_updated


def migrate(config_directory: Path, check: bool = False) -> str:
    """Create the managed package and retire original climate-only files."""
    package_path = config_directory / "packages" / PACKAGE_NAME
    backup_path = package_backup_path(config_directory)
    if package_path.is_file():
        if check:
            return "ready"
        updated = upgrade_managed_package(
            config_directory,
            package_path,
        )
        store_package_backup(package_path, backup_path)
        return "updated" if updated else "existing"
    if backup_path.is_file():
        if check:
            return "ready"
        write_package(
            package_path,
            backup_path.read_text(encoding="utf-8"),
        )
        upgrade_managed_package(config_directory, package_path)
        return "restored"
    content, sources = render_package(config_directory)
    if check:
        return "ready"

    write_package(package_path, content)
    upsert_delivery_guard(package_path)
    store_package_backup(package_path, backup_path)

    archive_root = config_directory / "fht" / "retired_climate"
    for source in sources:
        destination = archive_root / source.relative_to(config_directory / "fht")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))
    return "migrated"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="/homeassistant")
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    print(migrate(Path(arguments.config), arguments.check))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
