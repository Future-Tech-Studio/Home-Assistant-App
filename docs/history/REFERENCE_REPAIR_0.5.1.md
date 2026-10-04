# Reference repair release 0.5.1

The homeowner retired the 0.4.80 stable hold on September 11, 2026. Its immutable recovery archives remain available. 0.5.1 is a candidate until accepted after installation.

## What installation does

Before managed configuration is generated, the add-on checks the 18 reviewed repeated-area renames against the current registry and live states. An old ID must be absent from both; its replacement must be enabled and loaded. The repair updates private saved assignments, including mode-specific door keys, rather than just replacing generated YAML that would revert later.

Light-group references are consolidated only when recursive live light membership is exactly identical to a canonical FHT group. Empty, unavailable, cyclic, missing, or ambiguous non-group memberships are not merged. Existing registry entities are not deleted: unknown external consumers were not covered by the audit. Duplicate saved entity-target selections and identical colliding assignments are combined. Different colliding assignments defer the entire repair.

This release does not edit active Home Assistant `.storage` files, the Wall Controllers dashboard, native automations, device pairings, or Protect/Exterior settings. The unresolved bedroom subgroup references remain unchanged; redirecting them to All Lights would change behavior without evidence.

## Verification and rollback

- Mounting source does not change private saved settings. Install 0.5.1 and inspect the add-on log for `Reference repair:`. A deferred repair leaves data unchanged and retries at the next add-on start.
- A successful repair records files, mappings, and skipped rename candidates in `/data/reference-repair-0.5.1/manifest.json` inside the FHT add-on container. It does not repeatedly query Home Assistant on subsequent starts.
- Original changed settings are saved beside that manifest; managed FHT YAML is copied into its `packages` directory before generation. These files can contain private configuration and stay private, not on the public add-on share.
- If interrupted during writes, the next start restores originals and stops before generators. An administrator must inspect the backup before retrying; do not delete a pending manifest without recovery.
- To undo a completed migration, stop the FHT app, preserve any newer settings, then restore only the manifest-listed private settings from that backup using container-level access. Restore the archived managed packages if returning to the old release, validate Home Assistant configuration, and restart/reload only after review. Do not overwrite unrelated Home Assistant configuration or its live registry.
- Verify saved targets persist across an add-on restart and inspect regenerated configuration. No physical lights, alarms, or sirens are exercised by automated tests.

The broader unresolved-ID and legacy-group audit remains in `REFERENCE_REPAIR_PLAN_2026-09-10.md`; its historical counts are not a claim of completed live repair.
