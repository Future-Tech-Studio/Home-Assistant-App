# Room Modes and Scenes — 0.5.5 candidate

## Customer flow

1. Open **Settings → Room Modes**. Existing bedroom selections are retained; other room-type mode sets are not invented.
2. Check or uncheck a mode. It saves automatically, with visible saving/failure feedback and a retry button. Selecting a mode does not put the room into that mode.
3. Open **Settings → Scenes → Room Scenes**. There is one expandable card per enabled room/mode. Its light picker is built only when that card is opened.
4. Choose lights or light groups, brightness, and optional color/temperature. Save Scene to activate the configuration. A brightness of 0% means off.
5. An actual transition of the existing room-mode helper into that mode applies the saved lighting scene. Saving or opening a scene does not operate lights. Restore-from-unavailable transitions do not run it.

Clearing targets removes the scene's lighting action. Unchecking a mode removes its scene automation and hides its card, but retains its saved configuration for re-enabling later. Existing specialized bedroom security/toddler behavior and other automations are not rewritten into this new scene model.

Adaptive scene color selects the current solar-based tone when the mode starts; it is not a continuous adaptive-lighting override. The color dialog explains this distinction. Existing Light Automations remain in their own tab.

## Loading and safety

- Lighting has no presence, opening, temperature, humidity, or lux header rows. Its API copies only FHT light groups, and sensor-only events no longer invalidate the Lighting screen.
- Security and Exterior status use their existing separate projections and continue updating.
- Room Modes uses the compact floor/room index, not full device discovery. Scene target metadata uses the revision-keyed shared editor catalog.
- A mode save invalidates dependent scene/editor data. An in-flight older scene response is retried rather than repopulating stale cards. Scene editors retain drafts when collapsed/reopened.
- Room-mode helper IDs remain stable; an empty enabled-mode list retains the room helper for existing references.
- Scene writes are serialized, atomic, and backed up by the existing bounded revision mechanism. Reload failure reports `saved: true, activated: false`; retry actually retries activation even when the generated file has not changed.

## Persistence and rollback

- Existing enabled-mode store: `/data/room_modes.json`.
- New scene store: `/data/room_scenes.json`.
- New generated package: `/homeassistant/packages/future_homes_tech_room_scenes.yaml`.
- Existing room helper package remains `future_homes_tech_bedroom_mode_automations.yaml`.
- 0.5.3 remains the homeowner-approved stable release. Neither its archives nor the private live-repair backups are removed by this release.

If rolling back after configuring scenes in 0.5.5, first stop the candidate and preserve the new scene JSON and generated YAML. Move **only** the new `future_homes_tech_room_scenes.yaml` package out of the included packages directory, install the stable source, and reload automations. Older releases do not know to remove that package. Keep the JSON for a future return to 0.5.5; do not delete existing bedroom, door, presence, or wake packages.

## Validation

- Full release gate covers Python, both source and served browser modules, bootstrap, regression tests, and release metadata.
- Backend regressions cover persistence/reopen, independent rooms, enable/disable/re-enable, helper creation without enabling specialized security behavior, scene generation, RGB/tone/adaptive data, 0% off, clearing targets, invalid inputs, saved-versus-activated failures and retries, and sensor-event/projection separation.
- Browser behavior regressions cover autosave, dependent cache invalidation, stale in-flight scene responses, progressive scene editors, escaped display names, brightness/color controls, and draft retention.
- An isolated browser preview with simulated rooms verifies navigation, selecting a mode, appearance of its corresponding scene card, multi-selection, color application, saving, and refresh persistence. No real lights or alarm devices are triggered for these checks.
- Mounted source and homeowner-installed runtime are separate; installation and physical mode-transition acceptance are performed after the update is offered.
