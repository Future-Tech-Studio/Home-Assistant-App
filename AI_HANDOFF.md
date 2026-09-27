# AI Handoff

## Project

This repository is the Future Homes Tech Home Assistant App. The add-on source
is in `future_homes_tech_app/`. It is installed as a local Home Assistant add-on
through the mounted share at `/Volumes/addons/future_homes_tech_app` on the
original development Mac.

## Current Release State

- Current stable (Stable channel, `main`): `0.6.1`
- Beta channel: `beta` branch, next version `0.6.2`
- Stable 0.5.23 was retired by the homeowner on 2026-09-27
- Do not promote a newer candidate to stable until the homeowner explicitly
  confirms that installed runtime behavior is stable.
- The current candidate adds Parent Presence Groups. A selected same-area
  presence group prevents a child sensor's clear action from turning its lights
  off while that parent group remains occupied.

## Required Workflow

0. Develop on the `beta` branch. `main` is the Stable channel every
   installation follows; merge into it only after homeowner approval. See
   `docs/BETA_CHANNEL.md`.
1. Work in the nested repository root containing this file.
2. Keep changes focused and preserve existing Home Assistant assignments.
3. Update `future_homes_tech_app/config.yaml`, the visible browser version, the
   JavaScript `CLIENT_VERSION`, and `future_homes_tech_app/CHANGELOG.md` together.
4. Run `./scripts/release_gate.sh` before packaging or mounting.
5. Mount the exact tested source to the local add-on share.
6. Verify mounted and source checksums match.
7. Package with `./scripts/package_candidate.py VERSION`.
8. Never change `stable_releases/STABLE.json` without explicit homeowner
   approval after live Home Assistant testing.

## Local Test Runtime

The original Mac uses bundled Codex runtimes when system dependencies are not
available:

```bash
export PYTHON_BIN="$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"
export FHT_NODE_BINARY="$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node"
export FHT_PLAYWRIGHT="$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright"
./scripts/release_gate.sh
```

## Verification At Handoff

Release `0.6.1` passed 365 Python and browser checks in the cloud release
gate. It has not yet been mounted or packaged on the development Mac.

## Security Boundary

- Never commit Home Assistant secrets, Supervisor tokens, PINs, private webhook
  identifiers, Protect API keys, or data from the add-on's private `/data`
  directory.
- App defaults may contain a non-secret internal DeviceAlarm endpoint, but real
  credentials remain in Home Assistant add-on options or private storage.
- Do not commit generated candidate archives or mounted rollback tarballs.

## Key Files

- `future_homes_tech_app/server.py`: backend API, persistence, discovery, and
  generated automations.
- `future_homes_tech_app/web/index.html`: main interface and client behavior.
- `future_homes_tech_app/config.yaml`: Home Assistant add-on metadata/options.
- `tests/`: backend, browser, startup, security, and regression coverage.
- `scripts/release_gate.sh`: required release verification.
- `stable_releases/STABLE.json`: homeowner-approved rollback pointer.
