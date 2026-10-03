# Performance release 0.5.4

## Scope

Addresses the remaining battery/inventory processing and repeated action-catalog fetching found in the September 12 live check. The change does not alter mode behavior, physical automations, network integrations, alarm handling, or permissions. The broader deferred audit items remain separate unless explicitly included by the homeowner.

0.5.3 is now the homeowner-approved stable release. 0.5.4 is prepared for the homeowner to install and evaluate; mounting is not installation and does not advance the stable pointer.

## Changes

- State events replace one entry in an ID-indexed cache. The old and new snapshots remain independent; events arriving during a full refresh are still replayed.
- Snapshot readers capture record references and freshness together under a short lock, then copy only selected records outside that lock. Sorting occurs for a requested projection, not each state event.
- Rooms copy only their own entities and a small room/house-mode helper subset. The floor index copies only the fields it consumes. Battery requests copy battery sensors only and reuse registry metadata. Menu and security requests select their relevant domains.
- A separate metadata revision changes on additions, removals, renames, area/device reassignment, group membership, or capability changes. Ordinary readings no longer invalidate target catalogs. Room aliases and saved room modes, bedroom settings, wake settings, and switch settings still affect the catalog revision.
- Catalog entities omit live state values; actual live controls keep using room/dashboard state projections. A returned catalog revision replaces the older revision in the room payload, so reopening another subsection does not repeat that download.

## Local benchmark

`scripts/benchmark_inventory.py` compares the retained stable archive with current source using 4,000 synthetic entities, 100 batteries, and 20 rooms. Seven samples per operation, median shown. The measured operations exclude network and filesystem I/O; this is not an installed end-to-end benchmark.

| Warm-cache operation | Stable 0.5.3 | Candidate |
| --- | ---: | ---: |
| Battery projection | 150.191 ms | 3.330 ms |
| One-room projection | 109.460 ms | 5.818 ms |
| One state event | 0.685 ms | 0.007 ms |

The previous installed delays (battery request 6.9 seconds, room request about 2 seconds) include work not measured here. No equivalent installed 0.5.4 timing is claimed before installation.

## Acceptance after installation

The complete release gate passed 230 tests, including battery-only projection, no repeated registry reads, room alias preservation, ID-indexed updates, snapshot isolation, non-blocking live events during projection copying, metadata-only invalidation, and browser catalog revision reconciliation. Python and served/source browser syntax checks also passed.

Open Home Configurator, choose a floor and a room, then expand Switches and Buttons. Confirm the action catalog is reused while normal sensor readings arrive and open editors do not collapse. Check the battery popup and assigned battery types. Rename or move a test device only when appropriate, then refresh the affected room to verify metadata changes invalidate the catalog. Do not activate sirens, alarms, or physical loads merely to test performance.

Keep 0.5.3 stable until the homeowner explicitly approves a replacement.

## Published candidate verification

Home Assistant's refreshed update metadata reports installed 0.5.3, state `started`, available 0.5.4, and `update_available: true`. The candidate is mounted and ready for the homeowner to install; no live app update or restart was triggered in this pass.

Source and mounted runtime trees match SHA-256 `47007ecb1a368afe18504aa115626d8533e8bb2027378b1901c2afaca7cf7f4a`. The packaged runtime archive was independently read back and matched the same tree digest.
