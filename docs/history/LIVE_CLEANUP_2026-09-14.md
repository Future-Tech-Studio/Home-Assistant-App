# Home Assistant cleanup — September 14, 2026

## Result

Removed **726 retired entity-registry entries** from the live Home Assistant installation using Home Assistant's supported entity-management UI:

| Type | Removed |
| --- | ---: |
| Obsolete input-select/dropdown helpers | 536 |
| Obsolete input-text helpers | 43 |
| Old switch-sync guard helper | 1 |
| Obsolete automation entries | 145 |
| Obsolete room-mode generator script entry | 1 |
| **Total** | **726** |

These were restored/unavailable entries that Home Assistant marked **Not provided**, not functioning automations or active settings. Their definitions were absent from the current configuration, and the audit found no references in the configuration and current app settings reviewed. No active YAML automation files were deleted.

The first batch contained 536 dropdown helpers. A safety check stopped the second batch; the homeowner explicitly approved the exact remaining 190 entries before they were removed.

## Verification

- Before/after entity-ID comparison confirmed exactly 726 removals, all within the approved manifest; **zero unexpected removals** and **zero approved candidates remaining**.
- Registry count changed from 3,335 to 2,610. One new Master Bathroom toilet-switch automation registered during the audit and was left untouched, explaining the additional entity in the final total.
- Home Assistant configuration validation returned `{"result":"ok","data":{}}` during the cleanup. No configuration files were changed by the cleanup.
- Installed Future Homes Tech remains **0.5.33**, state **started**. Local source is **0.5.34**; this task did not publish or install a release.
- Approved stable **0.5.23** and its source/mounted archive checksums were verified and preserved. No stable promotion occurred.
- No Home Assistant restart, network reset, device unpairing, firmware installation, alarm action, or physical-light test was performed.

## Recovery and evidence

A fresh Home Assistant configuration plus installed FHT app backup was created and its contents verified before deletion:

- Backup name: `FHT before obsolete-item cleanup 2026-09-14`
- Backup slug: `dfafc111`
- Home Assistant host path: `/backup/fht_before_cleanup_20260914.tar`
- Contains `homeassistant.tar.gz`, `local_future_homes_tech_app.tar.gz`, and backup metadata.
- Home Assistant version: **2026.9.2**. App version in this backup: **0.5.33**.
- Recorder database was excluded. This is a private, unencrypted backup; do not publish it or attach it to a public issue.

Private audit evidence remains on the Home Assistant host under `/addons/fht-cleanup-audit-20260914/`, including `registry.json`, `restored_review_full.json`, `approved-obsolete-candidates.json`, and `cleanup-result.json`. These host paths are not local Mac paths.

Home Assistant documents normal backup restoration in its [backup guidance](https://www.home-assistant.io/common-tasks/general/#backups). Restoring the configuration/app backup is a recovery operation, not a per-entity Undo; preserve newer settings before a rollback.

## Intentionally retained

- Active user-created helpers, current room names, presence settings, switch/button assignments, scenes, modes, reservations, and credentials.
- Device/integration entries, including offline devices. Unavailable does not by itself mean unused.
- **62 legacy group entries and 5 template-presence entries**. Some still appear in live definitions or references. Of these, 14 group and 3 template entries are additional unreferenced candidates, but were left for a separate group/presence mapping review rather than included in the approved helper/automation batch.
- Three restored SleepIQ entries belonging to an existing bed integration.
- Stable releases, existing backups, database/history, integrations, and network credentials.

The audit covered registered entities, runtime state, current root/package configuration, dashboard references, helper/integration storage, and entity-ID references in current private FHT settings. It cannot prove the absence of references on external controllers or in dynamically constructed third-party templates. Therefore this is a completed approved cleanup batch, not a claim that every unavailable item is now safe to delete.

## Other findings

- The pre-cleanup runtime inventory included **36 non-restored unavailable entities** in the physical-device domains reviewed, alongside restored leftovers. Examples included Stairway PIR 1, Office Everything Presence Pro, several room/entry door sensors, and refrigerator door sensors 3 and 4. They were retained for connectivity diagnosis, not treated as rubbish.
- Two live group pairs had identical members: Kitchen RGB / Kitchen Switch RGB, and Outside Perimeter Side Yard / Yard. Existing assignments must be checked and migrated before consolidating them.
- Kitchen All Lights included the switch RGB indicator light. Confirm whether that indicator should belong in a room-wide lighting command before changing membership.
- Repairs showed no pending repairs. Storage showed 84% used and approximately 4.4 GB free before the new backup; this is not a post-cleanup free-space measurement.
- The repository roadmap still describes early modules as future work although many are already implemented. Future planning should use the current code and changelog rather than that old roadmap alone.

## Recommended next five features

1. **Device Health and Firmware Center.** One view for genuinely offline devices, last-seen/last-recovered times, battery health, and stalled update attempts. Distinguish sleeping devices, unreachable devices, and orphaned registry entries. Do not automatically reset networks or unpair devices.
2. **Automation “Why?” Timeline.** Show which switch, presence sensor, door rule, room mode, or schedule last changed a light, including brightness and competing actions. Build on Home Assistant's existing [automation traces](https://www.home-assistant.io/docs/automation/troubleshooting/#traces) rather than introducing another opaque automation engine.
3. **Safe Cleanup and Group Manager.** Track app ownership, canonical groups, dependencies, and generation version. Provide a dry-run manifest, reference-preserving migration, protected current settings, and a recoverable retirement flow so hundreds of abandoned helpers do not accumulate again.
4. **Installer Acceptance and Performance Checks.** Add non-actuating previews for Day/Night/Sleep rules, missing-target checks, cache-age/startup timing, and a release checklist with backup verification. Any real siren, webhook, lock, or light test must be separately initiated and clearly labeled.
5. **Secure Room/Guest Wall Panels.** Finish device enrollment and tightly scoped room-control/arm-disarm actions for NSPanel/Shelly displays, using the Users/reservation/PIN groundwork already present. Add revocation and access logging without exposing administrator credentials; future lock programming remains a separate supported-device integration.

These are recommendations only. No feature code or release metadata was changed in this task.
