# Future Homes Tech App

![Future Homes Tech logo](logo.png)

The Future Homes Tech App provides an admin-only Home Assistant Ingress panel
and manages the Home Assistant packages that power Future Homes Tech controls.

## Interface

Implemented dashboards:

- **Lighting** — Area cards, light-group controls, brightness, presence,
  temperature, humidity, lux, and door/window status.
- **Security** — Door sensors grouped by Area with explicit unavailable state.

Implemented Settings pages:

- **Apple HomeKit** — light, climate, and security bridge selection.
- **Climate** — thermostat and schedule configuration.
- **Home Configurator** — Floors, Areas, switches, buttons, Door Actions,
  presence actions, Room Modes, Whole Home solar boundaries, and wake routines.
- **Scenes** — scheduled light automations and room-mode configuration.
- **UniFi** — Protect status and resources.

Amazon Alexa, Dashboards, Google Nest, the main Climate dashboard, and Shades
are visible placeholders. Retired standalone Automations, Blueprints, Buttons,
Entities, Light Groups, Presence, and Switches editors are not shipped.

## Live Data

The backend maintains one normalized Home Assistant entity snapshot and updates
it from `state_changed` WebSocket events. Registry events trigger a coordinated
metadata refresh. Browser panels wait on a lightweight revision feed and use a
30-second poll only as a reconnect fallback.

Home Configurator first loads a Floor/Area index and requests one room only when
that room opens. Background updates preserve the selected Floor, selected room,
open editors, scroll position, and unsaved drafts.

## Generated Configuration

The App owns separate package files for its generated light groups, presence
groups, control actions, presence actions, schedules, bedroom modes, wake
routines, HomeKit bridges, and base alarm helpers. Settings are written
atomically with bounded backups. Generation is serialized and activation
reports whether data was saved separately from whether Home Assistant reloaded
it successfully.

Legacy Door Actions and Actual Load settings are migrated into the shared
stable-ID action model. Compatibility readers remain so an existing
installation upgrades without losing assignments; retired HTTP and UI paths do
not remain exposed.

## Security Defaults

- Home Assistant Ingress only; `ALLOW_NON_INGRESS=1` is development-only.
- Admin-only panel.
- Bounded JSON request bodies, request deadlines, and worker concurrency.
- Strict CSP nonces, no inline event attributes, security headers, gzip, and
  immutable caching for fingerprinted assets.
- Protect certificate and hostname verification enabled by default.
- Installation-specific secret entry-delay webhook with disarm cancellation
  and final armed-state recheck.

## Verification

Run `../scripts/release_gate.sh`. It compiles Python, checks browser-module
syntax, executes the complete regression suite, and verifies version and asset
metadata. Passing locally does not prove a Home Assistant production runtime;
install each candidate, review logs, exercise controlled non-alarm test
entities, and obtain homeowner approval before moving the stable pointer.

See `DOCS.md` for the operator guide and `CHANGELOG.md` for release history.
