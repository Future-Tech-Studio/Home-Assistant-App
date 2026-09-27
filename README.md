# Future Homes Tech Home Assistant App

![Future Homes Tech logo](future_homes_tech_app/logo.png)

This repository contains the Future Homes Tech Home Assistant App. Home
Assistant formerly called Apps add-ons. Install it from the Home Assistant App
Store, not HACS.

## Current Capabilities

- Lighting and Security dashboards with live, stale-aware status.
- Home Configurator organized by Home Assistant Floor and Area registries.
- Settings → Doors, Switches, and Buttons provide room-grouped action editors,
  loaded when a room expands. Door and switch status updates keep editors open
  and preserve in-progress changes.
- Shared multi-action configuration for wall switches, buttons, doors, and
  presence sensors.
- Room modes, Whole Home day/night solar offsets, wake routines, and scheduled
  lighting.
- Apple HomeKit light, climate, and security bridge selection.
- UniFi Protect arm-mode and resource status.
- Generated Future Homes Tech light groups, presence groups, helpers, and
  native Home Assistant automations.

The Amazon Alexa, Dashboards, Google Nest, main Climate dashboard, and Shades
dashboard entries are placeholders. Climate configuration under Settings is
implemented separately.

## Safety And Data Flow

- The panel is admin-only and accepts requests from Home Assistant Ingress by
  default.
- Home Assistant live states are maintained in one backend WebSocket cache.
  Lighting, Security, Batteries, and Home Configurator read projections from
  that shared cache instead of repeatedly downloading the full entity list.
- Safety status becomes stale or unavailable when evidence expires; an old
  green state is not treated as current truth.
- Protect TLS verification is enabled by default. A trusted local CA can be
  configured when the Protect certificate is private or self-signed.
- The exterior-door entry-delay webhook ID is installation-specific and must
  be treated as a secret. Pending entry delays are persisted, cancelled on
  disarm, and rechecked before escalation.

## App Options

- `protect_api_key`
- `protect_verify_ssl`
- `protect_ca_certificate`
- `entry_delay_seconds`
- `entry_delay_webhook_id`
- `armed_away_interior_door_webhook`
- `armed_stay_kids_interior_door_webhook`
- `beta_mode` (off by default; switches this installation to Beta updates)

## Stable And Beta Channels

`main` is the Stable channel that every installation follows. In-development
work goes to the `beta` branch. Only installations with `beta_mode` turned on
are offered Beta updates; installing one restarts only the App.
See `docs/BETA_CHANNEL.md`.

Secrets remain in Home Assistant configuration or the App's private data
volume. Do not place credentials in this repository.

## Local Installation

1. Copy `future_homes_tech_app` into a subdirectory of Home Assistant's
   `/addons` directory.
2. Reload the App Store.
3. Install or rebuild the `Future Homes Tech App` local App.
4. Start the App and open its Ingress panel.

## Release Gate

Run the complete local release gate before packaging:

```bash
./scripts/release_gate.sh
```

Create a candidate only after mounting the exact tested source:

```bash
./scripts/package_candidate.py VERSION
```

The user-designated rollback is recorded in `stable_releases/STABLE.json`.
Candidate packaging never advances that pointer. A newer version becomes stable
only after the homeowner explicitly approves it following Home Assistant
runtime testing.

See `future_homes_tech_app/DOCS.md` for operation, startup, security, and
troubleshooting details. See `future_homes_tech_app/CHANGELOG.md` for version
history.
