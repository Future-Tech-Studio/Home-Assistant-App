# Maintenance tools

There is no maintenance page any more: the Safe Cleanup page was removed in 0.8.57. (Device Health and Action Timeline were removed in 0.7.11.)

## Automatic cleanup

Every time the App activates its generated configuration (at start-up and after a settings revert), it deletes what it made itself and nothing uses any more:

- **Retired App entities**: automations, light groups and template entities with an App unique ID (`fht_…`, or the plain room-group IDs early releases used), not linked to an integration, that Home Assistant reports as unavailable and that no configuration YAML or package still provides.
- **Replaced fan-light groups**: `light.<room>_fan_lights` once the active `light.fht_<room>_fan_lights` replaces it and nothing references the old ID.
- **Unused App helpers**: `fht_` helpers (input_*, automation, script) with a verifiable unique ID, no device or integration, that Home Assistant restores as unavailable (or that an earlier Safe Cleanup archived), and that no scanned source mentions. Sources: configuration YAML and packages (following `!include`s), Lovelace and helper storage, config entries and the App's own settings files. Commented-out includes are ignored, missing includes count as empty, and ESPHome and Zigbee2MQTT folders are skipped. A source that cannot be read safely (unreadable, linked, outside the configuration folder, invalid JSON) skips this step for that start, and the App log names the file.

Entities and helpers the App did not make are never touched.

Before each deletion the full registry entries are journaled under `/data/maintenance/removed`. The **Revert Changes** card lists each batch as "App · Removed automatically" for information; it has no Revert button, because the App recreates an item itself whenever a setting needs it again.

## Installation and validation

Stable 0.5.23 remains the approved rollback. Candidate 0.5.35 is not stable until the homeowner approves it after live testing.

Run `scripts/release_gate.sh` with a supported Python and Node runtime. `tests/run_maintenance_browser.py` uses an isolated loopback fixture and covers lazy loading, desktop/mobile layout, trace summaries, archive confirmation and recovery without device operations.

When the add-on share is unavailable, `scripts/package_candidate.py 0.5.35 --local-only` creates explicitly labeled local source/runtime archives. This does not publish, mount or install an update. After mounting the real add-on share, verify matching runtime checksums before installation and test administrator access, device freshness, context attribution and recovery in Home Assistant.

Trace integration follows the official [Home Assistant WebSocket API](https://developers.home-assistant.io/docs/api/websocket/) and [trace implementation](https://github.com/home-assistant/core/tree/dev/homeassistant/components/trace). Live compatibility must still be verified against the installed HA release.
