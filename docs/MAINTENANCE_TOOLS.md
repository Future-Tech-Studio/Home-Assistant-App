# Maintenance tools

Safe Cleanup is administrator-only and loads on demand. Opening Future Homes Tech does not start a maintenance scan or add maintenance API requests to its preload. (Device Health and Action Timeline were removed in 0.7.11.)

## Safe Cleanup

- First opens private recovery history; scanning requires an explicit click.
- Lists retired Future Homes Tech entities found at start-up (no longer generated and not used by any configuration) for approval before deletion. Deleted registry entries are journaled under `/data/maintenance/removed`. An option deletes them automatically at start-up from then on.
- Reports groups with identical nonempty direct membership for review only. Nested-equivalent groups require manual review. No automatic merges.
- Lists leftover entities not made by Future Homes Tech: registry entries that no integration currently provides (restored or missing state), excluding disabled entities and App-made entities. Read-only; delete them in Home Assistant after review.
- Archive eligibility is deliberately narrow: unavailable restored FHT-prefixed helpers, no physical-device/config-entry linkage, no existing disabled/hidden protection, stable unique identity, and no definition/reference found in scanned files.
- Scans configuration YAML, packages, Lovelace/helper storage, config-entry definitions and top-level app JSON settings. Commented-out includes are ignored and includes of files that do not exist are treated as empty. Unreadable sources, links, and includes outside the configuration folder block the operation, and the message names the file. ESPHome and Zigbee2MQTT folders are not Home Assistant configuration and are skipped. External controllers and dynamically constructed references still require explicit installer review.
- Administrator authentication, CSRF verification, a fresh plan revision, confirmation of the exact batch and external-reference review are mandatory. Maximum ten helpers per batch.
- **Archive means disable and hide, not permanent deletion.** A private journal under `/data/maintenance` records the original registry flags before changes. Recovery checks entity identities/protections before restoring those flags. Partial failures remain visible for recovery rather than being reported as completed.
- A journal restores registry flags only; it is not a substitute for a full Home Assistant backup. No live cleanup is executed while developing or testing this feature.

## Installation and validation

Stable 0.5.23 remains the approved rollback. Candidate 0.5.35 is not stable until the homeowner approves it after live testing.

Run `scripts/release_gate.sh` with a supported Python and Node runtime. `tests/run_maintenance_browser.py` uses an isolated loopback fixture and covers lazy loading, desktop/mobile layout, trace summaries, archive confirmation and recovery without device operations.

When the add-on share is unavailable, `scripts/package_candidate.py 0.5.35 --local-only` creates explicitly labeled local source/runtime archives. This does not publish, mount or install an update. After mounting the real add-on share, verify matching runtime checksums before installation and test administrator access, device freshness, context attribution and recovery in Home Assistant.

Trace integration follows the official [Home Assistant WebSocket API](https://developers.home-assistant.io/docs/api/websocket/) and [trace implementation](https://github.com/home-assistant/core/tree/dev/homeassistant/components/trace). Live compatibility must still be verified against the installed HA release.
