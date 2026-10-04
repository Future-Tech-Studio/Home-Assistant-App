# Splitting server.py and index.html

`server.py` (about 13,000 lines) and `web/index.html` (about 11,000 lines, with
inline script and styles) are split one self-contained piece at a time, so each
step can be tested and released on its own.

## How each piece moves

1. Move a cohesive part into `future_homes_tech_app/fht_<name>.py` with no
   imports from `server.py` (pass in anything it needs).
2. Load it in `server.py` like `fht_access.py` and keep the old names working
   (a thin wrapper or an alias), so callers and tests do not change in the
   same step.
3. Add a `COPY` line to the `Dockerfile` (Beta installs follow those lines).
4. Run `scripts/build_release_manifest.py` and the full release gate.

Tests that patch `SERVER.<name>` only affect code still in `server.py`; when
moving code that tests patch, update those tests to patch the new module.

## Done

- `fht_catalog.py` (0.6.32): light and switch choices for every action editor.
  `server.action_catalog_from_entities` wraps it and adds room-mode and
  wake-override choices.
- `JsonSettingsStore` (0.7.21): one base for the sixteen JSON settings stores
  (path, lock, corrupt-file handling, `read()` via `_clean`, writes through
  `atomic_write_json`); each store keeps only its own `_clean` and `save`.
- `fht_ha_client.py` (0.8.12): the Home Assistant WebSocket client (handshake,
  frames, the shared connection, `execute_websocket_commands`, and
  `HomeAssistantAPIError`). `server.py` keeps every old name as an alias. Its
  tests are in `tests/test_ha_client.py` and patch `fht_ha_client`; the live
  updates loop stays in `server.py`, so its test still patches `SERVER`.

## Next, in order

1. Registry organizer (categories, renames, cleanup) → `fht_registry.py`.
2. Presence automations and presence groups → `fht_presence.py`.
3. Door, switch, and control automations → `fht_controls.py`.
4. HTTP handler routes, grouped by page, into small route modules.

For `index.html`: move the inline styles to `web/app.css` and page scripts
(Presence, Doors, Buttons, …) to modules under `web/`, updating
`interface_bundle` so they are still served with the CSP nonce and cache
headers.
