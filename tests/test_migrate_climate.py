"""Tests for the Future Homes Tech Climate package migration."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


MODULE_PATH = (
    Path(__file__).parents[1]
    / "future_homes_tech_app"
    / "migrate_climate.py"
)
SPEC = importlib.util.spec_from_file_location("migrate_climate", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
MIGRATE_CLIMATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MIGRATE_CLIMATE)


class ClimateMigrationTests(unittest.TestCase):
    """Verify late migration additions keep legacy values intact."""

    def test_adds_weather_helper_to_existing_managed_package(self) -> None:
        """Move the legacy weather helper without creating a duplicate."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_directory = Path(temporary_directory)
            package_path = (
                config_directory
                / "packages"
                / MIGRATE_CLIMATE.PACKAGE_NAME
            )
            package_path.parent.mkdir(parents=True)
            package_path.write_text("input_boolean:\n", encoding="utf-8")
            weather_path = (
                config_directory
                / "fht"
                / "inputtext"
                / "weather_settings.yaml"
            )
            weather_path.parent.mkdir(parents=True)
            weather_path.write_text(
                "fht_weather_entity:\n"
                "  name: Weather Entity\n"
                "  initial: weather.forecast_home\n",
                encoding="utf-8",
            )

            result = MIGRATE_CLIMATE.migrate(config_directory)

            self.assertEqual(result, "updated")
            self.assertIn(
                "input_text:\n  fht_weather_entity:",
                package_path.read_text(encoding="utf-8"),
            )
            self.assertFalse(weather_path.exists())
            self.assertTrue(
                config_directory.joinpath(
                    "fht",
                    "retired_climate",
                    "inputtext",
                    "weather_settings.yaml",
                ).is_file()
            )

    def test_adds_delivery_guard_to_existing_climate_package(self) -> None:
        """Install the verification guard once before the script section."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_directory = Path(temporary_directory)
            package_path = (
                config_directory
                / "packages"
                / MIGRATE_CLIMATE.PACKAGE_NAME
            )
            package_path.parent.mkdir(parents=True)
            package_path.write_text(
                "automation:\n"
                "  - id: fht_climate_set_targets_on_rate_mode_change\n"
                "script:\n",
                encoding="utf-8",
            )

            result = MIGRATE_CLIMATE.migrate(config_directory)

            content = package_path.read_text(encoding="utf-8")
            self.assertEqual(result, "updated")
            self.assertIn(MIGRATE_CLIMATE.DELIVERY_GUARD_BEGIN, content)
            self.assertIn(
                "id: fht_climate_verify_rate_mode_targets",
                content,
            )
            self.assertLess(
                content.index(MIGRATE_CLIMATE.DELIVERY_GUARD_BEGIN),
                content.index("script:"),
            )
            self.assertEqual(
                MIGRATE_CLIMATE.migrate(config_directory),
                "existing",
            )

    def test_restores_app_owned_package_when_missing(self) -> None:
        """Recover the managed Climate package without legacy source files."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_directory = Path(temporary_directory)
            backup_path = config_directory / "climate-backup.yaml"
            backup_path.write_text(
                "automation:\n"
                "  - id: fht_climate_set_targets_on_rate_mode_change\n"
                "script:\n",
                encoding="utf-8",
            )

            with patch.dict(
                "os.environ",
                {"FHT_CLIMATE_PACKAGE_BACKUP_PATH": str(backup_path)},
            ):
                result = MIGRATE_CLIMATE.migrate(config_directory)

            package_path = (
                config_directory
                / "packages"
                / MIGRATE_CLIMATE.PACKAGE_NAME
            )
            self.assertEqual(result, "restored")
            self.assertIn(
                "id: fht_climate_verify_rate_mode_targets",
                package_path.read_text(encoding="utf-8"),
            )
