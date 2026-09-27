"""Tests for the Future Homes Tech App configuration manager."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest

MODULE_PATH = (
    Path(__file__).parents[1]
    / "future_homes_tech_app"
    / "configure.py"
)
SPEC = importlib.util.spec_from_file_location("configure", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
CONFIGURE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONFIGURE)

API_KEY = "test-key-with-#-character"
WEBHOOK_URL = CONFIGURE.PROTECT_DEVICE_OFFLINE_WEBHOOK


class ConfigureTests(unittest.TestCase):
    def test_device_alarm_webhook_command_uses_protect_auth(self) -> None:
        content = CONFIGURE._render_package(
            include_command=True, entry_delay_seconds=30,
            device_alarm_webhook="https://unifi.fht.internal/proxy/protect/integration/v1/alarm-manager/webhook/DeviceAlarm",
        )
        self.assertIn("fht_device_alarm_webhook:", content)
        self.assertIn("webhook/DeviceAlarm", content)
        self.assertIn("X-API-KEY: !secret", content)
        self.assertIn("verify_ssl: true", content)

    """Verify idempotent Home Assistant YAML management."""

    def test_updates_existing_rest_command(self) -> None:
        """Update the existing command without rewriting unrelated YAML."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_directory = Path(temporary_directory)
            configuration_path = config_directory / "configuration.yaml"
            configuration_path.write_text(
                """default_config:

rest_command:
  another_command:
    url: "https://example.com/other"
  unifi_device_offline:
    url: "https://old.example/device_offline"
    method: GET
    headers:
      X-API-KEY: "old-key"
""",
                encoding="utf-8",
            )

            result = CONFIGURE.configure(
                config_directory,
                API_KEY,
            )

            configuration = configuration_path.read_text(encoding="utf-8")
            secrets = (config_directory / "secrets.yaml").read_text(
                encoding="utf-8"
            )

            self.assertEqual(
                result,
                "Updated existing rest_command.unifi_device_offline.",
            )
            self.assertIn('url: "https://example.com/other"', configuration)
            self.assertIn(f'url: "{WEBHOOK_URL}"', configuration)
            self.assertIn(
                "X-API-KEY: !secret future_homes_tech_protect_api_key",
                configuration,
            )
            self.assertIn("method: POST", configuration)
            self.assertIn("verify_ssl: true", configuration)
            self.assertIn("timeout: 10", configuration)
            self.assertNotIn("old-key", configuration)
            self.assertIn(
                'future_homes_tech_protect_api_key: '
                '"test-key-with-#-character"',
                secrets,
            )
            self.assertTrue(
                config_directory.joinpath(
                    "configuration.yaml.future_homes_tech_app.bak"
                ).exists()
            )

    def test_creates_managed_package(self) -> None:
        """Enable packages and create the command when it is absent."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_directory = Path(temporary_directory)
            configuration_path = config_directory / "configuration.yaml"
            configuration_path.write_text(
                """default_config:

homeassistant:
  customize: !include customize.yaml
""",
                encoding="utf-8",
            )

            result = CONFIGURE.configure(
                config_directory,
                API_KEY,
            )

            configuration = configuration_path.read_text(encoding="utf-8")
            package = config_directory.joinpath(
                "packages",
                "future_homes_tech_app.yaml",
            ).read_text(encoding="utf-8")

            self.assertEqual(
                result,
                "Created the managed Future Homes Tech package.",
            )
            self.assertIn(
                "  packages: !include_dir_named packages",
                configuration,
            )
            self.assertIn("rest_command:", package)
            self.assertIn("unifi_device_offline:", package)
            self.assertIn(f'url: "{WEBHOOK_URL}"', package)
            self.assertIn("input_text:", package)
            self.assertIn(
                "future_homes_tech_protect_arm_mode:",
                package,
            )
            self.assertIn(
                'name: "Future Homes Tech Protect Arm Mode"',
                package,
            )
            self.assertIn("template:", package)
            self.assertIn("  - sensor:", package)
            self.assertIn(
                "unique_id: future_homes_tech_protect_arm_mode",
                package,
            )
            self.assertIn(
                "future_homes_tech_armed_siren:",
                package,
            )
            self.assertIn(
                "alarm-manager/webhook/Armed%20Siren",
                package,
            )
            self.assertIn(
                "webhook_id: !secret future_homes_tech_entry_delay_webhook_id",
                package,
            )
            self.assertIn(
                "Future Homes Tech - Alarm Exterior Door Entry Delay",
                package,
            )
            self.assertIn("    mode: restart", package)
            self.assertNotIn("    max_exceeded: silent", package)
            self.assertIn("timer:", package)
            self.assertIn("duration: 30", package)
            self.assertIn("event_type: timer.finished", package)
            self.assertIn(
                "action: rest_command."
                "future_homes_tech_armed_siren",
                package,
            )
            self.assertIn(
                "{{ states("
                "'input_text.future_homes_tech_protect_arm_mode'"
                ") }}",
                package,
            )
            self.assertIn(
                "future_homes_tech_entry_delay_webhook_id:",
                config_directory.joinpath("secrets.yaml").read_text(
                    encoding="utf-8"
                ),
            )

    def test_creates_helper_with_existing_rest_command(self) -> None:
        """Create the helper without duplicating an existing command."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_directory = Path(temporary_directory)
            configuration_path = config_directory / "configuration.yaml"
            configuration_path.write_text(
                """homeassistant:
  packages: !include_dir_named packages
rest_command:
  unifi_device_offline:
    url: "https://old.example/device_offline"
""",
                encoding="utf-8",
            )

            CONFIGURE.configure(
                config_directory,
                API_KEY,
            )

            package = config_directory.joinpath(
                "packages",
                "future_homes_tech_app.yaml",
            ).read_text(encoding="utf-8")
            self.assertIn("input_text:", package)
            self.assertIn("template:", package)
            self.assertIn("rest_command:", package)
            self.assertNotIn("unifi_device_offline:", package)
            self.assertIn(
                "future_homes_tech_armed_siren:",
                package,
            )

    def test_applies_configured_entry_delay(self) -> None:
        """Render the selected entry-delay seconds into the automation."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_directory = Path(temporary_directory)
            config_directory.joinpath("configuration.yaml").write_text(
                "default_config:\n",
                encoding="utf-8",
            )

            CONFIGURE.configure(
                config_directory,
                API_KEY,
                entry_delay_seconds=45,
            )

            package = config_directory.joinpath(
                "packages",
                "future_homes_tech_app.yaml",
            ).read_text(encoding="utf-8")
            self.assertIn("duration: 45", package)
            self.assertIn("timedelta(seconds=45)", package)

    def test_entry_delay_is_cancelled_and_rechecked_on_disarm(self) -> None:
        """Do not escalate a pending exterior-door delay after disarm."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_directory = Path(temporary_directory)
            config_directory.joinpath("configuration.yaml").write_text(
                "default_config:\n",
                encoding="utf-8",
            )

            CONFIGURE.configure(config_directory, API_KEY)

            package = config_directory.joinpath(
                "packages",
                "future_homes_tech_app.yaml",
            ).read_text(encoding="utf-8")

        self.assertIn("    mode: restart", package)
        self.assertIn("        id: entry", package)
        self.assertIn("        id: arm_state", package)
        self.assertIn(f"        entity_id: input_text.{CONFIGURE.HELPER_NAME}", package)
        self.assertIn("fht_entry_delay_is_armed_before_wait", package)
        self.assertIn("action: timer.cancel", package)
        self.assertIn("fht_entry_delay_is_still_armed", package)
        self.assertIn("fht_entry_delay_deadline_reached", package)
        self.assertLess(
            package.rfind("fht_entry_delay_is_still_armed"),
            package.rfind(f"action: rest_command.{CONFIGURE.ARMED_SIREN_COMMAND_NAME}"),
        )

    def test_preserves_installation_specific_entry_webhook_id(self) -> None:
        """Generate a private webhook ID once and preserve it on reruns."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_directory = Path(temporary_directory)
            config_directory.joinpath("configuration.yaml").write_text(
                "default_config:\n",
                encoding="utf-8",
            )

            CONFIGURE.configure(config_directory, API_KEY)
            first_secrets = config_directory.joinpath("secrets.yaml").read_text(
                encoding="utf-8"
            )
            CONFIGURE.configure(config_directory, API_KEY)
            second_secrets = config_directory.joinpath("secrets.yaml").read_text(
                encoding="utf-8"
            )

        self.assertEqual(first_secrets, second_secrets)
        webhook_id = CONFIGURE._secret_value(
            second_secrets,
            CONFIGURE.ENTRY_DELAY_WEBHOOK_SECRET_NAME,
        )
        self.assertGreaterEqual(len(webhook_id), 24)
        self.assertNotEqual(webhook_id, "future_homes_tech_entry_delay")

    def test_can_enable_protect_tls_verification(self) -> None:
        """Render verified Protect REST commands when configured."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_directory = Path(temporary_directory)
            config_directory.joinpath("configuration.yaml").write_text(
                "default_config:\n",
                encoding="utf-8",
            )

            CONFIGURE.configure(
                config_directory,
                API_KEY,
                protect_verify_ssl=True,
            )
            package = config_directory.joinpath(
                "packages",
                CONFIGURE.PACKAGE_FILENAME,
            ).read_text(encoding="utf-8")

        self.assertNotIn("verify_ssl: false", package)
        self.assertIn("verify_ssl: true", package)

    def test_adds_optional_bedroom_security_webhooks(self) -> None:
        """Create separate Protect calls for Away and Stay Kids modes."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_directory = Path(temporary_directory)
            config_directory.joinpath("configuration.yaml").write_text(
                "default_config:\n",
                encoding="utf-8",
            )

            CONFIGURE.configure(
                config_directory,
                API_KEY,
                bedroom_armed_away_webhook=(
                    "https://unifi.example/webhook/bedroom-away"
                ),
                bedroom_armed_stay_kids_webhook=(
                    "https://unifi.example/webhook/bedroom-stay-kids"
                ),
            )

            package = config_directory.joinpath(
                "packages",
                "future_homes_tech_app.yaml",
            ).read_text(encoding="utf-8")
            self.assertIn(
                "future_homes_tech_bedroom_armed_away:",
                package,
            )
            self.assertIn(
                'url: "https://unifi.example/webhook/bedroom-away"',
                package,
            )
            self.assertIn(
                "future_homes_tech_bedroom_armed_stay_kids:",
                package,
            )
            self.assertIn(
                'url: "https://unifi.example/webhook/bedroom-stay-kids"',
                package,
            )

    def test_rejects_invalid_bedroom_security_webhook(self) -> None:
        """Reject malformed optional webhook addresses."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_directory = Path(temporary_directory)
            config_directory.joinpath("configuration.yaml").write_text(
                "default_config:\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                CONFIGURE.ConfigurationError,
                "credential-free HTTP or HTTPS URL",
            ):
                CONFIGURE.configure(
                    config_directory,
                    API_KEY,
                    bedroom_armed_away_webhook="not-a-url",
                )

    def test_rejects_entry_delay_outside_range(self) -> None:
        """Reject unsafe or accidental entry-delay values."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_directory = Path(temporary_directory)
            config_directory.joinpath("configuration.yaml").write_text(
                "default_config:\n",
                encoding="utf-8",
            )

            with self.assertRaises(CONFIGURE.ConfigurationError):
                CONFIGURE.configure(
                    config_directory,
                    API_KEY,
                    entry_delay_seconds=601,
                )

    def test_uses_shared_protect_webhooks(self) -> None:
        """Use the standard Future Homes Tech Protect endpoints."""
        self.assertEqual(
            CONFIGURE.PROTECT_DEVICE_OFFLINE_WEBHOOK,
            "https://unifi.fht.internal/proxy/protect/"
            "integration/v1/alarm-manager/webhook/device_offline",
        )
        self.assertEqual(
            CONFIGURE.PROTECT_ARMED_SIREN_WEBHOOK,
            "https://unifi.fht.internal/proxy/protect/"
            "integration/v1/alarm-manager/webhook/Armed%20Siren",
        )

    def test_configuration_is_idempotent(self) -> None:
        """Applying the same options twice produces identical files."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_directory = Path(temporary_directory)
            configuration_path = config_directory / "configuration.yaml"
            configuration_path.write_text(
                "default_config:\n",
                encoding="utf-8",
            )

            CONFIGURE.configure(config_directory, API_KEY)
            first_configuration = configuration_path.read_text(
                encoding="utf-8"
            )
            first_secrets = config_directory.joinpath(
                "secrets.yaml"
            ).read_text(encoding="utf-8")
            first_package = config_directory.joinpath(
                "packages",
                "future_homes_tech_app.yaml",
            ).read_text(encoding="utf-8")

            CONFIGURE.configure(config_directory, API_KEY)

            self.assertEqual(
                first_configuration,
                configuration_path.read_text(encoding="utf-8"),
            )
            self.assertEqual(
                first_secrets,
                config_directory.joinpath("secrets.yaml").read_text(
                    encoding="utf-8"
                ),
            )
            self.assertEqual(
                first_package,
                config_directory.joinpath(
                    "packages",
                    "future_homes_tech_app.yaml",
                ).read_text(encoding="utf-8"),
            )

    def test_retires_only_legacy_climate_registrations(self) -> None:
        """Remove old Climate entry points without touching other features."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_directory = Path(temporary_directory)
            configuration_path = config_directory / "configuration.yaml"
            configuration_path.write_text(
                """lovelace:
  dashboards:
    climate-dashboard:
      mode: yaml
      filename: fht/dashboards/climate.yaml
    lighting-dashboard:
      mode: yaml
      filename: fht/dashboards/lighting.yaml

shell_command:
  fht_generate_climate_rate_times: /config/fht/generators/rates.sh
  fht_generate_climate_billing_months: /config/fht/generators/months.sh
  fht_generate_room_modes: /config/fht/generators/rooms.sh
""",
                encoding="utf-8",
            )

            CONFIGURE.configure(config_directory, API_KEY)

            configuration = configuration_path.read_text(encoding="utf-8")
            self.assertNotIn("climate-dashboard:", configuration)
            self.assertNotIn("fht/dashboards/climate.yaml", configuration)
            self.assertNotIn("fht_generate_climate_rate_times:", configuration)
            self.assertNotIn(
                "fht_generate_climate_billing_months:",
                configuration,
            )
            self.assertIn("lighting-dashboard:", configuration)
            self.assertIn("fht_generate_room_modes:", configuration)

    def test_allows_empty_protect_api_key(self) -> None:
        """Generate every non-Protect feature without an API key."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_directory = Path(temporary_directory)
            config_directory.joinpath("configuration.yaml").write_text(
                "default_config:\n",
                encoding="utf-8",
            )

            result = CONFIGURE.configure(config_directory, "")

            package = config_directory.joinpath(
                "packages",
                "future_homes_tech_app.yaml",
            ).read_text(encoding="utf-8")
            secrets = config_directory.joinpath(
                "secrets.yaml"
            ).read_text(encoding="utf-8")
            self.assertEqual(
                result,
                "Created the managed Future Homes Tech package.",
            )
            self.assertIn("automation:", package)
            self.assertIn("template:", package)
            self.assertIn(
                'future_homes_tech_protect_api_key: ""',
                secrets,
            )


if __name__ == "__main__":
    unittest.main()
