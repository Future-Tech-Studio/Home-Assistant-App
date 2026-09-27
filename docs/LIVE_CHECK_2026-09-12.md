# Installed 0.5.2 live check — September 12, 2026

Verified installed version 0.5.2 and state `started` through Home Assistant. Checks used the local Codex browser, not the wall panel hardware. No lights, modes, chimes, or sirens were activated.

## Performance observed

| Operation | Observed duration |
| --- | --- |
| Initial FHT iframe shell, from its own navigation | 727 ms (TTFB 471 ms, module 14 ms) |
| Reopened FHT iframe shell | 187 ms (TTFB 96 ms, module 6 ms) |
| Initial Home Configurator index request | 2,380 ms |
| Chloe's Bedroom room request | 1,958 ms |
| First shared editor catalog request | 1,507 ms |
| Opening Buttons later fetched the catalog again | 1,609 ms |
| Initial batteries request | 6,900 ms |
| Exterior status request samples | 1,359–4,636 ms |

Shell timings exclude Home Assistant's earlier ingress/session preparation. Exit changed to the Updates route within a 312 ms automation observation (including tool overhead); that is not a complete paint benchmark. Updates subsequently rendered without a new Home Assistant launch screen.

Room subsections initially showed only headers. Switches rendered on expansion and reopening retained the editor without a new room request. Buttons displayed two numbered cards with four gestures each. The Switches section stayed open while Buttons loaded.

Catalog reuse is still too easily invalidated: the saved room revision differs from later catalog revisions as live inventory changes. It fetched the catalog again for a second subsection of the same room. A metadata-focused revision and reconciling the room's catalog revision would reduce this further. Battery/inventory processing remains a substantial delay. Protect status and NVR requests still return 502; that previously skipped problem was not changed.

## Repair status at initial inspection

Startup logs report `Reference repair deferred (ValueError); no settings changed`, including the 0.5.2 startup at 08:21:56. The earlier mounted release was therefore not evidence of completed live repair.

A Home Assistant app-only backup was created before further repair work: `dc62b7b5`, named `FHT before live reference repair 2026-09-12`, file `/backup/fht_before_live_repair_20260912.tar`. This is separate from the source release archives and contains the private app settings. Do not publish it.

## Approved conflict resolution

The homeowner authorized retaining current settings and archiving older conflicting copies. The private snapshot confirmed Bathroom 1 toilet presence had older Night 25% / Sleep 5% versus current Night 28% / Sleep 25%. The current values must survive.

Release 0.5.3 implements this policy only where the original dictionary contains the canonical current key. Multiple legacy values without a canonical current entry still fail safely. All changed originals are archived before writes, and a private manifest records archived keys. No device registry entries are deleted.

The full release gate passed 223 tests. Source and mounted runtime trees match SHA-256 `05e30589ec206bab783617be4933f397538a2a72e33bd08de4e0e5a3da2df6a4`. Home Assistant reported installed 0.5.2, available 0.5.3; the targeted update was then requested. Live completion is recorded below once verified.

## Live installation and repair result

Home Assistant completed the targeted update and reported version 0.5.3, state `started`. Startup reported six saved files updated, zero reviewed rename candidates left unchanged, and backup `/data/reference-repair-0.5.1`.

Older conflicting copies were archived while current settings were retained:

- `presence_light_group_assignments.json`: 3 conflicts.
- `presence_light_group_timings.json`: 1 conflict.
- `presence_mode_settings.json`: 7 conflicts.

This confirms the previously deferred startup migration executed; it is not a claim that every legacy dashboard or registry helper has been repaired or deleted. The installed patch changes conflict handling, not the performance findings measured on 0.5.2.

An after-repair app backup (`79ac8228`, `/backup/fht_after_live_repair_20260912.tar`) independently confirmed the private manifest is `complete`, contains 20 verified mappings, and reports zero registry entities deleted. Its saved Bathroom 1 toilet presence settings retain Day 100%, Night 28%, Sleep 25%, all enabled; the obsolete repeated-area key is absent.

The six changed files were switch controls, door light-group assignments, presence light-group assignments, presence light-group timings, presence mode settings, and HomeKit climate entities. Original copies remain in the private migration archive and the pre-repair app backup.

Home Assistant's configuration check completed successfully after the repair. Reloading the app displayed V 0.5.3. No Home Assistant core reboot or physical action test was performed.
