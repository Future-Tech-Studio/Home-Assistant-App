# Candidate 0.5.35 — local validation

Date: September 14, 2026

## Included

- Device Health, Action Timeline and Safe Cleanup Settings pages.
- Existing 0.5.34 single-member fixture naming correction.
- No changes to live devices, networks, automations or registry entries during development.

## Results

- Release gate: **318 tests passed**, including Python compilation, browser module syntax and synchronized version/runtime asset validation.
- Maintenance browser fixture: passed lazy loading without startup maintenance requests, battery/offline display, preserved expansion, trace summaries, exact archive confirmation and recovery, desktop/mobile layout and modal sizing. No browser JavaScript errors.
- Existing Users browser fixture: passed account, PIN, reservation, approval, group, panel-plan, audit and mobile flows. No startup Users requests added.
- Administrator-only reads/writes, CSRF enforcement, private error responses, stale-plan rejection, partial-change recovery, protected entities and journal permissions have automated coverage.
- Device Health honors existing homeowner battery-type assignments before reported types.

Screenshots from isolated fixtures: `/tmp/fht-maintenance-health-desktop.png`, `/tmp/fht-maintenance-cleanup-desktop.png`, `/tmp/fht-maintenance-mobile.png`, `/tmp/fht-maintenance-modal-mobile.png`. These are not live Home Assistant screenshots.

## Stable protection

Approved 0.5.23 remains unchanged. Both saved archives still match STABLE.json:

- Source SHA-256: `b200fafc076c36526851d4205197c5c2cbfcf09f36b4043506327fefd4d0c6c0`
- Runtime SHA-256: `569b949be9d0645596485b777c7f8d1637cc558ef5d6857e1078753065ca5e80`

## Deployment status

The add-on/config shares were not mounted during packaging. This is a **local candidate, not published or installed**. A Home Assistant/Supervisor build and live smoke test remain outstanding. Availability/timeline histories start when the app starts, are memory-bounded, and reset on app restart; only cleanup recovery journals persist.

After mounting and installing: verify the three Settings pages as an administrator, deny access as a non-admin, compare health against known live entities, inspect an ordinary automation's context/trace, and run a read-only cleanup scan. Do not archive any real helpers until the installer reviews the exact candidates and external references.
