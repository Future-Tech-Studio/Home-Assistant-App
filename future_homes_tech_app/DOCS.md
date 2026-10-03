# Future Homes Tech App Operator Guide

## Purpose

The Future Homes Tech App is an admin-only Home Assistant Ingress application.
It provides dashboards and customer-facing configuration editors while writing
Future Homes Tech-owned helpers and native automations into separate Home
Assistant package files.

## Current Navigation

Main navigation:

- Dashboard
- Lighting
- Security
- Climate placeholder
- Shades placeholder

Settings navigation:

- Amazon Alexa placeholder
- Apple HomeKit
- Climate configuration
- Dashboards placeholder
- Google Nest placeholder
- Home Configurator
- Scenes
- UniFi
- Future Tech Portal (push reports to the portal; see `docs/FUTURE_TECH_PORTAL.md`)

Retired standalone Automations, Blueprints, Buttons, Entities, Light Groups,
Presence, and Switches pages are intentionally absent. Their active
configuration functions have moved into Home Configurator or are generated in
the background.

## Startup Order

### Add-on process

Before the web server starts, `run.sh` performs these ordered setup steps:

1. Read and validate App options.
2. Apply the base Future Homes Tech package and private entry-delay secret.
3. Migrate the legacy Climate package when needed.
4. Generate Future Homes Tech light groups.
5. Start the Ingress web server.

Once the server starts, independent background workers:

1. Open the shared Home Assistant state WebSocket cache.
2. Publish Protect arm status when Protect is configured.
3. Organize generated light groups in Home Assistant registries.
4. Generate all App-owned automation packages and activate one coordinated
   configuration revision.

### Browser panel

The browser renders the navigation shell before waiting for application data.
It then:

1. Enters kiosk presentation and starts the lightweight revision watcher.
2. Registers recurring refresh fallbacks.
3. Immediately requests the single configured weather entity and App update
   information.
4. During browser idle time, warms Protect status, Protect resources, the
   shared entity cache, Home Configurator's Floor/Area index, and offline
   counts.
5. Loads a dashboard or Settings payload when the user opens that view.
6. Home Configurator loads only the selected room body. It does not render
   every room's editors up front.

The browser console logs shell and warmup timing. These timings distinguish
HTML first display from later background data readiness.

## Live State And Caching

The backend owns one normalized entity snapshot. It initially reads Home
Assistant states once, then applies `state_changed` WebSocket events in place.
Entity, device, Area, or Floor registry events cause one coordinated metadata
refresh. Lighting, Security, and room payloads are projections from this
shared snapshot.

Each projection includes revision and freshness information. Safety-related
data becomes stale or unavailable when the live connection or evidence age is
not acceptable. The interface must not retain a false green state.

Browsers use `/api/live/revision` long polling to learn which projections need
updating. A 30-second visible-view refresh remains as a reconnect fallback, not
the primary state transport. Settings payloads use bounded in-document caches
and a page-local Refresh button.

## Home Configurator

Home Configurator builds navigation from Home Assistant Floor and Area
registries, including empty configuration destinations. Opening a room requests
one room payload containing only the data needed for these progressive cards:

- Buttons
- Door Actions
- Presence
- Room Modes
- Switches
- Wake Up Routine

The Whole Home Floor contains global Day/Night boundaries. Day and Night can be
offset from sunrise and sunset by -120 through +120 minutes. Sleep mode takes
precedence when a configured bedroom is in Sleep. If solar data is unavailable,
the App preserves a valid existing Day/Night value or reports Unknown instead
of inventing a boundary.

Background room updates preserve the selected Floor, room, open sections,
scroll position, and unsaved inputs. A delayed response is not allowed to
overwrite a newer interaction.

## Shared Actions

Switches, buttons, Door Actions, and reusable action editors consume the same
capability catalog. Targets use stable Home Assistant entity IDs. Presentation
is ordered as:

1. Light Groups and unnumbered light targets
2. Switches, fans, and plugs
3. Room Modes
4. Wake Overrides
5. Numbered individual lights

Distinct entities with duplicate friendly names remain selectable with an
Area/device hint. Previously saved but unavailable targets stay visible until
the homeowner removes them. Multiple actions may be selected, reviewed in the
summary, and cleared explicitly.

Legacy Door Action and Actual Load stores are read once for migration into this
model. After schema migration completes, clearing a shared action cannot be
undone by a later restart. The old public Door and standalone editor endpoints
are not exposed.

## Configuration Activation

Configuration-changing POST requests share one mutation lock. JSON bodies are
limited to 1 MiB and must be objects. Data and generated packages are written
atomically, with up to five previous file revisions retained beside the active
file.

Saves report persistence separately from Home Assistant activation. A response
may therefore say that a setting was saved but its reload failed. In that case,
fix the reported Home Assistant error and retry activation; do not assume the
runtime changed merely because the JSON file was written.

Some Home Assistant reload services are global by design. The App batches
startup generation into one coherent pass and limits routine saves to the
smallest available managed-domain reload. Delay-sensitive exterior-door state
uses persistent helpers and a deadline so a reload cannot silently discard the
alarm decision.

## Future Tech Portal

Settings → Future Tech Portal stores the portal token only in
`/homeassistant/secrets.yaml` as `future_tech_token` and writes
`/homeassistant/packages/future_tech_portal.yaml`, which reads it with
`!secret`. Home Assistant only pushes reports to the portal over HTTPS; it
accepts nothing back. The App never stores, logs or returns the token. Saving
or replacing the token reloads `rest_command`, `template`, `script` and
`automation` and sends the first inventory. Removing it deletes the package
before the secret line so the configuration stays valid. See
`docs/FUTURE_TECH_PORTAL.md` for what is reported and how errors are handled.

## Entry Delay Safety

The exterior-door webhook ID is generated per installation and stored as
`future_homes_tech_entry_delay_webhook_id` in `secrets.yaml`. Treat the complete
webhook URL as a credential.

On receipt, the managed automation:

1. Requires a currently armed state.
2. Records a pending flag and absolute deadline.
3. Starts the managed timer.
4. Cancels pending escalation when the system disarms.
5. Rechecks the armed state immediately before invoking the configured siren
   action.

Never publish or reuse the webhook ID across homes.

## Protect TLS

`protect_verify_ssl` defaults to `true`. If the Protect endpoint uses a private
certificate, place the trusted CA file where the App can read it and set
`protect_ca_certificate` to that path. Do not disable verification merely to
suppress an unknown-certificate error. The compatibility override logs a
visible security warning whenever it is disabled.

HTTP webhook values are accepted only for private or local destinations;
public destinations require HTTPS. Credentials embedded in URLs are rejected.

## HTTP Boundary

- Requests are limited to the configured Home Assistant Ingress proxy unless
  the development-only `ALLOW_NON_INGRESS=1` override is set.
- The server has bounded worker concurrency and socket deadlines.
- API JSON is never browser-cached and is gzip-compressed when useful.
- The HTML shell is revalidated; fingerprinted images are cached immutably.
- CSP nonces protect the inline module and stylesheet; inline event attributes
  are not used.
- Structured logs include request ID, method, path, status, and latency without
  logging API keys or entity payloads.

## Refresh Intervals

- Protect arm status: 60 seconds
- App update information: 60 seconds
- Weather temperature: 15 minutes
- Settings offline counts: 5 minutes
- Protect NVR object: 60 minutes
- Visible Lighting and Security fallback: 30 seconds

Live WebSocket revisions normally update active state sooner than these
fallbacks.

## Release And Rollback

Run:

```bash
../scripts/release_gate.sh
```

The gate compiles all Python entry points, checks browser-module syntax, runs
the full regression suite, and verifies synchronized version and static asset
metadata.

After mounting the exact tested App directory, package a candidate:

```bash
../scripts/package_candidate.py VERSION
```

The packager compares every source and mounted file by SHA-256, writes source
and mounted archives plus `MANIFEST.json`, and refuses to overwrite the
user-designated stable version. `stable_releases/STABLE.json` changes only when
the homeowner explicitly says a candidate is stable.

Local tests and matching mounted files are not production verification. Before
promotion, install the candidate in Home Assistant, inspect startup logs,
confirm the live-state connection, open and preserve a Home Configurator draft,
exercise non-alarm test actions, and verify safety status fail-closed behavior.

## Troubleshooting

- **Panel opens slowly:** inspect browser console `[FHT startup]` timings and
  `/api/health` freshness through Ingress. Separate first HTML display from
  background cache readiness.
- **Status is unavailable:** check `live_connected`, `last_event_at`,
  `cache_age_seconds`, and `last_error` in the health response before forcing a
  refresh.
- **Setting says saved but not activated:** inspect Home Assistant logs for the
  generated package error, correct it, and refresh that Settings page.
- **Protect fails after enabling verification:** configure the correct trusted
  CA and hostname; do not silently revert to insecure TLS.
- **A migrated target is unavailable:** keep it visible until its entity ID is
  restored or explicitly remove it from the multi-action selector.
# Quick switch brightness override

Non-Inovelli switch channels with verified dimmable wired or assigned light targets support an off/on cycle within three seconds. Only dimmable leaf lights receive 100% brightness. The generated override helpers prevent presence activation or house-mode changes from dimming those targets until the lights turn off; the normal presence vacancy timer still turns them off. Restarting Home Assistant clears overrides.

Both transitions must lack a Home Assistant parent context and user ID. This rejects attributed automation, synchronization, and UI changes, but integrations that discard command context cannot reliably distinguish physical presses from remote commands. Before promoting this build, verify a physical quick cycle, a cycle longer than three seconds, presence reactivation, vacancy timeout, an Inovelli device, a non-dimmable load, and automation-driven switching on the installed hardware.
