# Maintenance tools — candidate 0.5.35

These three Settings pages are administrator-only and load on demand. Opening Future Homes Tech does not start a maintenance scan or add maintenance API requests to its preload. Device Health reads the existing inventory cache; Action Timeline observes the existing state stream without another Home Assistant subscription.

## Device Health

- Search device/room names and optionally show only devices needing attention.
- Reports entity availability, current unavailable-since timestamps, battery percentage/type, available firmware and progress.
- A firmware installation without a state update for 15 minutes is flagged as possibly stalled, not proven failed. There is no force-update or reset action.
- Last state change/report is not a network heartbeat. Sleeping battery devices are not marked offline just because they are quiet.
- Availability history is limited to the most recent 1,000 transitions since app startup, with up to 20 displayed per device. It resets on restart. Existing Home Assistant unavailable-since timestamps remain visible when provided.
- Refreshes cached reports every 30 seconds only while this page is visible. Expanded device details remain open. A stale cache is explicitly identified.

## Action Timeline

- Keeps the latest 2,000 observed changes in memory, searchable and paginated 100 at a time. It does not load historic recorder data on startup and resets on restart.
- Correlates automation/script and target changes by Home Assistant context IDs. Unmatched changes say **Source unavailable**; proximity in time is not treated as proof.
- Opens available HA trace summaries on demand. A summary is not a full causal trace and may be unavailable when HA has no stored trace or the registry identifier is missing.
- Does not return raw trace variables, action payloads, PIN helper values or webhook URLs. Current light brightness is included where reported.
- Protocol-level actions and physical changes without HA causal context cannot be attributed automatically.

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
