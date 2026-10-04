# Changelog

## 0.5.152

- Refresh grouped presence sensors whenever Presence data loads, so newly added numbered PIRs create their room group automatically.

## 0.5.151

- Match Switches and Presence to Home Configurator and Doors with shared room headings, typography, glass cards, accent borders, spacing, and control styling.

## 0.5.150

- Use Fan Lights as the sole generated light group when every light in an area is a fan bulb.
- Move saved controls and HomeKit selections to that group, then automatically remove verified unused legacy fan group registry entries after reload.

## 0.5.149

- Remove retired Bedroom 5 and 6 fan group choices when the active All Lights group covers the same bulbs; migrate saved actions to the active group.

## 0.5.148

- Repair saved Play Room door actions that still target the retired, unavailable fan light group by moving them to the active group with the same two bulbs.

## 0.5.147

- Show each room's main door first, followed by its other doors alphabetically, preserving the existing responsive columns.

## 0.5.146

- Align Timeout labels with door names and selector text; match timeout dropdown height, typography, and theme border to the action selector.

## 0.5.145

- Match checkbox and dimmer accents to the selected Blue, Red, or Green app theme; keep loading indicators white.

## 0.5.144

- Order door modes as room Sleep, Day, Night, then a white divider and additional modes.
- Bedroom closet doors ignore Whole Home/Floor Sleep and use the bedroom's local modes, with solar Day/Night fallback using configured offsets.

## 0.5.143

- On wide tablet/desktop layouts, multi-door rooms span both columns and arrange doors side by side; single-door rooms occupy one column.
- Keep phone layouts single-column.

## 0.5.142

- Remove nested Door action cards and redundant Action labels; match Home Configurator label typography while preserving selectors and behavior.

## 0.5.141

- Match Door cards to Presence: one action picker, followed by timeout and mode brightness controls only when targets are assigned.
- Add an optional 1–120 minute timeout starting when the door opens; closing the door cancels the timer and turns lights off immediately.
- Save each door's targets and mode settings together, with background saves queued in order.

## 0.5.140

- Add optional Quiet room mode alongside Sleep, with independent actions and presence settings.
- Quiet stays local to the room and does not qualify as Whole Home or Floor Sleep.

## 0.5.139

- Door actions include Day, Night, Whole Home Sleep, the area's floor Sleep, and enabled room modes with individual light and color settings.
- Active room overrides take precedence over floor Sleep, Whole Home Sleep, and Day/Night; closing the door still clears assigned lights.
- Preserve existing mode assignments and background save-on-close behavior.

## 0.5.138

- Preserve and display existing Day/Night/Sleep door assignments outside the Pantry.
- Save switch and door multi-light selections when the picker closes, rather than after each checkbox.
- Allow door-close light shutoff even when the house mode changed since opening.

## 0.5.137

- Keeps Home Configurator, Doors, Switches and Presence cards hidden until their progress bar completes, then reveals the finished page together.

## 0.5.136

- Removes technical entity-ID subtitles from Door action dropdowns, matching the friendly-name-only Switches formatting.

## 0.5.135

- Places whole room sections side by side on wider Doors layouts, keeping each room's doors together and stacking rooms on phones.

## 0.5.134

- Makes navigation labels, selected-page highlights and hover backgrounds follow the red or green app theme.

## 0.5.133

- Groups each room's doors into one highlighted glass card with transparent action rows, matching Home Configurator.

## 0.5.132

- Adds saved Blue, Red and Green App Color choices in Whole Home Modes for backgrounds, shields, borders and card highlights.
- Preserves blue assets and saves appearance separately from automation settings.

## 0.5.131

- Applies Home Configurator's fading glass header, hide/reveal scrolling, responsive spacing, labels and field sizing to Doors.
- Preserves door assignments and automation settings.

## 0.5.130

- Renames the global Sleep label to Whole Home Sleep.

## 0.5.129

- Aligns mode and room-name labels with the inset text inside their controls.
- Halves the gap between section titles and their cards from 16 to 8 pixels.

## 0.5.128

- Removes inherited glass blur from individual Room Names rows, preserving the parent card and editable fields.

## 0.5.127

- Moves Whole Home Modes up ten pixels on iPhone while preserving tablet spacing and header positioning.

## 0.5.126

- Raises the iPhone Home Configurator header another four pixels, leaving tablet positioning unchanged.

## 0.5.125

- Raises the iPhone Home Configurator header another six pixels, leaving tablet positioning unchanged.

## 0.5.124

- Raises the iPhone Home Configurator header controls and glass edge three pixels without changing tablet positioning.

## 0.5.123

- Changes the Home Configurator header to frosted translucent black glass fading across its full height to transparent.

## 0.5.122

- Restores white text in the Whole Home Modes Day and Night dropdowns.

## 0.5.121

- Softens the black Home Configurator header with a subtle 12-pixel glass fade along its bottom edge.

## 0.5.120

- Gives the Home Configurator header a solid black background that scrolls with its controls.

## 0.5.119

- Home Configurator header controls scroll out of view and reveal before reverse touch or wheel scrolling moves the page.
- Keeps dropdown and text-field interactions independent and resets header visibility on navigation or resize.

## 0.5.118

- Raises the first Home Configurator title eight pixels on phones and four pixels on compact tablets, preserving header and safe-area clearance.

## 0.5.117

- Tightens mobile Home Configurator top spacing and mode-row spacing.
- Matches room labels and field dimensions to Whole Home Modes controls.
- Moves Room Names onto the transparent page background above its card.

## 0.5.116

- Places each room name above its full-width editable field.
- Aligns mobile and tablet update and exit controls with the menu logo.

## 0.5.115

- Moves Whole Home Modes above its card as a centered title on the transparent background.
- Removes the enclosing border and background from mode rows while retaining the dropdown controls.

## 0.5.114

- Lowers the tablet-width menu logo four pixels while preserving phone and desktop positioning.

## 0.5.113

- Moves mobile header controls up four pixels on inset screens and brings Whole Home Modes up eight pixels while retaining separation from the controls.

## 0.5.112

- Whole Home mode controls and Room Names rows use two columns when the available content width reaches 640 pixels, and one column on narrower split views and phones.
- Keeps both main cards full-width and mode labels above their selectors.

## 0.5.111

- Places Whole Home mode labels on their own rows with full-width dropdowns beneath them, including Day, Night and Sleep selections.

## 0.5.110

- Adds clearance between the floating header and Whole Home Modes on tablet and phone.
- Moves the mobile logo and floating controls slightly upward without entering the device safe area.

## 0.5.109

- Orders Room Names by bedrooms first, bathrooms second, then remaining rooms alphabetically, with natural numeric ordering within each section.

## 0.5.108

- Makes Whole Home Modes full-width and aligns both edges with Room Names on desktop, tablet and phone.

## 0.5.107

- Door labels use current room display names instead of generic Bedroom Door, including Playroom Door and Maverick’s Door.
- Normalizes closet sensor labels such as Room Closet 1 to Closet Door without changing entity IDs or automations.

## 0.5.106

- Consolidates room-name editing into one full-width Room Names glass card with a blue left highlight, original names on the left and editable display names on the right.
- Preserves Enter/blur autosave and removes unnecessary individual room-detail requests from Home Configurator.

## 0.5.105

- Centers all page progress bars at half the content width, with a smaller-phone cap to avoid overlapping the floating controls.

## 0.5.104

- Combines the Whole Home heading and House Mode title into Whole Home Modes.
- Adds independent Sleep bedroom selections for each registered floor, restricted to current bedrooms on that floor with Sleep enabled.
- Generates a Sleep Mode binary sensor for each configured floor; it is active when any selected bedroom is in Sleep. Whole Home Sleep remains separate.
- Removes the transient Pantry loading-door badge.

## 0.5.103

- Removes Pantry door-status and assigned-action badges from Home Configurator without changing door automations.

## 0.5.102

- Whole Home Sleep choices now use current bedroom areas with Sleep enabled, excluding bathroom and retired room settings.
- Validates saved Sleep selections against the same current bedroom list without deleting existing room settings.

## 0.5.101

- Removes Wake Up Routine from Home Configurator without deleting saved routines or changing existing automations.

## 0.5.100

- Adds an auto-saving exhaust fan timer to switch channels with exhaust fan loads: Off or 1–120 minutes in one-minute increments.
- Turning the load off cancels the countdown; turning it back on starts a fresh countdown. Home Assistant restart starts a fresh countdown for a fan still on. Automation reload cancels active countdowns until the next on transition.
- Existing switch actions remain unchanged.

## 0.5.99

- Removes Home Configurator loading text and shows the white progress bar during initial room discovery.
- Makes floor and area containers transparent, with centered compact titles and consistent spacing across Home Configurator, Doors and Presence.
- Keeps device and House Mode glass cards intact.

## 0.5.98

- Home Configurator shows all floors and rooms on one continuous page, without floor navigation or collapsed room cards.
- Matches the glass cards, blue highlights, compact spacing, floating controls and white progress bar of the other settings pages.
- Loads room details with at most three concurrent requests and reuses cached room data.

## 0.5.97

- Removes the duplicate logo inside mobile navigation while retaining the header menu toggle.
- Extends the menu's dimmed backdrop over the header for consistent transparency while open.

## 0.5.96

- Orders Settings as Home Configurator, Doors, Switches, Presence, then the remaining pages alphabetically.

## 0.5.95

- Removes Dashboards, Action Timeline, and Device Health from Settings navigation.
- Safe Cleanup follows valid in-configuration includes missed by the initial scan, retaining external-path and size protections.

## 0.5.94

- Places Switches, Doors, and Presence first in Settings, preserving the remaining pages' order.

## 0.5.93

- Lists combined presence groups before individual sensors within each room, keeping names alphabetized within each set.

## 0.5.92

- Softens the mobile navigation edge with translucent glass, a subtle fade and shadow, while retaining the transparent header.
- Hides Presence activation and clear delays when no action is assigned, preserving their values when actions are restored.

## 0.5.91

- Removes the visible Presence title bar and matches Switches spacing, keeping the floating exit/update icons and white loading progress.

## 0.5.90

- Adds an always-available update arrow beside Exit, opening Home Assistant updates without starting an installation.

## 0.5.89

- Orders Presence rooms like Doors: bedrooms, bathrooms, then common areas, alphabetically within each category.

## 0.5.88

- Uses the browser top layer for every shared action dropdown, including Presence and Doors, preventing glass cards and navigation from covering menus.
- Preserves toggle-to-close, outside dismissal, viewport positioning, and dialog fallback.

## 0.5.87

- Orders Doors rooms by bedrooms, bathrooms, then common areas, alphabetically within each category using display names.

## 0.5.86

- Completes Doors styling with Switches-style glass cards and blue left highlights.
- Uses one white header progress bar instead of repeated loading messages, including mobile safe-area positioning.

## 0.5.85

- Doors loads room cards automatically with centered area titles and responsive columns, without collapsing cards.
- Matches the Switches transparent header and floating exit button, without Refresh.

## 0.5.84

- Removes Doors-page status displays and background status refresh requests; door automation triggers are unchanged.
- Limits door action choices to the current room's light groups, excluding other rooms, individual lights, modes, switches, fans, and plugs. Existing assignments are retained.

## 0.5.83

- Hides Presence mode settings when no action is selected and shows them when an action is added, preserving configured mode values.

## 0.5.82

- Adds enabled room modes beneath Day/Night/Sleep in Presence settings, with independent activation and brightness settings.
- Applies configured room-mode overrides when that room mode is active; otherwise uses the house mode. New room-mode rules default disabled.

## 0.5.81

- Removes the repeated room prefix and Occupancy (2)-style suffix from Presence card titles.
- Hides entity ID subtitles in Presence action summaries, matching Switches.

## 0.5.80

- Simplifies Presence titles by removing trailing Occupancy labels and suffixes.
- Removes Presence status rows and their background status requests.
- Reuses the Switches action menu for Presence with fans and plugs, without room modes or wake overrides; retains existing presence target IDs.

## 0.5.79

- Centers Presence in the sticky header and removes its repeated page title.
- Adds the white Switches-style loading progress bar for Presence instead of per-room loading messages.

## 0.5.78

- Makes the mobile header fully transparent without blur, borders, or shadows while retaining safe-area spacing and navigation controls.
- Removes Dashboard placeholder text, leaving the existing background unobstructed.

## 0.5.77

- Restores Settings → Presence with centered room headings and open, responsive glass-style sensor cards matching Switches.
- Moves existing presence editors out of Home Configurator without changing saved actions, delays, or Day/Night/Sleep settings.

## 0.5.76

- Matches stale room-relative fixture names such as Shower Lights to their single Shower Light in the same area, preserving saved aliases without merging other bathrooms.

## 0.5.75

- Consolidates single-member light groups and room-relative stale All Lights/ Lights aliases into the actual light choice, preserving saved action aliases.

## 0.5.74

- Shortens Master Bedroom switch titles and selected local action labels by removing the redundant room prefix. Saved assignments remain unchanged.

## 0.5.73

- Positions mobile navigation, exit, progress, and content below the device safe area to avoid iPhone status-bar and Dynamic Island overlap.
- Preserves desktop spacing and the transparent Switches header.

## 0.5.72

- Removes verified unavailable Kitchen 1G, Switch 1G Load Control, and Switch 1G RGB Indicator groups from action choices.
- Excludes switch RGB indicators from lighting choices and generated room light groups, while retaining real under-cabinet loads and RGB fixtures.
- Existing saved actions and Home Assistant registry entries are not deleted.

## 0.5.71

- Collapses stale Entry All Lights and Entry Lights choices into the matching Entry Light. Preserves saved aliases and leaves active groups unchanged.

## 0.5.70

- Replaces redundant single-light helper choices with their actual light while preserving saved action aliases.
- Removes the FHT prefix from light display labels. Does not delete live helpers or change their dependencies.

## 0.5.69

- Uses the room display name in wired-load labels and selected summaries, including Bathroom 1 renamed to Master Bathroom. Physical load links are unchanged.

## 0.5.68

- Removes individual-light choices from bedroom Switches dropdowns. Keeps light groups, modes, fans, plugs, wired loads, and existing assignments.

## 0.5.67

- Excludes retired All Bathroom Lights entities from action catalogs even when Home Assistant still reports them. Associates legacy selections with the current All Lights choice.

## 0.5.66

- Adds a three-second physical off/on brightness override for non-Inovelli switches with wired or assigned dimmable lights. Non-dimmable lights receive no new brightness commands.
- Presence activation and house-mode changes respect the override until the light turns off, including normal vacancy shutoff. Overrides reset after Home Assistant restarts.
- Rejects off/on changes attributed to automation parents or UI users. Physical-device context behavior requires installation testing.

## 0.5.65

- Removes room-mode choices from common-area Switches dropdowns. Bedroom and bathroom options and saved assignments remain unchanged.

## 0.5.64

- Excludes generic Switch/Button channels from switch action targets even when classified as outlets. Keeps named plugs, fans, and saved assignments.

## 0.5.63

- Keeps a white loading animation until the first area finishes, then uses an explicitly white progress fill instead of browser-native styling.

## 0.5.62

- Makes the Switches loading progress bar white for improved contrast.

## 0.5.61

- Standardizes selected local All Lights summaries as All [Room] Lights while keeping compact names inside room dropdowns. Assignments remain unchanged.

## 0.5.60

- Makes Update Available open Home Assistant Updates directly. The exit icon still opens Settings.

## 0.5.59

- Replaces repeated Switches loading messages with a single floating progress bar between navigation and exit. Tracks area completion and hides when finished; errors remain visible.

## 0.5.58

- Removes individual light choices from bathroom Switches dropdowns and shortens local labels without redundant room suffixes. Keeps groups, local devices, and existing assignments.

## 0.5.57

- Retires the special All Bathroom Lights group and toilet exclusion. Bathrooms retain All Lights and fixture groups.
- Backs up and migrates app references from managed All Bathroom Lights helpers to verified All Lights counterparts during startup.

## 0.5.56

- Limits bathroom Switches choices to local groups, individual lights, modes, fans, and plugs. Places local fans and plugs under the bathroom heading and preserves saved assignments.

## 0.5.55

- Places bedroom fans and plugs below lights and modes under the bedroom heading. Combines linked fan/source-switch choices while preserving existing assignments.

## 0.5.54

- Removes individual lights and bedroom room modes from non-bedroom Switches dropdowns. Keeps bedroom choices, wired loads, and saved assignments unchanged.

## 0.5.53

- Keeps linked wired loads visible and locked checked even when the action catalog filters or deduplicates their light entry. Additional actions remain independently selectable.

## 0.5.52

- Tightens Switches page spacing above room titles and between areas and device cards without changing controls or actions.

## 0.5.51

- Resolves Home Assistant Switch as X light/fan links, including hidden source switches and registry UUID references.
- Displays the wired load by default in switch action pickers. Additional actions and Clear Actions do not control or remove the physical load.
- Keeps the picker anchored during scrolling, preventing a focus-induced close/reopen after editing actions.

## 0.5.50

- Hides other bedrooms' light groups from non-bedroom action dropdowns while retaining local groups and all other action categories. Existing assignments are preserved.

## 0.5.49

- Removes the redundant No action / clear all choice from action menus. Keeps the Clear Actions button and empty-selection behavior.

## 0.5.48

- Switches action pickers show Fans & Plugs instead of other switch channels. Retains fan entities and outlets identified by device class or plug/outlet/socket names; saved assignments remain unchanged.

## 0.5.47

- Restricts bedroom action choices to that room's light groups, individual lights, switches, fans, plugs, modes and wake overrides. Common-area choices remain unchanged; existing saved assignments are retained.

## 0.5.46

- Places enabled modes for the current room beside its light choices instead of below other rooms.
- Fixes Switches dropdown toggling closed without immediately reopening.

## 0.5.45

- Removes the faint border around Switches button rows, preserving dropdown and device-card borders.
- Removes the Switches header bar in favor of a transparent floating Exit icon; keeps the narrow-screen navigation logo accessible.

## 0.5.44

- Uses a logo-toggle slide-out navigation drawer on narrow screens. Selecting a page, tapping the logo or backdrop, or pressing Escape closes it. Desktop navigation stays visible.

## 0.5.43

- Hides alarm, exterior-door and battery header indicators; Exit opens Home Assistant Settings.
- Loads Switches from one complete room snapshot instead of separate requests for every room.
- Uses room names for local action headings and includes modes enabled in Room Modes administration.

## 0.5.42

- Keeps full bedroom display names in switch titles. Device IDs and assignments remain unchanged.

## 0.5.41

- Shows the actual light instead of a redundant All Lights action choice when that group contains a single light. Stops generating single-light area helpers and migrates verified saved references to the actual light before regeneration.

## 0.5.40

- Removes the Switches sticky-header Refresh button while preserving automatic updates.
- Reduces vertical spacing around Switches room titles while retaining centered, transparent headings.

## 0.5.39

- Switches action menus open in the browser top layer, above glass cards and the sidebar, with a native dialog fallback for older browsers.
- Anchors menus to the selector width, clamps them to the visible viewport and closes them on outside scrolling or navigation. Existing actions and styling remain intact.

## 0.5.38

- Compacts Switches channels into a single row with the button label and action selector, removing the per-button status/toggle control from this page.
- Hides technical entity IDs beneath selected Switches action names. Existing assignments, automation behavior, other pages and glass styling remain unchanged.

## 0.5.37

- Removes the background and border from centered Switches area headings.
- Gives Switches device cards a consistent translucent glass background, including Inovelli controllers. Layout, actions and other pages remain unchanged.

## 0.5.36

- Switches opens every area's devices without collapsible room cards, with centered area headings and two device columns on desktop, one on smaller screens.
- Loads room editors with at most three concurrent initial requests and keeps switch states updating without replacing action editors. Existing device discovery, assignments, Door Actions and automations remain unchanged.
- Approved stable 0.5.23 remains preserved.

## 0.5.35

- Adds administrator-only Device Health with shared-cache device reports, batteries, firmware progress warnings, unavailable timestamps and bounded observed availability history. No forced updates or device resets.
- Adds Action Timeline with the latest 2,000 observed changes, evidence-based Home Assistant context attribution, search, pagination and read-only trace summaries. Unknown causes remain explicitly unknown; raw trace variables are excluded.
- Adds Safe Cleanup with on-demand duplicate/helper review, configuration dependency checks and reversible archive/recovery. Only reviewed, unavailable restored FHT helpers can be hidden/disabled; no automatic deletion or active-group merging.
- These pages load on demand without adding Home Assistant startup requests. Cleanup requires authenticated administrator identity, CSRF protection, exact selection confirmation and external-reference review. Private recovery journals are written before mutations.
- Keeps approved stable 0.5.23 unchanged. History is bounded in memory and starts fresh after an app restart; recovery journals persist in add-on data.

## 0.5.34

- Names generated fixture groups with one member in the singular (Shower Light); multiple members retain Lights. Area All Lights labels remain unchanged.
- Preserves group entity IDs, unique IDs, and action assignments. Tests cover a shower changing from one bulb to two. Stable rollback remains 0.5.23.

## 0.5.33

- Includes event-only Inovelli switch controllers in the Switches room list and editor, even without relay switch entities. Device names must still contain Switch; fan and camera controls remain excluded.
- Adds desktop/mobile coverage for Kitchen with event channels only. Existing assignments and the approved 0.5.23 stable rollback are unchanged.

## 0.5.32

- Consolidates area-less legacy room Lights helpers into the matching All Lights menu choice, including Dining Room and renamed rooms. Distinct fixture groups remain available.
- Preserves old selections without rewriting automations or deleting helpers. Adds desktop/mobile coverage for the Dining Room case. 0.5.23 remains the approved stable rollback.

## 0.5.31

- Removes duplicate legacy All Lights and Fan Lights choices when their matching FHT helpers have room metadata but the legacy helpers do not. Renamed rooms retain compact local labels and independent rooms remain separate.
- Keeps existing legacy target IDs selected under the single visible group choice, including when another action is edited. Clear removes all represented selections; new assignments use the canonical FHT choice. No live helpers, integrations, or saved automations are deleted or migrated.
- Adds the reported Bailey's room fixture and desktop/mobile selection regressions. 0.5.23 remains the approved stable rollback.

## 0.5.30

- Fixes empty Switches and Doors editors for renamed rooms. Room requests use the original Home Assistant area name while the cards retain the homeowner's display name.
- Preserves existing entity IDs, assignments, switch discovery filters, and automation behavior. Adds regressions against real alias projection and renamed-room browser fixtures. 0.5.23 remains the approved stable rollback.

## 0.5.29

- Moves Door Actions from Home Configurator to Settings → Doors and Switches to Settings → Switches, grouped alphabetically by room with their titles in the sticky header.
- Loads only the selected room's action editor from the shared inventory cache. Live status changes update indicators without rebuilding editors or collapsing rooms.
- Preserves switch-device filtering, hidden switch channels, Inovelli events, existing action assignments, and Pantry Day/Night/Sleep brightness and color settings. No automation or integration changes; 0.5.23 remains the approved stable rollback.

## 0.5.28

- Alphabetizes Settings navigation, with Buttons directly after Alarm, and moves the Buttons title and existing refresh control into the sticky header.
- Combines Amazon Alexa, Apple HomeKit, and Google Nest under Voice Control. HomeKit retains its existing bridge configuration, lazy loading, saving, and refresh; Alexa and Nest remain coming-soon sections. No voice integration behavior or automation changes.
- Keeps 0.5.23 as the approved stable rollback.

## 0.5.27

- Moves Buttons from Home Configurator to Settings → Buttons, grouped by room. Action editors load when their room expands, using the existing button discovery and action-saving paths.
- Preserves device-trigger and event-trigger assignments. Stable rollback remains 0.5.23.

## 0.5.26

- Moves Home Configurator navigation into the main header with a floor dropdown, defaulting to Whole Home when available and preserving the selected floor on refresh. Rooms retain on-demand loading.
- Removes the outer Door Sensors and Device Sensors cards from Alarm, retaining each alarm-mode and device-sensor section. Stable rollback remains 0.5.23.

## 0.5.25

- Aligns Device Sensors title, audible output, and UniFi Webhook checkboxes with consistent sizing and spacing. Long sensor names cannot squeeze their checkbox. No alarm settings or execution changes; 0.5.23 remains stable.

## 0.5.24

- Adds Settings → Users with People, Reservations, Access Groups, Wall Panels, and Activity. Loads the Users module only on demand, without adding startup inventory requests or background refreshes that close editors.
- Adds private, transactional user profiles, bedroom assignments, capability presets, recurring access hours, and version-checked edits. Disabled profiles remain editable. Deleting a profile revokes its PINs without changing native Home Assistant accounts.
- Adds generated or manual PINs, one-time reveal, hashed verification, replacement, revocation, deletion, persistent attempt limits, and administrator-only simulated access checks. Guest credentials require confirmed stays and obey exact arrival/checkout boundaries.
- Adds reservation overlap checks and explicit extension requests/approval. Cancelled stays revoke their own credentials; extensions cannot revive expired or revoked PINs.
- Requires verified Home Assistant administrator identity and CSRF protection for all new Users APIs, with no secret-bearing response caching. No guest API, lock programming, wall-panel enrollment, or alarm command execution is exposed by this release. Panel profiles and door access groups are preparation only.
- Promotes homeowner-approved 0.5.23 to verified stable rollback and removes the superseded 0.5.3 app archives. Private Home Assistant settings backups remain untouched. 0.5.24 remains a candidate until explicitly approved.

## 0.5.23

- Allows editing and saving device alarm thresholds, delays, outputs and webhook selections while the alarm is disabled. The enable checkbox alone controls activation; controls lock only during a save. Stable rollback remains 0.5.3.

## 0.5.22

- Limits device alarm output choices to buzzer and siren actions, with concise device names instead of Play Buzzer/Play Siren suffixes.
- Resolves saved Play Chime targets to the matching Play Buzzer entity when present, both in settings display and generated alerts. Preserves unmatched saved targets for removal. Stable rollback remains 0.5.3.

## 0.5.21

- Moves Alarm title and navigation into the primary sticky header alongside status controls, removing the second header row and Alarm Refresh button. Existing live updates are unchanged. Stable rollback remains 0.5.3.

## 0.5.20

- Moves Alarm title, section tabs and refresh into the fixed top header, using the Scenes header sizing on desktop and mobile. Preserves sensor controls and stable rollback 0.5.3.

## 0.5.19

- Centers the Refrigerator Door Sensors and Refrigerator Environmental Sensors section titles. No control or behavior changes; stable rollback remains 0.5.3.

## 0.5.18

- Makes device sensor audible alerts always continue until cleared and removes the repeat-behavior selector. Regenerates existing device alarm rules at startup.
- Adds a per-sensor UniFi Webhook checkbox and a separate device_alarm_webhook add-on configuration URL defaulting to the usual UniFi endpoint ending in /webhook/DeviceAlarm. Sends one webhook when the delayed alert starts, avoiding repeated UniFi notifications; sirens and chimes continue until cleared. Startup reloads the managed REST command alongside generated automations. The matching DeviceAlarm rule must exist in UniFi Alarm Manager.
- Preserves stable rollback 0.5.3.

## 0.5.17

- Adds Scenes-style Door Sensors and Device Sensors navigation beside the Alarm title, replacing expandable headings. Shows one panel at a time and preserves device controls when switching tabs. Stable rollback remains 0.5.3.

## 0.5.16

- Makes Door Sensors and Device Sensors mutually exclusive expanding cards, with Door Sensors open initially.
- Replaces device alarm output popups with visible two-column siren/chime checkboxes (single column on phones), and places enable beside the sensor name. Existing delays, thresholds, output selections and repeat behavior are preserved. Stable rollback remains 0.5.3.

## 0.5.15

- Restores the Door Sensors container's glass background while retaining fully transparent sensor rows inside each armed-mode card. No behavior changes; stable rollback remains 0.5.3.

## 0.5.14

- Makes Alarm door sensor rows completely transparent, including checked rows, showing only the parent alarm-mode card background. Preserves checkboxes, status bubbles and behavior. Stable rollback remains 0.5.3.

## 0.5.13

- Removes the Select door sensors footer and its extra spacing from alarm mode cards, retaining the empty-state message when no sensors exist. Alarm behavior is unchanged; stable rollback remains 0.5.3.

## 0.5.12

- Removes the extra background tint and blur from the Alarm page Door Sensors container for a seamless backdrop around the arm-mode cards. Collapsing, selections, and alarm behavior are unchanged.
- Stable rollback remains 0.5.3.

## 0.5.11

- Moves Device Alarms out of Home Configurator into a collapsible Device Sensors card on the Alarm page. Existing refrigerator alert settings, outputs and automation behavior are preserved.
- Makes Door Sensors collapsible while retaining the responsive mode checklists. Device Sensors loads on expansion using the shared inventory and existing settings store.
- Keeps 0.5.3 as the homeowner-approved stable rollback.

## 0.5.10

- Stacks Alarm mode cards in a single column. Door checklists use two columns on wider screens and one column on portrait phones.
- Places identical 84 × 26 pixel Open/Closed/Unavailable bubbles between each checkbox and sensor name, keeping the status column aligned.
- Presentation only: selections, live updates, and alarm behavior are unchanged. Stable rollback remains 0.5.3.

## 0.5.9

- Moves Alarm to the first Settings menu position. Adds a top-level Door Sensors card containing Armed Away, Armed Stay Kids, Armed Stay Adult, and Disarmed sensor checklists.
- Saves each profile's sensor selections independently in private alarm_door_settings.json, without overwriting existing room assignments or triggering alarm actions. Existing webhook, siren, and chime behavior remains unchanged; these selections are configuration and live status only.
- Uses actual door contacts from the shared security snapshot, excluding battery, tamper, moisture, and camera detections. Retains missing selected contacts for removal, and marks stale or disconnected readings unavailable.
- Updates sensor status from existing live events without rebuilding checkboxes or adding polling. Keeps 0.5.3 as the homeowner-approved stable rollback.

## 0.5.8

- Gives Lighting natural-height, tightly packed responsive room cards instead of stretching every room to the tallest neighbor. Layout updates are local and batched, including when opening brightness controls or resizing; no additional API polling.
- Orders Lighting areas as common areas, closets, outside, bedrooms, then bathrooms, alphabetically within each category with numeric sorting. Recognizes the existing Bedoom spelling without renaming rooms.
- Removes the Room Modes saved/enabled footer and routine Save button. Checkbox changes still save automatically, with accessible progress and an error-only Retry control that preserves the unsaved selections.
- Keeps existing light controls, alarm assignments, and stable rollback 0.5.3 unchanged.

## 0.5.7

- Moves Armed Away, Armed Stay Kids, Armed Stay Adult, and Disarmed selections out of Room Modes into Settings → Alarm, with four dark-glass, blue-accent cards and automatically saved room assignments.
- Keeps existing selections, helpers, scene configurations, and alarm automations. Page-scoped saves preserve the other page's settings under the settings lock; configuration does not arm/disarm the house.
- Keeps 0.5.3 as the homeowner-approved stable rollback.

## 0.5.6

- Matches Settings → Room Modes cards to House Mode's dark glass background, blue border and left accent, with subtle blue selected options and white labels. No mode behavior or automation changes.
- Keeps 0.5.3 as the homeowner-approved stable rollback.

## 0.5.5

- Removes presence, door/window, temperature, humidity, and lux rows from Lighting room headers. Lighting transfers only light groups and no longer refreshes on sensor-only events; Security and the Exterior toolbar remain live.
- Moves room-mode checklists from Home Configurator into Settings → Room Modes, with automatic saving and the existing bedroom-specific choices. Existing settings and specialized bedroom automations remain intact.
- Adds Scenes → Room Scenes. Every enabled room/mode gets its own configuration card, with light/group selection, 0–100% brightness, and color/tone controls. Saved scenes run when their room enters that mode, not while configuring it.
- Disabling a mode removes its scene automation while retaining the scene settings for reuse. Room-mode helpers stay available to existing controls, even when no modes are selected.
- Uses the compact room index and shared action catalog for the new screens. Saving modes invalidates dependent scene/editor caches without adding startup-blocking inventory requests.
- Keeps 0.5.3 as the homeowner-approved stable rollback. This is a candidate until explicitly approved.

## 0.5.4

- Keeps 0.5.3 as the homeowner-approved stable rollback release; this update remains a candidate until accepted.
- Maintains the live inventory by entity ID, replacing only the changed record instead of rebuilding and sorting the whole house for every state event.
- Copies only the requested room, battery sensors, security sensors, or compact toolbar/index fields. Projection work no longer holds the live-event lock while copying and translating names.
- Reuses battery metadata from the shared inventory instead of repeatedly opening the full registries. Registry refresh and live state updates continue to update it.
- Keys action catalogs to device metadata and configuration changes rather than ordinary brightness, presence, or battery readings. Catalogs contain target metadata, not stale device states.
- Reconciles each room with the returned catalog revision, preventing repeated catalog downloads when a subsection was opened with an older revision.
- Preserves current settings, migration archives, existing controls, and automation behavior.

## 0.5.3

- Completes deferred reference repairs using the approved current-settings policy: existing canonical settings win over older aliases regardless of file order.
- Archives original private settings and records older conflicting keys in the repair manifest. Ambiguous collisions without a current canonical entry still stop safely.
- Reports resolved conflict counts at startup. Existing completed migrations remain unchanged; no registry entities are deleted.

## 0.5.2

- Shares a revision-keyed action/editor catalog across Home Configurator rooms rather than rebuilding and transferring it in every room response. Revalidates after inventory or saved-setting changes.
- Renders applicable room section headers first; builds each editor only when expanded, retaining its existing DOM and drafts when closed and reopened.
- Warms button discovery independently with single-flight refresh, a short cache lock and failure backoff. Room navigation uses its last cached result; only an opened Buttons section waits for initial discovery.
- Batches registry-change bursts into a delayed metadata refresh instead of refreshing per event. Preserves state events that arrive during a full snapshot so fresh states are not overwritten.
- Keeps room responses scoped to that room's assignments. Late button discovery retrieves its saved ZHA actions as well.
- Preserves the backed-up 0.5.1 reference migration and existing automations. Physical runtime acceptance remains separate from regression tests and mounting.

## 0.5.1

- Repairs the reviewed repeated-area entity references in private saved settings before configuration generation, only when the old ID is absent and its enabled replacement is loaded.
- Consolidates saved light-group targets only when live recursive membership matches an FHT group exactly. Removes duplicate selector targets, not physical devices or unverified registry helpers.
- Preserves original saved settings and managed YAML in a private repair backup with a migration manifest. Conflicting assignments defer the entire repair; interrupted writes are restored before generators run.
- Leaves dashboard references and unverified/missing groups unchanged for separate review. Repairs run on installation/startup, not merely when this source is mounted.
- Retires the 0.4.80 stable hold at the homeowner's request, preserving its recovery archives. 0.5.1 remains pending homeowner stability acceptance.

## 0.4.100

- Keeps Home Assistant alive behind the ingress app instead of redirecting away and booting it again on exit.
- Uses a reversible fullscreen iframe popover when supported, with ordinary embedded rendering as the fallback. Exit returns to Updates through Home Assistant's client-side navigation.
- Removes the intermediate kiosk redirect document while retaining fingerprinted interface assets.
- Removes repeated registry reads and redundant inventory copying from exterior/security status requests.
- Makes unavailable exterior sensors inspectable and prevents stale closed states from producing a green bubble.
- Distinguishes Protect certificate, DNS, timeout, and refused-connection errors without exposing credentials. TLS verification remains enabled.
- Preserves stable rollback 0.4.80; this release does not repair a console's invalid certificate or alter device pairings.

## 0.4.99

- Uses a lightweight kiosk handoff instead of initializing the complete application twice.
- Separates the interface shell from fingerprinted, compressed CSS and JavaScript assets that remain cached across openings and updates safely.
- Staggers background startup requests, combines identical in-flight reads, and loads a compact menu summary instead of a full entity inventory just to count offline thermostats.
- Keeps stale-cache recovery off the navigation request path and removes repeated registry reads from lighting updates.
- Fixes live revision recovery after server restarts and accepts state events during subscription setup.
- Reserves HTTP capacity for navigation, corrects overload response framing, and handles cancelled browser requests quietly.
- Fixes forced Home Configurator refresh, refreshes staying attached to their original page, missing-temperature display, and refresh rejection handling.
- Disables the enhanced Device Alarm output picker during saves so edits are not silently discarded.
- Adds real navigation and slow-request timings, behavioral regression coverage, and an audit with 15 next-step recommendations. Stable rollback remains 0.4.80.

## 0.4.95

- Removes the nested Refrigerators card and places refrigerator door and environmental sensor cards directly inside Whole Home Device Alarms.
- Shows each sensor's current state beside its friendly name and simplifies alert timing into a compact second row.
- Adds persistent siren and chime output selection with One Time or Indefinitely Until Clear behavior.

## 0.4.94

- Renames the legacy Whole Home Bridges room to Device Alarms in Home Configurator.
- Renders Device Alarms with the same centered blue-accent card design as House Mode.
- Treats Bridges, Fridges, and Device Alarms as compatible names for the refrigerator alarm settings card.

## 0.4.93

- Reshapes Pantry Door Actions into compact two-row Day, Night, and Sleep cards with the enable checkbox, mode name, and action selector aligned on one row.
- Reuses the native-style color dialog for Pantry mode RGB, tone, and Adaptive choices from a compact color button beside brightness.
- Joins every expanded Home Configurator section header and body into one polished card.

## 0.4.92

- Removes Home Configurator room counts and hides the Unassigned floor unless it contains a room.
- Restores the fixed Whole Home Device Alarms card and keeps the Sleep bedroom picker above surrounding cards with friendly labels only.
- Expands Room Modes into one persistent checklist of available modes while preserving the existing detailed bedroom automation panels.

## 0.4.91

- Expands Pantry Door Actions into enabled Day, Night, and Sleep mode cards with independent action selections and 0–100 percent brightness.
- Adds Current Color, Adaptive, Color Temperature, and RGB color behavior to each Pantry door mode and persists those settings in generated Home Assistant automations.
- Adds a Whole Home Sleep source selector so only chosen bedroom Sleep modes activate the global House Sleep mode.

## 0.4.90

- Adds separate Day Mode and Night Mode action pickers to Pantry Door Actions and conditions the generated automations on the active house mode.
- Migrates existing Pantry door actions to both modes so current behavior remains intact until each picker is changed.
- Removes duplicate light-group choices by comparing their final room-relative names and preferring the canonical Future Homes Tech group.

## 0.4.89

- Replaces Pantry's generic Door Actions selector with a concise Pantry Light Groups section and a separate Advanced section.
- Removes the repeated green door bubble and hides internal action IDs from the Pantry selector summary.
- Excludes obsolete Pantry All Lights and Lights aliases from the focused Pantry action menu.

## 0.4.88

- Collapses generated fixture groups whose membership exactly matches their area's canonical All Lights group.
- Hides legacy generic All Lights and Lights helpers from action menus when the canonical FHT area group exists.
- Elevates the entire active Home Configurator floor so expanded action menus remain above later floor cards.

## 0.4.87

- Removes irrelevant Room Modes, Wake-up Routine, and Not Set status from Pantry while surfacing its live door state and assigned-action count beside the room title.
- Fixes Home Configurator action menus so they render above neighboring room and floor cards instead of being obscured.
- Removes raw entity-ID fallback text from duplicated action names while retaining clean room and device context where available.

## 0.4.86

- Replaces the Whole Home Fridges room editor with a fixed Device Alarms card and an expandable blue Refrigerators panel.
- Groups refrigerator temperature and door sensors by device with auto-saving threshold and open-duration alert controls.
- Generates persistent Home Assistant refrigerator alert automations and clears each notification automatically when the sensor recovers.

## 0.4.85

- Increases centered Home Configurator floor-name text by approximately 25 percent while keeping room counts aligned at the edge.
- Restyles Fridges as a centered blue-accent Whole Home card that remains open and loads only when Whole Home is displayed.

## 0.4.84

- Centers Whole Home and floor headings while keeping room counts aligned at the edge, and centers the House Mode title.
- Limits the Day and Night solar selectors to clear 15-minute steps from 90 minutes before through 90 minutes after sunrise or sunset.
- Rebuilds action menus as wider, scannable rows with the selected room's light groups first and all remaining groups alphabetized separately.

## 0.4.83

- Keeps Whole Home first in Home Configurator and replaces its House Mode popup with compact inline Day and Night solar-time selectors that save immediately.
- Groups physical button events into one blue-accent card per button with Single Press, Double Press, Long Press, and Long Release action rows.
- Moves Clear Actions into the open action menu so action summaries stay aligned and readable.

## 0.4.82

- Replaces Whole Home's raw signed-minute inputs with a compact blue-accent Day/Night dial picker anchored to sunrise and sunset; readable before/at/after values are shown and saving closes the picker.
- Adds progressive Room Modes selection in Home Configurator: available modes appear as a compact checklist and detailed settings open only for checked modes.
- Fixes the macOS release-gate temporary-module check so the candidate gate runs consistently on macOS.

## 0.4.81

- Replaces repeated full-entity polling with one shared Home Assistant state cache, live WebSocket revisions, projected page payloads, and lazy per-room Home Configurator loading.
- Preserves open room editors and unsaved drafts during background updates while rendering the application shell immediately and warming independent data concurrently.
- Unifies switch, button, presence, wake, and door actions under stable multi-action targets with duplicate-name context, atomic saves, and persistent door automation generation.
- Corrects Whole Home solar-boundary evaluation, entry-delay cancellation and rechecks, stale safety-state handling, and reload coordination.
- Enables verified Protect TLS by default and hardens the embedded HTTP service with bounded requests, timeouts, compression, revalidation, CSP nonces, and security headers.
- Removes retired screens, endpoints, startup paths, frontend helpers, and superseded runtime artwork; adds an auditable candidate release gate while preserving `0.4.80` as stable.

## 0.4.80

- Adds Whole Home sunrise and sunset offsets from -120 to +120 minutes, persistent settings, and offset-aware house mode automation and display.

## 0.4.79

- Runs independent startup preload phases concurrently and logs phase and total preload timing.

## 0.4.78

- Replaces Door Actions light-group selectors with the shared multi-action selector and persists door action assignments.

## 0.4.77

- Adds cached Home Configurator navigation, preserved room expansion, visible switch action summaries, clear controls, and concise button labels.

## 0.4.76

- Classify unnumbered light targets with Light Groups and keep numbered lights in the individual Lights section.

## 0.4.75

- Place Light Groups first and individual Lights last in action selectors.

## 0.4.74

- Prefer an FHT light group when a physical light shares its friendly name, preventing duplicate action targets.

## 0.4.73

- Separates physical lights from FHT light groups in action menus and removes duplicate displayed targets.

## 0.4.72

- Limits Home Configurator Switches to devices whose registered device name contains `Switch`.

## 0.4.71

- Restricts Home Configurator Switches to switch-named entities and their related event channels.

## 0.4.70

- Limits the Switches page to switch entities whose device or entity name includes `switch`.

## 0.4.69

- Deduplicates identical light-group names in Button action selections.

## 0.4.68

- Organizes every door-time input-text helper under the native `Future Homes Tech Door Timers` Helpers category.

## 0.4.67

- Allows one Controls, Buttons, Inovelli, or Presence action dropdown to select and persist multiple targets.
- Builds one shared Home Assistant entity inventory at startup and reuses it across the App.
- Opens Home Configurator rooms from cached data immediately, then refreshes only the selected room.

## 0.4.66

- Keeps the Lighting dashboard Lux bubble on one content-sized line.
- Removes the Automations, Blueprints, and Entities entries from the Settings menu.
- Opens Home Configurator with Floor cards only, then reveals Room cards for the selected Floor and hydrates only the selected Room.
- Restores renamed Inovelli Up, Down, and Config event channels by matching them to their physical switch device and labels them Button 1, Button 2, and Button 3.

## 0.4.65

- Limits Presence and PIR individual-light actions to physical light entities whose friendly name, original name, or entity ID ends in a number.
- Keeps every Future Homes Tech light helper, including room Lights and All Lights helpers, exclusively under FHT Light Groups.

## 0.4.64

- Organizes Home Configurator into real Home Assistant Floor cards containing Room cards.
- Keeps room content cached but only renders the room currently expanded for faster switching.
- Preloads every App page at startup while prioritizing a page immediately when it is selected.
- Limits Controls to actual `switch` entities and excludes camera and doorbell controls.

## 0.4.63

- Discovers every channel belonging to a wall-switch device, including channels Home Assistant exposes as a light or fan.
- Uses Home Assistant's original channel metadata to label device channels as Button 1, Button 2, and Button 3.
- Removes the Physical Load checkbox and gives every discovered channel a direct Action selection.
- Adds individual lights alongside FHT light groups in Controls action selections.

## 0.4.62

- Includes every Home Assistant switch entity in its assigned Area on Controls and Home Configurator.
- Makes each Home Configurator Buttons section use the same collapsible card treatment as Controls.

## 0.4.61

- Makes each Home Configurator Presence section use the same collapsible card treatment as Controls.
- Adds individual lights, FHT light groups, and named actual loads to Presence action selections.

## 0.4.60

- Packages the restored `0.4.56` application baseline as a newer installable release.
- Removes the `0.4.57` Door Actions expansion and the `0.4.58` Smart Device Settings evaluation flow.

## 0.4.56

- Shortens Home Configurator Door Actions to location-only labels such as Closet Door and Bedroom Door.
- Shows each door name in a live gray unavailable, green closed, or red open status bubble.

## 0.4.55

- Replaces Wake Up Routine native time inputs with the app's safe hour, minute, and AM/PM dialog.
- Prevents the Home Assistant macOS app from crashing when a weekday or override wake time is opened.

## 0.4.54

- Adds a compact Door Actions section for room door-to-light-group assignments.
- Reduces spacing between Home Configurator expandable sections.

## 0.4.53

- Makes room display-name editing compact and saves automatically on Enter or leaving the field.
- Aligns Room Modes and Wake Up Routine with the compact Controls dropdown sections.
- Tightens spacing between Home Configurator sections.

## 0.4.52

- Removes the redundant Home Configurator display-preview text.
- Makes Wake Up Routine use the same compact expandable section treatment as Controls and Bedroom Modes.

## 0.4.51

- Makes the Home Configurator sticky toolbar match the main glass toolbar transparency.
- Groups multi-channel switch controls into one translated device card with compact button rows.
- Makes Controls and Room Modes compact, highlighted, collapsible sections inside each room.
- Removes the embedded Bedroom Modes current-mode dropdown while preserving mode checkboxes and saves.

## 0.4.50

- Rebuilds Home Configurator as a single-column, display-name-sorted workspace with its title, house mode, security mode, room count, and refresh control in one sticky secondary toolbar.
- Shows only a room's real active mode and reports `Not Set` when no room mode helper currently has an active value.
- Makes wake schedules progressive: enable days individually with native time pickers, expand only the selected functionality, and add working Lights, Light Groups, Room Mode, and Audio / Music actions.

## 0.4.49

- Moves Presence, Controls, and Buttons cards into their matching Home Configurator rooms.
- Preserves all existing assignments, toggles, delays, room modes, and actual-load controls in the consolidated cards.
- Removes the redundant Presence, Controls, and Buttons entries from the Settings submenu.

## 0.4.48

- Renames Room Configurator to Home Configurator.
- Adds separate Day/Night house mode and Armed/Disarmed security summaries.
- Shows the current operating mode on every room card.

## 0.4.47

- Adds per-room seven-day wake routines in Room Configurator.
- Adds separate Lights and FHT Light Groups wake-function blocks with room-specific selections and brightness.
- Adds one-time next-wake override helpers that can be assigned to switches and buttons.
- Hides the Door Sensors section when an area has no door sensors.

## 0.4.46

- Changes Room Configurator to a responsive two-column room layout.
- Excludes the infrastructure-only Adopting, Bridges, and Unifi areas.
- Moves existing room mode controls into their applicable Room Configurator cards and removes the duplicate Scenes menu entry.

## 0.4.45

- Adds standalone Home Assistant switches and plugs to Button action targets.
- Automatically saves a selected switch or plug as a reusable FHT load and generates a persistent toggle automation.

## 0.4.44

- Adds configurable Toddler Mode to every bedroom with door-armed monitoring, RGB light alerts, repeatable chime actions, optional Inovelli LED controls, and automatic timeout.
- Adds Toddler Mode targets to direct switches, Inovelli gestures, and button presses while preserving existing Sleep Mode assignments.

## 0.4.43
- Simplifies Actual Load configuration to one checkbox and automatically uses the switch entity's current Home Assistant friendly name.
- Reconciles enabled actual-load names after Home Assistant entity renames so selectors and generated automation aliases stay current.
- Keeps named switch loads available to direct controls, Inovelli gestures, and button actions without requiring duplicate naming.

## 0.4.42
- Replaces the physical-light Actual Load selector with a checkbox and custom load name for the switch channel itself, such as Exhaust Fan.
- Makes named actual loads available as persistent action targets from direct switches, Inovelli gestures, and button controls.
- Generates switch-domain ON, OFF, and toggle actions for named loads without applying light brightness commands.
- Removes dependent action assignments automatically when a named actual load is disabled.

## 0.4.41
- Adds an Action selector to every managed switch so it can control either an existing FHT light group or its bedroom Sleep Mode.
- Restores the room to its armed, daytime, or nighttime mode when a Sleep Mode switch turns off.
- Adds a separate Actual Load selector that persistently identifies the individual physical light controlled by each switch channel.
- Preserves existing light-group and button-gesture assignments while adding the new switch controls.

## 0.4.40
- Prevents FHT switch synchronization from feeding back into a second 100-percent light command when presence or another automation has already turned the assigned group on.
- Preserves the existing 100-percent behavior for a real switch-on action when its assigned light group is off.

## 0.4.39
- Reconciles Future Homes Tech House Mode immediately when the App starts or bedroom-mode settings are saved, so an App update after sunset cannot leave the house in Day mode.
- Adds a lightweight five-minute House Mode safety check while preserving immediate sunrise, sunset, and bedroom Sleep updates.

## 0.4.38
- Adds an automatic Future Homes Tech House Mode helper: Day after sunrise, Night after sunset, and Sleep whenever any bedroom is set to Sleep.
- Adds per-presence Day, Night, and Sleep enable and brightness controls with defaults of disabled daytime activation, 80 percent at night, and 25 percent during Sleep.
- Updates native presence automations immediately when the house mode changes while presence remains detected.
- Adds a current-mode selector to each bedroom so Sleep mode can drive the house-wide presence override.

## 0.4.37
- Writes grouped presence member metadata as a Home Assistant template string so the generated presence package passes configuration validation.

## 0.4.36
- Groups separately numbered physical presence devices, such as Bathroom 1 Presence 1 and Bathroom 1 Presence 2, into one Bathroom 1 Presence Group sensor.
- Includes every enabled occupancy entity from the numbered device family in the grouped sensor.

## 0.4.35
- Creates one FHT grouped occupancy binary sensor for each physical presence device that exposes numbered occupancy channels.
- Shows grouped presence sensors beside the individual channels on the Presence settings page and supports the same light-group and delay assignments.
- Rebuilds grouped presence helpers when the Presence page is refreshed.

## 0.4.34
- Keeps a consistent Lighting sensor-status row in every room card, including rooms without environmental sensors.
- Loads the battery inventory through a dedicated lightweight endpoint and excludes Mobile App batteries without a registry WebSocket lookup.
- Lists batteries with missing type information first and lets homeowners assign common or discovered battery types from the battery popup.

## 0.4.33
- Rebuilds the battery popup as a professional full inventory sorted lowest-first within grouped battery types.
- Uses Home Assistant's reported battery type when available, with practical device categories as a fallback.

## 0.4.32
- Refines the toolbar battery into the professional Precision Cell design with a slimmer rounded shell, five clean charge bars, and restrained illumination.
- Uses yellow for the two-bar low-battery state while retaining red below 10% and green for levels at or above 20%.

## 0.4.31
- Replaces the toolbar battery percentage with a five-segment battery icon whose outline stays green, with red below 10%, orange below 20%, and graduated green levels above 20%.
- Orders Lighting areas with common areas first, bedrooms second, and bathrooms last.

## 0.4.30
- Removes the redundant Master Brightness control from Lighting room cards.
- Keeps an Exterior toolbar bubble beside arm mode: green when all entry doors are closed, red when any are open, and gray when status is unavailable.

## 0.4.29
- Combines presence, interior openings, temperature, humidity, and lux into one balanced Lighting status row.

## 0.4.28
- Slims each Lighting control row while allowing long light names to expand naturally.

## 0.4.27
- Changes the Lighting presence bubble label from uppercase to title case.

## 0.4.26
- Lists each room's Lighting controls vertically with the light name and brightness percentage on one row.

## 0.4.25
- Adds the current room illuminance in lux to the Lighting environment-status row.

## 0.4.24
- Moves exterior entry-door alerts from Lighting room rows to the global toolbar.
- Shows a red Exterior Door bubble only while entry doors are open, with a clickable open-door list.
- Refreshes cached entry-door states without repeatedly loading the full entity inventory.

## 0.4.23
- Shortens Lighting door/window bubbles to their location or Door/Window fallback.
- Excludes Fridge door sensors from Lighting room status rows.

## 0.4.22
- Labels room presence bubbles and centers live door/window status bubbles on Lighting cards.
- Shows closed openings in green, open openings in red, and unavailable openings in gray.

## 0.4.21
- Shows room presence, temperature, and humidity in compact Lighting status bubbles.
- Uses white, blue, and red light-group edge states for off, on, and offline groups.

## 0.4.20
- Removes the obsolete Settings > Light Groups page and its refresh/offline-count UI.
- Keeps generated FHT light groups and their use by Lighting, Controls, Scenes, and HomeKit unchanged.

## 0.4.19
- Keeps button presses pending for up to five minutes when their assigned FHT light group is temporarily unavailable.
- Executes only the latest pending press after the group recovers, preventing duplicate delayed toggles.

## 0.4.18
- Removes the redundant Bedroom Modes subtitle from bedroom cards.
- Stacks each door sensor name above its light-group selector and keeps the right panel at content height.

## 0.4.17
- Renames the bedroom security settings to Armed Away Interior Door Webhook and Armed Stay Kids Interior Door Webhook.
- Retains existing saved webhook values as a legacy migration fallback.

## 0.4.16
- Stacks Armed Away, Armed Stay Kids, Armed Stay Adult, and Disarmed in the left side of each bedroom Room Modes card.
- Places all bedroom door-sensor lighting assignments in a dedicated right-side column.

## 0.4.15
- Simplifies bedroom Armed Away and Armed Stay Kids controls while automatically monitoring only that bedroom's door sensors.
- Moves bedroom door-sensor light-group assignments from Room Configurator into each bedroom's Room Modes card.
- Defaults Disarmed mode to Day at sunrise and Night 15 minutes before sunset.

## 0.4.14
- Adds functional bedroom Room Modes for Armed Away, Armed Stay Kids, Armed Stay Adult, Day, and Night.
- Adds configurable UniFi webhooks for bedroom Armed Away and Armed Stay Kids door alerts.
- Adds bedroom door monitoring, selected Kids-mode door sensors, randomized Away lighting, and solar Day/Night timing controls.

## 0.4.13
- Adds a Room Modes toolbar action that saves every room's mode selections together.
- Keeps the Save Changes action directly to the left of the Room Modes refresh control.

## 0.4.12
- Adds Disarmed, Armed Stay, and Armed Away as universal options on every Room Modes card.

## 0.4.11
- Darkens the unified top glass header while preserving the existing left sidebar transparency.

## 0.4.10
- Keeps every Scenes submenu title white and uses only the blue underline to indicate the active submenu.

## 0.4.9
- Extends the left sidebar's dark glass surface continuously across the top of the app.
- Combines global actions and the Scenes sub-toolbar into one unified two-row header.
- Preserves compact responsive spacing on tablets and phones.

## 0.4.8
- Adds Room Modes as a second Scenes submenu with persistent room cards.
- Recommends tailored modes for bedrooms, bathrooms, kitchens, dining rooms, living rooms, theaters, and playrooms.
- Keeps mode selections tied to original Home Assistant areas while displaying Room Configurator names.

## 0.4.7
- Simplifies the Light Automation color picker to Adaptive, Tone, Color, and one Apply button.
- Stages color choices until Apply is pressed and makes Adaptive override manual tone and color.
- Removes color presets and uses a solid light-blue Apply button.

## 0.4.6
- Adds a Color control beside brightness and Save on every Light Automation card.
- Supports current color, adaptive circadian color, fixed white tones, custom Kelvin, and custom RGB color.
- Smoothly refreshes adaptive color every 15 minutes while the scheduled light is on.

## 0.4.5
- Hides solar offset minutes when a trigger is set to At sunrise or sunset.
- Uses a native wheel-friendly minute picker from 0 through 240 for Before and After.

## 0.4.4
- Opens Light Automations automatically when the Scenes page is selected.
- Rebuilds every light automation as four compact rows: light/enabled, Turn On, Turn Off, and brightness/save.
- Keeps Scenes out of startup preload while loading its default subpage on demand.

## 0.4.3
- Converts the Scenes toolbar into a transparent subpage navigation row.
- Places Scenes and Light Automations on the left with count and refresh on the right.
- Defers Light Automations inventory and schedule rendering until its subpage is selected.

## 0.4.2
- Replaces signed solar offsets with clear At, Before, and After controls.
- Places Time of Day at the top of each trigger menu and uses the device's native time picker.
- Preserves Sunset as the default ON trigger and Sunrise as the default OFF trigger.

## 0.4.1
- Introduces scene control with independently configurable light automations.
- Moves the Scenes title into a sticky second toolbar row.
- Places the enabled/light count and Scenes refresh control beside Protect arm status.

## 0.3.118
- Renames the Scenes configuration section to Light Automations.
- Groups light automation cards by area and keeps each light independently configurable.
- Compacts the solar/custom-time controls while preserving every schedule setting.

## 0.3.117
- Adds functional Automation Light Cards to Settings > Scenes.
- Configures independent ON and OFF triggers using sunrise, sunset, or custom time.
- Supports signed solar offsets and per-light ON brightness.
- Persists card settings and generates managed Home Assistant automations.

## 0.3.116
- Discovers physical devices with Button in their name while excluding devices containing Switch.
- Adds Matter button event gestures to Buttons with persistent FHT light-group assignments.
- Generates toggle automations for IKEA Matter button presses while preserving native ZHA button triggers.

## 0.3.115
- Adds a Future Homes Tech Security Bridge to Apple HomeKit using the filtered door sensors from Security.
- Keeps the security bridge independently pairable and applies Room Configurator display names.

## 0.3.114
- Removes door-sensor battery, moisture, and tamper diagnostics from Security.

## 0.3.113
- Restricts Security to actual door contact sensors and removes doorbell detection entities.

## 0.3.112
- Adds a live Security dashboard grouped by area and door sensor.
- Highlights open doors in green while closed doors remain neutral.

## 0.3.111
- Restores the global Update Available indicator on dashboard pages.
- Restores the conditional red Refresh control after an app update.

## 0.3.110
- Moves each area Master Brightness control directly beneath the area title.

## 0.3.109
- Converts each Lighting control into a compact name and brightness bar.
- Adds per-light brightness sliders while preserving animated power feedback.

## 0.3.108
- Versioned restored Lighting dashboard build.

## 0.3.106
- Removes global bell and refresh controls.
- Adds animated, page-local refresh controls to Settings pages.

## 0.3.105

- Flatten Lighting area cards so individual light cards sit directly beneath each area title.
- Move the blue accent line onto each light card and keep Master Brightness as the full-width bottom row.
- Keep the ON/OFF toggle and brightness percentage as the only lighting controls.

## 0.3.104

- Remove the Lighting summary bar and its Lights On, Offline, and All Off controls.
- Split each lighting control into a titled card with a large ON/OFF toggle across its lower half.
- Keep brightness, optimistic state changes, and pending command animation inside each compact card.

## 0.3.103

- Replace Lighting's separate names and tiny status controls with compact, fully clickable named control tiles.
- Show immediate optimistic ON/OFF state, brightness, and a visible pending animation while Home Assistant applies each command.
- Tighten area cards, summaries, and responsive layouts to fit substantially more lighting controls on one screen.

## 0.3.102

- Read `weather.forecast_home` through a lightweight single-entity endpoint so toolbar temperature appears before full inventory loading.
- Stage startup as temperature, primary pages, update information, Settings configuration, Protect status, Protect NVR, one shared entity inventory, offline counts, then lowest battery.
- Cache Settings configuration responses during startup and reuse them while entity-backed pages render.

## 0.3.101

- Load one shared full entity inventory at startup and reuse it across every page.
- Calculate the lowest battery only after all page preloads and offline counts finish.
- Refresh the shared inventory only from a manual page refresh instead of recurring entity polling.

## 0.3.100

- Preserve the generated Outside Perimeter Coach Lights subgroup even when it contains every light in the area.
- Complete regression coverage for cached page loading, current refresh intervals, categories, live lighting, and persistent button automations.

## 0.3.99

- Persist ZHA button-action light-group assignments and regenerate their native Home Assistant automations after restarts.
- Show button assignment success and errors directly on the Buttons page.

## 0.3.98

- Refresh Lighting once per second only while its page is visible using a lightweight lighting-only status endpoint.
- Redraw Lighting only when state or brightness changes.

## 0.3.97

- Cache preloaded page data and stop reloading pages on navigation.
- Add manual page refresh and reduce recurring background polling.
- Move Settings offline-count loading to the end of startup.

## 0.3.67

- Show every named button event device on Settings Buttons.

## 0.3.66

- Fix the Buttons page event-label lookup.

## 0.3.65

- Add Settings Buttons with area and device cards for supported event triggers and FHT light-group assignments.

## 0.3.64

- Show offline or unavailable counts beside Settings Entities, Light Groups, Controls, and Climate.

## 0.3.63

- Group Presence entities under their physical Home Assistant device within each area.

## 0.3.62

- Exclude presence-sensor indicator LEDs from generated light groups.
- Add a compatible fallback when renaming the Light Groups helper category.

## 0.3.61

- Group FHT Control automations by area and triggering device.

## 0.3.60

- Group Presence sensor cards inside their matching area cards.

## 0.3.59

- Exclude named door sensors from the Presence page.

## 0.3.58

- Redesign Presence into compact two-column cards with Activation and Clear delays.

## 0.3.57

- Create managed Presence automations: detected turns the selected light group on; clear turns it off.

## 0.3.56

- Retry Light Groups category organization after Home Assistant finishes starting.
- Show the underlying registry error in the App log when retries are exhausted.

## 0.3.55

- Rename the generated helper category to Future Homes Tech, Light Groups.

## 0.3.54

- Store and restore the complete App-managed Climate package if it is removed.
- Retire legacy Climate dashboard and generator registrations while leaving old files untouched.
- Organize App-managed Climate automations in the Future Homes Tech category.

## 0.3.53

- Verify Climate target delivery five minutes after each rate-mode or occupancy change, retry only mismatches, then perform one final five-minute retry.

## 0.3.52

- Use an AM/PM time picker for On-Peak and Super-Off Peak schedules.
- Make all Climate targets adjustable with sliders and split the Holiday schedule into two columns.
- Return Upcoming Rate Changes to a compact half-width card.

## 0.3.51

- Refine the Climate page with centered cards, read-only thermostat summaries, a lowest-temperature slider, and native time/month selectors.
- Load the configured weather entity on the Climate page, including weather.forecast_home.

## 0.3.50

- Organize migrated Climate helpers under Future Homes Tech Climate.
- Rename the native Light Groups Helpers category to Future Homes Tech Light Groups.
- Move the legacy Weather Entity helper into the App-managed Climate package.

## 0.3.49

- Migrate legacy Climate configuration into an App-managed package and add Settings Climate controls.

## 0.3.48

- Assign unique ports to the Light and Climate HomeKit bridges so both can be paired independently.

## 0.3.47

- Recognize paired fixtures named with the direction after Light, such as Coach Light Left/Right.

## 0.3.46

- Correct the Apple HomeKit title and generate shared groups for paired left/right fixtures.

## 0.3.45

- Match the Climate Bridge to the Light Bridge checklist layout and correct both bridge titles.

## 0.3.44

- Fill the HomeKit Light Bridge columns top-to-bottom in alphabetical order.

## 0.3.43

- Change the Update bubble to green and label it Update Available.

## 0.3.42

- Replace the persistent refresh icon with a Refresh bubble that appears only when needed.

## 0.3.41

- Rename the Apple HomeKit page and Light Bridge; tighten light-group checklist labels.

## 0.3.40

- Show a dedicated Update bubble only when a newer add-on release is available.
- Reserve notification alerts for configuration changes and refresh alerts for a loaded App refresh or light-group rebuild.

## 0.3.39

- Simplify the HomeKit Light Bridge into a three-column selectable light-group list.

## 0.3.38

- Split Apple HomeKit into selectable Light Bridge and Climate Bridge cards.

## 0.3.37

- Use Room Configurator display names for selected FHT light groups in the HomeKit bridge.

## 0.3.36

- Add the FHT HomeKit Bridge page for selecting FHT light groups; add Alexa and Google settings placeholders.

## 0.3.35

- Add Settings placeholders for Apple HomeKit, Amazon Alexa, and Google Nest.

## 0.3.34

- Place the Presence Sensor total on the right side of the Presence header.

## 0.3.33

- Show offline/unavailable counts in the Light Groups and Controls left-menu labels.

## 0.3.32

- Show offline/unavailable Presence sensor counts on area cards.

## 0.3.31

- Add Settings > Presence with area cards, saved FHT light-group assignments, and per-area status refresh controls.

## 0.3.30

- Move Home Assistant device details to the bottom of Protect cards and show linked entities in two columns.

## 0.3.29

- Use full-width Protect cards for sirens, sensors, cameras, and chimes; place Bridges beneath Key Fobs.

## 0.3.28

- Place the Unifi inventory update time directly beneath the Unifi Protect title.

## 0.3.27

- Send the App Exit action directly to Home Assistant Updates.

## 0.3.26

- Show linked Home Assistant Protect entities and their states, improve Chime ring settings, widen Users, and show the Unifi inventory update time.

## 0.3.25

- Link Unifi Protect cards to matching Home Assistant Protect devices by MAC/Protect identifier.

## 0.3.24

- Add Unifi Protect Bridge cards with MAC and client MAC details.

## 0.3.23

- Use a fixed three-column Unifi card layout and rate-limit/cached Protect inventory calls to avoid HTTP 429 responses.

## 0.3.22

- Use the standard three-column layout for key fobs, sirens, and sensors; support wrapped Chime API responses.

## 0.3.21

- Add Unifi Protect cards for cameras, chimes, and users; hide Arm Profiles from the resource list.

## 0.3.20

- Use two-column half-width cards for Unifi Protect key fobs and sirens.

## 0.3.19

- Keep Control dropdowns open during live refreshes and apply room display names to FHT light-group options.

## 0.3.18

- Add quick-read Unifi Protect cards for key fobs, sirens, and sensors while retaining raw JSON.

## 0.3.17

- Add Settings > Unifi with Protect arm/NVR details and raw v1 resource inventory.

## 0.3.16

- Toggle a Control directly when its status is selected.

## 0.3.15

- Restyle the Control status detail pop-up as a Home Assistant-style device panel.

## 0.3.14

- Add a color-coded live Protect arm-mode bubble to the top action bar.

## 0.3.13

- Restore the in-App control detail card when Home Assistant declines the native card request.

## 0.3.12

- Color the lowest-battery bubble by battery health.
- Simplify the lowest-device battery pop-up.

## 0.3.11

- Send the native entity-card request through both supported Ingress parent paths.

## 0.3.10

- Exclude Mobile App integration batteries from the lowest-battery indicator.

## 0.3.09

- Open Home Assistant's native entity card when a Control status is selected.

## 0.3.08

- Show the lowest device battery in the top action bar with device details.

## 0.3.07

- Open a device detail card when a Control status is selected.

## 0.3.06

- Refresh Controls status every three seconds only while that page is visible.

## 0.3.05

- Set FHT control-driven light-group on actions to 100% brightness.

## 0.3.04

- Request word-by-word capitalization for Room Configurator display names.

## 0.3.03

- Alphabetize the Settings submenu.
- Include valid integration-hidden lights when building FHT light groups.

## 0.3.02

- Make Room Configurator cards full width.
- Detect door, opening, garage-door, and door-named binary sensors.

## 0.3.01

- Add per-room door sensor assignments to FHT light groups.
- Turn the selected group on when a door opens and off when it closes.

## 0.2.67

- Make Dashboard, Lighting, Security, Climate, and Shades equal-level menu items.

## 0.2.66

- Add blank Lighting, Security, Climate, and Shades Dashboard pages.
- Move Entities, Dashboards, Scenes, and Blueprints into Settings.

## 0.2.65

- Organize App-created automations under the native Future Homes Tech category.

## 0.2.64

- Synchronize every direct switch assigned to the same FHT light group.
- Reconcile switches only after an on/off group state change.
- Send switch commands only when a control does not already match the group.

## 0.2.63

- Keep dedicated Fan Lights groups even when they match the area's All Lights members.
- Make fan groups available in the Controls light-group dropdown.

## 0.2.62

- Remove the Protect event-message tile and background WebSocket listener.
- Simplify the NVR tile to status, armed profile ID, armed time, and breach time.
- Refresh the NVR tile hourly instead of every three seconds.

## 0.2.61

- Replace the unreliable NVR device WebSocket tile with raw `GET /nvrs` data.
- Poll the authoritative NVR object every three seconds.
- Display the complete documented `armMode` object and current NVR fields.
- Retain the independent Protect event WebSocket diagnostic tile.

## 0.2.60

- Add an independent Protect `/subscribe/events` WebSocket listener.
- Display raw Protect event responses in a third Dashboard tile.
- Keep `/subscribe/devices` raw messages in the device-update tile.
- Expand the Dashboard width for three responsive Protect columns.

## 0.2.59

- Capture every Protect device WebSocket message, not only `armMode` updates.
- Display timestamped, formatted raw JSON in the Dashboard diagnostic tile.
- Retain only the latest 25 messages to keep memory bounded.

## 0.2.58

- Subscribe locally to Protect device WebSocket updates with the API key.
- Retain NVR/device messages containing `armMode` details.
- Add a second Dashboard tile showing live arm-mode update diagnostics.
- Keep the existing REST Protect arm-mode tile unchanged for comparison.

## 0.2.57

- Detect light-group changes without rewriting configuration.
- Show pending name changes on the notification bell and refresh dot.
- Rebuild groups only when the top-right Refresh action is clicked.
- Read renamed Matter light names stored on the Home Assistant device registry.

## 0.2.56

- Regenerate managed light groups whenever Settings > Light Groups opens.
- Build subgroup names from current Home Assistant friendly names.
- Reload Home Assistant only when generated light groups actually change.
- Preserve the existing entity IDs when a light is renamed.

## 0.2.55

- Add Room Configurator beneath Settings with one card per room.
- Persist optional App-only room display names.
- Apply room names across entity, light-group, control, and automation displays.
- Preserve all underlying Home Assistant entity and device identifiers.

## 0.2.54

- Generate native automations for every assigned Inovelli Matter gesture.
- Map any assigned Up gesture to `light.turn_on`.
- Map any assigned Down gesture to `light.turn_off`.
- Map any assigned Config gesture to `light.toggle`.
- Show each generated automation's action on Settings > Automations.

## 0.2.53

- Generate native `FHT -` Home Assistant automations for direct Control
  assignments.
- Turn the selected FHT light group on and off with the mapped switch state.
- Reload Home Assistant automations immediately after assignment changes.
- List generated Control automations on Settings > Automations.

## 0.2.52

- Rename the Settings submenu and page from Switches to Controls.
- Move Automations from the primary navigation into Settings.

## 0.2.51

- Detect installed Inovelli Matter Up, Down, and Config event entities.
- Display all seven advertised gestures for each button: one through five taps,
  long press, and long release.
- Allow each individual gesture to be persistently assigned to an FHT light
  group.

## 0.2.50

- Replace Switch Entity and Integration columns with an FHT Light Group
  dropdown.
- Persist each switch-to-light-group assignment across refreshes and App
  restarts.
- Save dropdown changes immediately through the App API.

## 0.2.49

- Enable Supervisor API access required for installed and available App version
  checks.
- Show an exclamation badge and readable notification when the update check
  fails instead of failing silently.

## 0.2.48

- Limit the Switches page to switch entities whose friendly name or entity ID
  contains a number followed by G or C.

## 0.2.47

- Display OFF status in gray on Light Group rows while preserving Switch status
  colors.

## 0.2.46

- Add a Switches submenu beneath Settings.
- Display switches in Area cards with friendly name, status, entity, and
  integration.
- Retain the centered Refresh icon correction from 0.2.45.

## 0.2.45

- Replace the asymmetric Refresh drawing with a balanced, centered icon.

## 0.2.44

- Open a system-wide friendly-name popup from the total offline count.
- Center friendly names in offline-device popups.
- Keep Offline / Unavailable column names white.
- Display an unavailable light group's status in bright red.

## 0.2.43

- Rename the Settings submenu from Groups to Light Groups.
- Show a numbered Notifications badge when Supervisor reports an App update.
- Show the available version inside the Notifications dialog.
- Show a red Refresh dot when the loaded interface version differs from the
  installed App version.

## 0.2.42

- Make each red per-Area offline count clickable.
- Open a compact modal listing the offline/unavailable friendly names for that
  Area.
- Support closing through the close button, backdrop, or native Escape action.
- Preserve bright-red emphasis for Unavailable entities inside the popup.

## 0.2.41

- Remove Offline and Unavailable lights from both Included and Excluded lists.
- Move those entities exclusively into the Offline / Unavailable column.
- Display Offline entity names in red and Unavailable entity names in bright
  red with stronger emphasis.
- Reuse one state classifier for system totals, Area totals, and all columns.

## 0.2.40

- Add a global Refresh icon between Notifications and Exit.
- Use a timestamped reload URL and disable interface asset caching so tablets
  immediately request the installed App version.
- List every Offline or Unavailable physical light in the Area within each
  generated group's offline column.
- Keep per-Area offline counts and displayed offline entity names aligned.

## 0.2.39

- Convert Settings from a page link into an expandable navigation header.
- Move Groups from the primary navigation into an indented Settings submenu.
- Require selecting Groups after opening Settings rather than navigating to a
  standalone Settings page.
- Collapse the Settings submenu when another primary page is selected.

## 0.2.38

- Standardize content-pane text, labels, entity IDs, and empty values to white.
- Preserve green ON states, red OFF states, and existing Protect status colors.
- Hide system and per-Area offline counters when their value is zero.
- Display every visible offline counter in red for quick exception scanning.

## 0.2.37

- Add frosted navy glass behind every generated Groups row.
- Add a slightly stronger glass treatment behind each Area header.
- Brighten Area names for improved contrast over the warp background.
- Preserve the background, navigation, and existing Groups structure.

## 0.2.36

- Replace Data Lanes with a luminous blue infinite vertical warp background.
- Repeat the warp only from top to bottom for long scrolling pages.
- Apply a symmetric black fade only to the outside left and right edges.
- Preserve equal blue detail and brightness at the top and bottom boundaries.

## 0.2.35

- Darken the Data Lanes pattern slightly and display it across every App tab.
- Remove the Exit item from the left navigation rail.
- Add global icon-only Notifications and Exit controls to the top-right corner.
- Keep Notifications as a visual placeholder while preserving Exit behavior.

## 0.2.34

- Replace the Groups artwork with the selected vertically repeating Data Lanes
  pattern.
- Reduce the Groups overlay so the background remains visible through cards.
- Move the existing navigation from the top toolbar into a fixed left rail.
- Increase and center the logo, App name, and simplified `V0.2.34` version.
- Rename Home to Dashboard and add Settings immediately before Exit.

## 0.2.33

- Make every Groups Area card and Area header background transparent.
- Extend the Hyperlane Ribbons artwork beneath the sticky toolbar.
- Reduce the artwork overlay while preserving legibility with text shadowing.
- Remove the opaque Groups background from the pinned Exit control.

## 0.2.32

- Pin the Exit control to the far-right edge of the top menu.
- Add the selected Hyperlane Ribbons artwork behind the Groups screen.
- Preserve card and text readability with a dark overlay and translucent cards.
- Serve approved interface artwork through the App's Ingress server.

## 0.2.31

- Add a stacked Exit icon and label to the right of Groups.
- Open the ingress interface as a kiosk-style full App screen without the Home
  Assistant navigation chrome.
- Return directly to Home Assistant Settings when Exit is selected.

## 0.2.30

- Restore the neutral background on each Area header.
- Center Area names and display them in the darker Future Homes Tech blue.
- Add a compact light-blue divider between each Area header and its groups.

## 0.2.29

- Center the Light Groups page title.
- Use the Future Homes Tech light blue for Area headers.
- Bold total and per-Area group counts.
- Add system-wide and per-Area Offline / Unavailable light totals.
- Center group status values and display ON in green and OFF in red.

## 0.2.28

- Resolve entity Areas directly from Home Assistant's area, device, and entity
  registries.
- Correct per-group Excluded Lights when physical entities do not yet expose
  customized Area state attributes.
- Cover device-inherited Areas, including Bathroom 1 toilet lights.

## 0.2.27

- Attach the three light-detail columns directly beneath every generated group.
- Calculate Included and Excluded lights separately for each group.
- Limit Offline / Unavailable to lights included in that group.
- Display friendly names instead of entity IDs in all three lists.

## 0.2.26

- Tighten spacing between generated group rows and strengthen separators.
- Replace per-group included-light details with three Area-level columns:
  Included Lights, Excluded Lights, and Offline / Unavailable.
- Show compact entity IDs only in the Area-level light lists.

## 0.2.25

- Always create `Area All Lights` for every Area containing at least one
  eligible light, including single-light Areas.
- Omit specific fixture groups whose members exactly duplicate `Area All
  Lights`.
- Organize the App's Groups tab into Area cards.
- Show each group's Friendly Name, Status, Entity ID, and included light names
  and entity IDs.

## 0.2.24

- Add a live Light Groups list to the App's Groups tab.
- Refresh the list automatically whenever Groups is selected.
- Display Friendly Name, Status, and Entity ID for every `light.fht_*` group.
- Exclude locally created light groups from the App-managed list.

## 0.2.23

- Skip an area's `All Lights` helper when its single specific group contains
  exactly the same lights.
- Keep `All Lights` when it covers additional fixtures or is the area's only
  useful generated group.
- Remove obsolete App-managed group entries from the Home Assistant entity
  registry while preserving every locally created group.

## 0.2.22

- Create or reuse the native Home Assistant Helpers category `Light Groups`.
- Assign every generated `light.fht_*` group helper to that category at App
  startup.
- Leave locally created light groups and their categories unchanged.

## 0.2.21

- Display generated light groups with their normal friendly names.
- Retain the `light.fht_*` entity ID prefix so App-managed groups remain easy
  to distinguish from locally created groups and helpers.

## 0.2.20

- Generate managed light groups from the Home Assistant area, device, and
  entity registries whenever the App starts.
- Prefix generated names with `FHT -` and unique IDs with `fht_`.
- Store generated groups in
  `/config/packages/future_homes_tech_light_groups.yaml`.
- Preserve existing YAML light groups and exclude group entities from generated
  memberships.
- Reload Home Assistant YAML only when generated content changes.

## 0.2.19

- Hardcode the shared Future Homes Tech Device Offline Webhook.
- Remove the Device Offline Webhook option from App configuration.
- Make the Protect API key optional.
- Continue loading all non-Protect features when an installation has no
  cameras or Protect API.

## 0.2.18

- Replace the entry-delay timer and two automations with one single-mode
  automation.
- Rename the workflow to Future Homes Tech - Alarm Exterior Door Entry Delay.
- Ignore additional exterior-door webhooks while the entry delay is active.

## 0.2.17

- Reload managed REST commands, timers, and automations when the App starts.
- Report one startup error listing any managed YAML domains that failed to
  reload.

## 0.2.16

- Add the configurable `Entry delay seconds` App option.
- Add the standard local entry webhook
  `/api/webhook/future_homes_tech_entry_delay`.
- Start or restart a managed Home Assistant entry-delay timer on each webhook.
- Call the derived Protect `Armed Siren` webhook when the timer finishes.
- Keep the entry webhook local-only and reuse the configured Protect API key.

## 0.2.15

- Discover and cache Protect arm profiles when the App starts.
- Create `sensor.future_homes_tech_protect_arm_mode`.
- Publish Disarmed, Arming, or the active profile name every 15 seconds.

## 0.2.9

- Query the official Protect NVR endpoint for current arm-mode status.
- Reuse the configured Protect API key and webhook API base.
- Display Protect Arm Mode automatically on the Home tab.
- Include the NVR name when returned by Protect.

## 0.2.8

- Read entity integration sources from the Home Assistant entity registry.
- Display Integration after Entity in every Domain and Offline entry.
- Keep entities visible with a blank Integration when registry metadata is not
  available.

## 0.2.7

- Serve the Future Homes Tech logo with the correct PNG response.
- Add an italic Offline group before every real Domain.
- Include all entities with an Offline or Unavailable status in the Offline
  group.

## 0.2.6

- Remove Automation, Calendar, Conversation, Sun, and Weather Domains from the
  displayed entity inventory.

## 0.2.5

- Filter excluded entities before sending results to the UI.
- Remove Identify and Calibrate entities from the Button Domain.
- Remove Device Tracker, Notify, Number, Person, Remote, Script, Select, STT,
  Text, To-do, TTS, Update, and Zone Domains.
- Remove every `input_*` helper Domain.

## 0.2.4

- Replace the large sidebar interface with a compact top menu.
- Add Home, Entities, Dashboards, Automations, Scenes, Blueprints, and Groups tabs.
- Refresh entities automatically whenever the Entities tab is selected.
- Group entities in collapsible Domain sections.
- Display only Friendly Name, Status, and Entity inside each Domain.

## 0.2.3

- Display entity inventory results only in the App content panel.
- Stop writing entity records to the App log.
- Stop persisting entity inventory results to the App data directory.

## 0.2.2

- Add the official Future Homes Tech logo and square App icon.
- Use the logo in the Home Assistant App Store and App interface.
- Establish shared canonical branding assets for future projects.

## 0.2.1

- Display every entity directly in the App interface.
- Show Entity, Friendly Name, Status, Class, and Domain columns.
- Use the patch version for incremental App updates.

## 0.2.0

- Add an Ingress web interface for the Home Assistant sidebar.
- Add the Future Homes Tech navigation menu.
- Add the Get All Entities action.
- Write a sorted entity inventory to the App log.
- Save the latest structured inventory in the App data directory.

## 0.1.0

- Add Protect API key and device-offline webhook configuration.
- Manage `rest_command.unifi_device_offline`.
- Store the Protect API key in Home Assistant `secrets.yaml`.
## 0.3.68

- Lists physical Zigbee Home Automation button devices by area on the Buttons page.
- Stops confusing switch event entities with the installed button devices.
## 0.3.69

- Adds native ZHA device-trigger assignments for physical button devices.
- Each available button press can toggle its selected Future Homes Tech light group.
## 0.3.70

- Corrects ZHA button trigger discovery to use Home Assistant's device-trigger list API.
## 0.3.71

- Limits Button assignments to real ZHA remote-button press actions.
- Removes diagnostic triggers and duplicate trigger labels from button cards.
## 0.3.72

- Refreshes the Presence offline badge whenever the App refreshes.
- Centers Button device titles and displays each device's press assignments in two columns.
## 0.3.73

- Shows the current weather temperature beneath the App version and refreshes it every five minutes.
- Preloads Settings data in menu order after refresh, with UniFi Protect resources loaded last.
## 0.3.74

- Simplifies Zigbee button actions to Short Press, Double Press, Long Press, and Long Release.
- Falls back to a new Future Homes Tech Light Groups helper category when Home Assistant rejects the legacy category rename, allowing stale FHT groups to be cleaned up.
## 0.3.75

- Consolidates the Climate thermostat display into one unified target-temperature card.
## 0.3.76

- Softens nested Automation card transparency across area, device, and automation levels.
- Prevents the toolbar temperature from falling back to zero when weather attributes are missing.
## 0.3.77

- Categorizes generated automations into Future Homes Tech Door Sensors, Switches, Climate, Presence, and Motion categories.
## 0.3.78

- Styles `Tech` and the spaced version label with the shield’s dark blue accent.
- Adjusts Automation card transparency to 44%, 43%, and 42% by nesting level.
## 0.3.79

- Categorizes direct switch activations as Future Homes Tech Switch Activation.
- Categorizes light-group-to-switch synchronization as Future Homes Tech Light Sync.
## 0.3.80

- Sets Automation nesting to a 40% outer surface with 1% and 2% inner overlays.
## 0.3.81

- Renames the Light Groups category to Future Homes Tech Light Groups.
- Adds Future Homes Tech Ungrouped for remaining App-managed helpers.
## 0.3.82

- Changes Automation area titles to white.
- Applies the shared glass treatment to the Apple HomeKit page.
## 0.4.96

- Restricts Device Alarm outputs to real Play Siren, Play Buzzer, and Play Chime actions while excluding restart, unadopt, identify, and unrelated buttons.
- Converts the audible output control to a checkbox multi-picker so any combination of sirens and chimes can be selected.
- Fires all checked outputs together and preserves One Time or Indefinitely Until Clear behavior.
## 0.4.97

- Simplifies Home Configurator Room Modes into one expanding card with a single flat checklist and no nested Available Modes or mode-detail cards.
- Limits selectable Room Modes to Sleep, Wake Up, Game, Relax, Movie, Study, Chill, Infant, Toddler, Baby, Armed Away, Armed Stay Kids, Armed Stay Adult, and Disarmed.
- Keeps internal Day and Night helper states available for existing solar mode automation without exposing them as selectable Room Modes.
## 0.4.98

- Limits the current Room Modes checklist to bedroom areas so other room types can receive purpose-built mode sets later.
- Hides the room-mode badge when no homeowner-enabled mode is currently active, removing the Not Set placeholder from initial load and background refreshes.
- Preserves active enabled bedroom mode labels while keeping non-bedroom room headers clean.
## 0.5.153

- Matched Switches and Presence to the Home Configurator and Doors mobile header layout, including safe-area spacing and the glass header fade.
## 0.5.154

- Centered the iPhone progress bar within the sticky header.
## 0.5.155

- Hide redundant room-wide All Lights groups when a named multi-light group already covers the room.
## 0.5.156

- Ordered Presence modes as Sleep, Day, Night, then the remaining room modes with a divider.
- Newly assigned Presence actions now default every available mode to enabled at 100% brightness.
- Restored two-column Presence cards on tablet and desktop, keeping phones single-column.
## 0.5.157

- Deduplicated single-light rooms so Entry exposes only its singular light option instead of All Lights/Lights variants.
## 0.5.158

- Refrigerator door alarms now display each device's actual registry name instead of the generic Fridge Door label.
## 0.5.159

- Restored two-column Presence cards by allowing grouped sensors to occupy a normal card column.
- Matched Presence card typography, spacing, glass styling, and controls to Doors.
## 0.5.160

- Matched Presence action, activation-delay, and clear-delay rows to the Doors stacked layout with full-width controls.
## 0.5.161

- Changed Presence activation and clear delays to minute dropdowns from Off through 120 minutes.
- Expanded the backend delay limit to 120 minutes while preserving stored values in seconds.
## 0.5.162

- Applied the Doors timeout dropdown styling and typography to Presence activation and clear delays.
## 0.5.163

- Combined Presence groups now use full-width cards; individual Presence sensors remain two-column on tablet and desktop.
# 0.5.164

- Adds a saved multi-select Parent Presence Groups control to same-area presence sensors.
- Prevents a sensor's clear action from turning lights off while any selected parent presence group remains occupied.
- Preserves existing presence actions, delays, mode brightness settings, and approved stable rollback 0.5.23.

## 0.6.1

- Adds a Beta mode App option (off by default) and a BETA badge shown only when it is enabled.
- Documents separate Stable (`main`) and Beta (`beta` branch) update channels so only Beta subscribers receive in-development updates.
- Becomes the homeowner-approved stable release, replacing retired stable 0.5.23.

## 0.6.2

- With Beta mode on, the App checks the `beta` branch and shows "Beta X Available" when a newer Beta build is published.
- Installing a Beta update downloads it into the App's private storage and restarts only the App; the next start runs the Beta build.
- Turning Beta mode off, or installing a Stable version at least as new, starts the Stable build again.

## 0.6.3

- A local App install exports its saved settings and configuration on each start to a private transfer file in the Home Assistant configuration directory.
- A new repository install with no saved settings imports that file once on first start, applies the configuration, restarts, and deletes the transfer file.

## 0.6.4 (Beta)

- Removes the "Action" label under each Presence sensor and Presence group title; the action selector keeps an accessible name.

## 0.6.5 (Beta)

- After a Beta update, the interface checks the fast health status for the restarted App instead of the slower update status, and reloads as soon as the App is back.
- If the App has not restarted after a minute, the button says to restart it from Home Assistant; the downloaded Beta starts on that restart.
- Logs the Home Assistant response when an App restart request is refused.

## 0.6.6

- Fixes a startup loop with Beta mode on: the Beta startup script now continues in the same shell, so the "already applied" flag is kept instead of being cleared by with-contenv.
- A Beta build that has not reached a running interface after three starts is skipped and Stable starts instead, until a newer Beta build is installed.

## 0.6.7 (Beta)

- Includes Stable 0.6.6 startup fixes with the 0.6.4 and 0.6.5 Beta changes.

## 0.6.8 (Beta)

- A sensor that selects a Parent Presence Group now counts as occupancy for that group, so the group stays occupied (and its lights stay on) while only the child sensor detects presence.
- A child sensor's clear action still waits for the rest of its parent group, ignoring its own presence, so it is not blocked by itself.
- Saving a Presence sensor updates the generated group sensors and reloads templates.

## 0.6.9 (Beta)

- Saving a Presence sensor's mode percentages or on/off choices now applies them immediately when that sensor currently detects presence, instead of waiting for the next detection or mode change.

## 0.6.10 (Beta)

- A sensor whose own Home Assistant area was deleted now appears in its device's room instead of Unassigned.
- Presence groups use the same area rule as their member sensors (a sensor's own area first, then its device's), so a group and its members appear in the same room.

## 0.6.11 (Beta)

- Presence shows each area as one card with the red, green, or blue accent edge; the sensors inside are borderless sections separated by space.

## 0.6.12 (Beta)

- Presence cards warn when another presence sensor or group turns on the same lights with a different brightness for the same mode, and name that sensor and its percentage.

## 0.6.13 (Beta)

- Reworks Parent Presence Groups: a child sensor controls its own lights on and off independently, and its parent group's lights stay on while the child detects presence.
- A child no longer turns its parent group's lights on and is no longer counted in the group sensor (reverts the 0.6.8 group membership).
- When the child clears after the group has already cleared, the group's lights turn off after the group's clear delay.

## 0.6.14 (Beta)

- With Beta mode on, the header checks for a new Beta build every 20 seconds and whenever the App comes back into view.
- The App checks the beta branch's newest commit on GitHub instead of the raw file, which GitHub caches for up to five minutes; unchanged answers do not count against GitHub's request limit.
- Beta updates download the exact commit that was offered.

## 0.6.15 (Beta)

- Presence no longer shows Sleep Number (SleepIQ) bed sensors, does not group them, and does not generate presence automations for them. Any saved choices for them are kept, not deleted.

## 0.6.16 (Beta)

- Action and Presence dropdowns only offer Future Homes Tech light groups the App currently generates. Groups Home Assistant still remembers from earlier releases (such as Bedroom 5 All Lights after it became Fan Lights only) are hidden, and saved actions on them show the room's current group.

## 0.6.17 (Beta)

- On every start (including after an update), removes Future Homes Tech automations, light groups, and template sensors that Home Assistant still lists but no configuration provides anymore. Only unavailable entities with an App unique ID that appears in no configuration file are removed; removals are listed in the App log.
- Light-group cleanup matches groups by unique ID, so a renamed current group is kept and an old group with a different entity ID is removed.

## 0.6.18 (Beta)

- On every start, renames App-generated light groups and presence groups whose entity IDs lack the fht_ prefix (kept by Home Assistant from older names) to their fht_ IDs, and updates saved App settings to the new IDs.
- Presence groups are categorized under Future Homes Tech Light Groups alongside the light groups.

## 0.6.19 (Beta)

- A room whose lights form only one multi-light group (for example Bedroom 4 Fan Lights) no longer also gets an All Lights group.
- Saved actions that used a removed All Lights group move to the room's group plus any room lights outside it, so they keep controlling the same lights; the moves are listed in the App log.

## 0.6.20 (Beta)

- In a room whose lights form one group, old All Lights groups from early releases (IDs without fht_) fold into that group in dropdowns instead of reappearing beside it.
- Start-up cleanup also removes those early-release room groups when Home Assistant lists them as unavailable and no configuration provides them.

## 0.6.21 (Beta)

- A single light is no longer wrapped in its own group (for example Bedroom 6 Desk Light); it is offered as the light itself.
- Single lights no longer count as groups, so a room with Fan Lights plus one Desk Light gets Fan Lights only, without All Lights.
- Saved actions that used a removed single-light group, or a removed All Lights group, move to the actual lights so they keep controlling the same bulbs.

## 0.6.22 (Beta)

- Restores All Lights in rooms where it covers more than one group can (for example Bedroom 6: Desk Light, Fan Lights, and All Lights). Rooms whose lights are all fan bulbs still get Fan Lights only.
- Single lights remain offered as themselves, without a group of one.

## 0.6.23 (Beta)

- Start-up cleanup ignores comments when checking whether configuration still provides an entity, so replaced single-light groups (such as light.bedroom_6_desk_lights) are removed.
- Early-release room light groups of any kind (not only All Lights and Fan Lights) are removed when unavailable and no configuration provides them.

## 0.6.24 (Beta)

- Safe Cleanup's scan now lists leftover entities not made by Future Homes Tech: entities Home Assistant still lists that no integration provides, with their integration. The list is read-only; delete them in Home Assistant after review.

## 0.6.25 (Beta)

- Safe Cleanup scans no longer stop on commented-out `!include` lines or includes of files that do not exist yet; those cannot define or reference anything.
- ESPHome and Zigbee2MQTT folders are skipped, and any remaining blocking message names the file that needs review.

## 0.6.26 (Beta)

- Safe Cleanup names any configuration file it cannot read or parse instead of showing a general error.
- Unexpected maintenance errors show their type and write full details to the App log.

## 0.6.27 (Beta)

- Safe Cleanup reads included folders the way Home Assistant does: files only, skipping hidden folders such as the App's `packages/.fht-backups` configuration backups.

## 0.6.28 (Beta)

- Combined light groups keep their location words: her and his bathroom vanities combine as Bathroom Vanity Lights instead of Vanity Lights.
- Groups with exactly the same lights as a more specific group (such as Toilet Lights beside Bathroom Toilet Lights) are no longer created.
- Saved actions on the old group names move to the new groups.

## 0.6.29 (Beta)

- Presence action and Parent Presence Group lists save once when the list closes, like Doors and Switches, instead of after every checkbox. Choosing several lights quickly no longer loses choices made while a save was running.

## 0.6.30 (Beta)

- Registry and helper commands share one kept-open Home Assistant connection instead of opening a new one for each batch.
- Beta updates use a verified release manifest (RELEASE.json): only files that differ are downloaded, each pinned to the offered commit and checked against its SHA-256, instead of the whole 24 MB repository.
- A Beta that needs configuration options or system packages the installed Stable lacks is refused with a clear message.
- New optional GitHub access token option for a private repository (takes effect with the next Stable release).
- Start-up cleanup no longer deletes retired entities silently: Safe Cleanup lists them for approval, with an option to delete them automatically from then on. Deleted registry entries are recorded privately first.
- Next Stable release: the App starts automatically with Home Assistant, a watchdog restarts it if it stops responding, and the base image is pinned.
- Unexpected maintenance errors are logged without their message text, which could contain credentials.

## 0.6.31 (Beta)

- New Settings → Light Groups page: every group the App builds for each room, its lights, and why; rename a group or keep a light out of every group, and saving rebuilds the groups right away.
- Saving Presence settings re-applies brightness only to lights still at the App's previous brightness, so lights someone dimmed or turned off are left alone.
- A Beta start counts as healthy only after the App has run for three minutes, so a Beta that crashes soon after starting still falls back to Stable.
- After a repository install has the settings, a local install stops re-exporting them, and leftover settings transfer files are deleted.

## 0.6.32 (Beta)

- Internal: the action-editor light and switch catalog moved from server.py into fht_catalog.py, the first step of splitting server.py (docs/CODE_SPLIT_PLAN.md). No behavior change.

## 0.7.0 (Stable)

Homeowner-approved Stable release bringing together Beta 0.6.7–0.6.32:

- The App starts automatically with Home Assistant, a watchdog restarts it if it stops responding, and the base image is pinned (ghcr.io/home-assistant/base:3.24-2026.08.0).
- New optional GitHub access token option, needed only if the repository is made private (see docs/BETA_CHANNEL.md).
- Beta mode: checks for Beta builds every 20 seconds, installs verified small packages (RELEASE.json), refuses Betas that need a Stable update first, and falls back to Stable after repeated failed starts.
- Presence: one card per area, Parent Presence Groups hold their group's lights while a child sensor detects presence, brightness conflict warnings, saves on list close, and saves no longer override manual dimming. Sleep Number bed sensors are hidden.
- Light groups: fht_ entity IDs and one category, no single-light groups, All Lights only when it adds something, combined groups keep location words, and the new Settings → Light Groups page to preview, rename, and keep lights out of groups.
- Safe Cleanup scans real configurations, lists leftover entities not made by the App, and asks for approval before deleting retired App entities.
- One kept-open Home Assistant connection for registry work; stricter release gate (lint and browser checks).

## 0.7.1 (Beta)

- Removes the Settings → Light Groups page and its group renaming and exclusion overrides; light groups are built exactly as before that page.

## 0.7.2 (Beta)

- New Settings → Room Devices page, above Home Configurator: one card per room listing every entity's name and entity ID in two columns, with a filter by room, name, or entity ID.

## 0.7.3 (Beta)

- Room Devices drops the room name (both the App room name and the Home Assistant area name) and the "FHT - " prefix from each name, since the card title already names the room. The filter still matches full names.

## 0.7.4 (Beta)

- Room Devices hides diagnostic and configuration entities whose name or entity ID ends with Firmware, Identify, LQI, RSSI, Off transition time, On level, On transition time, On/Off transition time, Power on behavior, or Power on level.

## 0.7.5 (Beta)

- Room Devices hides every Power-on behavior entity, wherever the phrase appears in its name or entity ID (for example "Power-on behavior 2" or "Power On Behaviour (startup)"), not just at the end.

## 0.7.6 (Beta)

- Room Devices no longer shows the Bridges room.
- Room Devices also hides entities whose name or entity ID ends with Battery type or Battery voltage (Identify was already hidden).

## 0.7.7 (Beta)

- Room Devices shows each entity's current state (with its unit, such as 71.5 °F) as a small tag in front of its name: green for on/open, grey for off/closed, red for unavailable/unknown.

## 0.7.8 (Beta)

- Fixed: choosing the first actions for a presence sensor that had none (a new sensor, or one whose actions were cleared) now turns every mode on at 100% again. The page read the card's "no actions" marker as if actions already existed, so the defaults were skipped.

## 0.7.9 (Beta)

- Camera sensors are no longer treated as presence. Any sensor on a device that has a camera (UniFi Protect, Frigate, Reolink and similar), or whose name says Camera or Doorbell, is left off the Presence page and out of the automatic presence groups. Saved presence actions on a camera sensor stay saved but no longer run. UniFi Protect sensors without a camera, such as the UP-Sense, still count.

## 0.7.10 (Beta)

- Doors and Presence load much faster: one request now carries every room's door sensors, mode options and saved settings, so the pages no longer make a separate request for each room (three at a time) while the progress bar fills. Switches already worked this way.

## 0.7.11 (Beta)

- Room Modes: ticking a mode now opens a pop-up with that mode's settings for that room (for example "Maverick's Bedroom · Toddler"). Toddler shows its own panel (monitored door, alert lights and colour, chimes, repeats, auto-off, Inovelli LED); every other mode shows its Room Scene (lights, brightness, colour). A gear next to each ticked mode reopens its pop-up.
- Removed the hidden Device Health and Action Timeline leftovers, including the background recording of every state change that only fed them.
- Removed page code that was never called (four functions) and two unused server helpers.

## 0.7.12 (Beta)

- Fixed: on Doors, choosing an action in a room with a display name (Maverick's Bedroom, Chloe's Bedroom…) showed "A door and its mode settings are required." The 0.7.10 snapshot keyed each room's mode options by display name while the page looked them up by the Home Assistant area name, so no mode rows rendered. The rows now always render, with Day/Night/Whole Home Sleep as the fallback.

## 0.7.13 (Beta)

- The App package is about 2.5 MB instead of 8.5 MB: the red and green backgrounds are now WebP and the colour logos are 256 px.
- Removed the "coming soon" Shades and Climate entries from the main menu and the Amazon Alexa and Google Nest tabs. Voice Control opens Apple HomeKit directly; climate settings stay under Settings → Climate.
- The App configuration page now shows names and descriptions for Verify Protect certificate, Protect CA certificate and Entry delay webhook ID.
- The one-time saved-reference repair from 0.5.1 no longer runs at every start.

## 0.7.14 (Beta)

- Exhaust fans can follow a humidity sensor: on Settings → Switches, each exhaust fan timer row gains a same-room **Humidity sensor** picker with **Start above** and **Stop below** levels. The fan turns on when humidity rises above the start level and off once the room has stayed below the stop level for two minutes. The manual timer still works as before and no longer cuts short a humidity-started run, nor turns off a hand-started fan while the room is still humid.

## 0.7.15 (Beta)

- Site profile: this home's Protect console address, time zone, weather entity and room/door naming rules now live in `site_profile.json`, with an optional per-installation override in `/data/site_profile.json`, so the same App can run in another home without code changes. Nothing changes for this home. Settings → Unifi shows the active profile read-only; every key is documented in docs/SITE_PROFILE.md.

## 0.7.16 (Beta)

- Alarm → Device Sensors gains **Door Left Open** reminders for any door or window sensor, grouped by room: a delay, Any time / Night / Night and Sleep timing, and siren, chime, notification and UniFi webhook outputs. The reminder clears when the door closes, and a Night reminder also fires if the house enters Night while the door has already been open too long.

## 0.7.17 (Beta)

- Phone alerts through the Home Assistant Companion app: Settings → Alarm → Device Sensors lists every signed-in phone with a **Send test** button, and each refrigerator door and temperature alert gains "Phone: …" tick boxes beside the sirens and chimes. The bedroom Armed Away and Armed Stay Kids panels (Room Modes pop-up) gain the same tick boxes, so a door opening while armed can notify a phone even without a UniFi webhook. Phones are off by default; the notice clears itself when the door closes or the temperature drops.

## 0.7.18 (Beta)

- Wake Up routines are set up from Settings → Room Modes: turn on **Wake Up** for a room (or press its gear) to edit the days, time, actions, brightness and override time in the pop-up.
- Fixed: wake routines at 10:00 or later no longer stop the room's wake automation from loading (times are now quoted in the generated package).
- Fixed: a wake routine whose light or speaker has been renamed, or has not loaded yet, no longer blocks the App's start-up activation or other rooms' wake saves; the App logs which devices are missing and keeps the routine.
- Fixed: saving a wake routine with a Room Mode action no longer re-declares the room's mode helper (no more "duplicate key" package error or extra reload on every start and save).
- Fixed: a rare start-up deadlock between the HomeKit bridge settings and other configuration saves.
- Fixed: opening the App long after it started now loads the battery level and exterior door status straight away.

## 0.7.19 (Beta)

- Every saved settings file keeps its last 20 versions, and the Doors, Switches, Buttons, Presence, Room Modes, Scenes, Alarm, Home Configurator and Apple HomeKit pages gain an **Undo last change** pill showing when that change was made. Press it to see what changed and put the page's settings back; the generated automations are rebuilt to match. Undoing an undo redoes it.

## 0.7.20 (Beta)

- Presence and Doors: each mode rule can set a light tone after its brightness — Current, Warm (2700 K), Neutral (4000 K), Cool (5500 K), Adaptive (follows daylight) or a custom Kelvin — applied together with the brightness to lights that support it. Existing rules stay on Current, so nothing changes until you pick a tone.

## 0.7.21 (Beta)

- Internal: the sixteen settings stores now share one base class (261 fewer lines in server.py). Saved files, return values and generated packages are unchanged; verified by a before/after comparison of every store.

## 0.7.22 (Beta)

- Removed the hidden header arm-mode, Exterior Doors and Battery Inventory indicators with their dialogs, the `/api/batteries`, `/api/battery-types` and `/api/security/entry-status` routes and the battery-type store (about 1,200 lines). The Unifi Protect Arm Mode panel and the Security page are unchanged. The saved `battery_type_assignments.json` is left on disk.

## 0.7.23 (Beta)

- Housekeeping: the stale ROADMAP.md no longer ships in the package; design mock-ups, original logo files and orphaned developer scripts were removed from the repository.

## 0.7.24 (Beta)

- "Undo last change" moves off the individual settings pages into one **Revert Changes** card at the bottom of Home Configurator. It lists the recent saves from every settings page (which page, what changed, when) with a **Revert** button on each. A revert is itself listed as a change, so it can be reverted again.

## 0.7.25 (Beta)

- Doors: in one-column (phone) layout a blue line now separates the doors inside a room card; in two-column layout each door becomes its own card with the left highlight.

## 0.7.26 (Beta)

- Removed the Alarm page's Door Sensors tab and its unused per-mode door selections (nothing generated automations from them; the saved file is left on disk), so Alarm opens directly on Device Sensors. Removed the unreachable Pantry-only door colour cards from Doors; every door uses the shared mode rows with the tone picker.

## 0.7.27 (Beta)

- Room Devices: every state tag is now the same width, with the text centred, so the names line up down the page.

## 0.7.28 (Beta)

- Room Devices: the state tag is wide enough for "unavailable", and entities without a state show a blank tag so every name lines up.

## 0.7.29 (Beta)

- New Settings → **Environment** page, just before Presence: every exhaust fan grouped by room with its auto-off timer and its humidity sensor, start and stop levels. These controls have moved there from the Switches rows, which now show only the fan's actions.

## 0.7.30 (Beta)

- Switches, Doors and Presence: a collapsed action picker no longer repeats the room name the card already shows — in Master Bedroom, "Master Bedroom Bathroom Toilet" reads "Bathroom Toilet". The open list is unchanged.

## 0.7.31 (Beta)

- Internal: the stylesheet lost about 770 lines — 120 rules for classes nothing uses, 28 dead selectors and 15 folded duplicates. A computed-style comparison of every page at desktop and phone widths showed no visual change.

## 0.7.32 (Beta)

- The header shows how long the App took to open, under the version: **Server** (until the App answered), **Page** (until the page was drawn) and **Data** (until the first data arrived). Hover it for the explanation.
- Door Left Open reminders are now part of the settings history, so their changes appear in Home Configurator → Revert Changes under Alarm.

## 0.7.33 (Beta)

- The header's opening times are stacked one per line so they fit inside the sidebar.

## 0.7.34 (Beta)

- Environment now looks and lays out exactly like Switches: centred room headings, one glass card per exhaust fan with the blue left edge, two columns on wide screens and one on phones, the same top bar and loading bar. Every Switches style rule now also applies to Environment, so the two pages stay in step.

## 0.7.35 (Beta)

- Environment: the current humidity next to the sensor reads just "46%" instead of "Now 46%".

## 0.7.36 (Beta)

- Environment: each fan card is named after the fan instead of the switch channel it is wired to ("Laundry Switch Switch 3" reads "Exhaust Fan"; in Master Bedroom, "Bathroom Toilet Exhaust Fan"), and the humidity reading is plain white.

## 0.7.37 (Beta)

- Environment: a fan in a room with no humidity sensor shows only its timer; the Humidity sensor, Start above and Stop below fields are hidden.

## 0.7.38 (Beta)

- Environment: exhaust fans can follow a presence sensor in their room. When the room has one, the fan card shows **Presence sensor**, **Activation delay** (how long someone must be there before the fan starts, default 2 minutes) and **Clear delay** (how long it keeps running after the room clears, default 5 minutes). Nothing runs until a sensor is chosen. A humid room keeps the fan running past the clear delay. "Exhaust fan timer" is renamed **Manual fan timer**; it only arms when the fan is switched on by hand and never turns the fan off while someone is still in the room.

## 0.7.39 (Beta)

- New **Settings → Future Tech Portal**: Home Assistant pushes device status to the Future Tech Portal. Paste the portal token once and the App stores it only in Home Assistant's secrets.yaml (`future_tech_token`), writes `packages/future_tech_portal.yaml`, reloads Home Assistant and sends the first inventory. Reports: the full inventory 60 seconds after start and hourly (at most 150 devices per request), device offline after 2 minutes unavailable and recovered, low battery below 20% once per device a day, and a heartbeat every 10 minutes. Home Assistant only sends; the portal cannot control anything. The page shows the connection (green when reports are arriving, red when they are not or the token is rejected), the last report, devices reported, which integrations report, Send inventory now, and Remove token. Failed reports raise a "Future Tech Portal" notification with the status code only; a rejected token pauses automatic reports until a new token is saved. See docs/FUTURE_TECH_PORTAL.md.
- The Settings menu stays open on Room Devices and Environment.

## 0.7.40 (Beta)

- Future Tech Portal: the App's Configuration tab gets **Future Tech Portal token** and **Future Tech Portal URL**, right under the Protect API key. A token entered there is copied into Home Assistant's secrets.yaml when the App starts, the reporting package is installed and the first inventory is sent; the Settings page then shows that the token comes from the Configuration tab. The URL defaults to `https://futuretech.studio/api/beta/ingest` and must be https. Both are optional, so Beta still installs over Stable 0.7.0; the two fields appear in the Configuration tab once Stable includes them.
- Fix the App option descriptions: the translations file was not valid YAML (the Beta mode description), so Home Assistant could not show any option names or descriptions.

## 0.7.41 (Beta)

- Future Tech Portal: the inventory goes in one request (up to the portal's 500 devices, split only to stay under 256 KB) instead of chunks of 150. The portal treats each inventory as the complete list, so earlier chunks showed as "status unknown, missing from the last report".

## 0.7.42 (Beta)

- Future Tech Portal activity: each inventory also sends the home's automations (`kind: "automations"`: automationId, name, enabled, configId, lastTriggeredAt), and a new "Future Tech - activity" automation reports every automation run as it happens (`automation.triggered` event with automationId, name, source and occurredAt). The portal's own automations are left out, and reports go one at a time to stay within the portal's rate limit. See docs/FUTURE_TECH_PORTAL.md for the payloads.

## 0.7.43 (Beta)

- Future Tech Portal moves into **Home Configurator**, as a card at the bottom below Revert Changes, styled like the Whole Home and Revert Changes cards (blue-edged card, framed blocks, pill buttons, Room Names-style token box). The separate Settings page is removed.

## 0.7.44 (Beta)

- Future Tech Portal inventory: each device now says which Home Assistant integration it comes from: `integration` (for example `zha`, `unifiprotect`), `integrationName` (its name in Home Assistant), and `integrations` when a device belongs to more than one.

## 0.7.45 (Beta)

- Future Tech Portal: `lastSeenAt` is now when a device was really last seen. Online devices report the time of the report; offline devices report the last time they were online, kept across Home Assistant restarts (a restart used to make long-offline devices look "offline since" the restart). Devices already offline are filled in from Home Assistant's history (up to 10 days) when the App starts or an inventory is sent by hand. `device.offline` events also carry `lastSeenAt`.

## 0.7.46 (Beta)

- Future Tech Portal: a device's `integration` is now the integration that created it. Helpers that wrap another integration's entity, such as Switch as X, are never reported (Matter Wi-Fi switches shown as lights through Switch as X were reported as `switch_as_x`), and the device's own entity is used as its main entity.
- Future Tech Portal: UniFi Network switches and access points that UniFi lists as disconnected are reported offline. UniFi keeps their entities available, so the device's State sensor (`disconnected`, `heartbeat_missed`) now decides, in the inventory and for live offline/recovered events.

## 0.7.47 (Beta)

- Future Tech Portal: Matter devices now say which network they use, `network`: `thread`, `wifi` or `ethernet`, so the portal can separate Matter over Thread from Matter over Wi-Fi. The App reads it from the Matter integration's diagnostics when it starts and on Send inventory now; bridged devices take their bridge's network.

## 0.7.48 (Beta)

- Future Tech Portal: the inventory no longer sends a list of the home's automations (`kind: "automations"`). Only automation runs are reported, each as it happens (`automation.triggered`).

## 0.7.49 (Beta)

- Scenes → Light Automations now also lists lights that have no group of their own, such as a single porch or side-yard light, beside the room's groups (Outside All Lights, Outside Coach Lights). The light-group generator offers a lone light as itself instead of a one-light group, so those lights were missing; rooms with only one light are listed too. Schedules can be saved for them, and they stay listed after saving.

## 0.7.50 (Beta)

- House Mode Status no longer runs every minute. It set the house mode 1,440 times a day; it now runs only when the mode can change: at sunrise and sunset (with your offsets), when a bedroom enters or leaves Sleep, and when Home Assistant starts.
- Room Devices uses the same header as Doors, Switches and Environment.

## 0.7.51 (Beta)

- Fix the Mac Home Assistant app crashing when a light schedule's time of day is opened: the schedule card used the system time wheel, which the Mac app can't show. It now uses the App's own time picker (hour, minute, AM/PM), like Climate and Wake routines.
- Future Tech Portal: every inventory now carries `system` with the App version (`appVersion`, the Beta build when Beta mode is on), Home Assistant Core (`coreVersion`), Supervisor (`supervisorVersion`) and OS (`osVersion`), for the portal's System → Home Assistant card.

## 0.7.52 (Beta)

- Light Automations move from Scenes into **Home Configurator**, as the last section at the bottom, styled like the rest of Home Configurator: a centered "Light Automations" heading with the number enabled, one blue-edged card per room like Whole Home, framed light cards, and the same dropdowns. Scenes now shows Room Scenes.
- Room Devices is at most two columns wide (one on narrow screens).

## 0.7.53 (Beta)

- Future Tech Portal: the inventory's `system` block now lists every installed Home Assistant App (add-on) with its version, whether an update is waiting and its state (`apps`), and everything installed through HACS with its version, plus custom integrations HACS doesn't manage (`hacs`).
- Switches and Environment use the Doors layout: rooms sit two to a row; a room with one device takes one column, and a room with more spans the row with its devices in two columns.

## 0.7.54 (Beta)

- The App colour now recolours every card edge. On Doors, the separate door cards in a two-door room and the line between doors in a room stayed blue when red or green was chosen; card edges, accent lines, the loading spinner and outline buttons on every page now follow the App colour.

## 0.7.55 (Beta)

- Future Tech Portal: installed Apps and HACS items are sent in the format the portal expects, as their own report after each inventory: `{"kind": "apps", "appVersion": ..., "apps": [{appId, name, source, version, latestVersion, updateAvailable, state, category}]}`. `source` is `addon`, `hacs` or `custom`; HACS items now include their latest version and whether an update is waiting. They are no longer part of the inventory's `system` block.
- The apps report goes once a day with the hourly inventory; Send inventory now (or running the inventory script yourself) always sends it.
- The Dashboard uses the same header as Room Devices and Home Configurator: no bar, just the update and exit buttons in the corner.

## 0.7.56 (Beta)

- Environment is renamed **Environmental**. The refrigerator sensors stay on the Alarm page (0.7.55 had moved them to Environmental by mistake).

## 0.7.57 (Beta)

- Lighting and Security use the same header as Room Devices, Home Configurator and the Dashboard.
- Room Devices shows the loading bar at the top while it loads, like Switches and Environmental.

## 0.7.58 (Beta)

- Doors: a door's timeout now turns the lights off even when the timer was cut short. A Home Assistant restart, an App restart or update, or saving settings (which reloads automations) used to cancel a pending timeout, so a door left open kept its lights on. Each door automation now also checks how long the door has been open and turns the lights off once the timeout has passed, within about a minute.
- Doors: a door sensor coming back from unavailable no longer counts as the door opening.
- Future Tech Portal: **Send app versions now**, next to Send inventory now, sends only the installed Apps and HACS versions straight away, however many were sent today. The Connection card shows **Last app versions**, the last time the portal accepted them.

## 0.7.59 (Beta)

- New Betas show up in the header reliably. The App asked GitHub for the newest Beta every 15–20 seconds while it was open, even in a background tab. Without a GitHub access token, GitHub allows 60 requests an hour from one home, so it refused for most of each hour, and the header couldn't see new Betas. The App now asks every two minutes, and when you open it if the last check is a minute old. If GitHub still refuses, the App waits as long as GitHub asks, keeps offering a Beta it already found, and shows why on the BETA badge's tooltip.
- Setting **GitHub access token** in the App's Configuration tab removes GitHub's limit (a fine-grained token with read-only access to public repositories is enough).

## 0.7.60 (Beta)

- Future Tech Portal: HACS items are reported under the name HACS shows, such as "HACS" and "Alexa Media Player", instead of their GitHub repository name ("integration", "alexa_media_player"). HACS items are still found when HACS keeps its records only in its newer `hacs.data` file.

## 0.7.61 (Beta)

- Environmental: an exhaust fan with a presence sensor now runs once for a set time. When the activation delay ends, the fan turns on and a Home Assistant timer starts for the **Run time** (previously "Clear delay", 1 to 60 minutes). When the timer finishes, the fan turns off. Seeing someone again during the run no longer restarts or extends it, as the old clear delay did. The timer keeps running through settings saves, App restarts and Home Assistant restarts. Switching the fan off by hand ends the run. A paired humidity sensor still keeps a humid room's fan running until the air is dry.
- Beta mode looks for a new Beta every minute. Without a GitHub access token it reads GitHub's git branch list, which is never cached and doesn't count toward GitHub's limit of 60 checks an hour. With Beta mode off, the App asks Home Assistant for a Stable update once an hour.

## 0.8.1

- Stable release of everything through Beta 0.7.61: Future Tech Portal reporting (inventory, app versions with Send app versions now, automation activity), the door timeout backup, the exhaust fan run timer, reliable Beta update checks, and the interface changes from the 0.7.x Betas.

## 0.8.2 (Beta)

- Future Tech Portal: events are sent every 5 minutes instead of one at a time. Automation runs, offline, recovered and low battery events go into one queue, each keeping its own `eventId` and `occurredAt`. Every 5 minutes the queue goes out as `{"kind": "events", "appVersion": …, "events": [ … ]}`, in requests of up to 500 (sooner once 500 are waiting). A heartbeat goes out only when a window has nothing else to send. A 429, a 5xx or no answer keeps the events for the next send, and a 401 or 403 still pauses sending until a new token is saved. The queue holds at most 2,000 events or about 240,000 characters, dropping the oldest, and drops events older than 7 days. It survives restarts, and Home Assistant's history database doesn't store it. The Connection card shows how many events are waiting.

## 0.8.3 (Beta)

- The **Beta X Available** (and **Update Available**) button shows in the header again on every page. Since the shared corner header (0.7.55–0.7.57), the Dashboard, Doors, Switches, Lighting, Security, Environmental, Room Devices, Presence and Home Configurator headers hid every button except Updates and Exit, including the update button, so a waiting Beta only showed on Scenes. It now sits in the corner, to the left of Updates.

## 0.8.4

- Stable release of everything through Beta 0.8.3: Future Tech Portal events sent every 5 minutes from one queue, and the **Beta X Available** and **Update Available** button showing in the header on every page again.

## 0.8.6 (Beta)

- A room whose lights are all plain numbered lights (Dining Room Light 1 to 5, Pantry Light 1 and 2, Closet 1 Light 1 to 3, Upstairs Hallway Light 1 and 2) now gets one **Dining Room Lights** group instead of **All Lights**, and Lighting shows it under that full name. The group keeps its `light.fht_<room>_all_lights` ID, so saved switch actions, scenes and automations keep working. Rooms with other lights too (Kitchen) still get **All Lights**.
- Lighting shows every light again. A light that is in no group except the room's whole-room group now gets its own control: Porch Light, Side Yard Light and Backyard Light on the Outside card, a bedroom lamp, and the only light in Entry, Stairway or Laundry Room. Before, single lights only appeared through All Lights.
- Lighting only shows groups the App still writes. An old group that Home Assistant still remembers, such as Bedroom 6 All Lights from before that room became **Bedroom 6 Fan Lights**, no longer appears next to the current group.
- A bedroom with its own bathroom (Master Bedroom Bathroom Shower Light, Bathtub Light, Toilet Lights, Vanity Lights) gets a **Master Bedroom All Bathroom Lights** group with every bathroom light, toilet included. The Shower and Bathtub lights still have their own controls too. Rooms named Bathroom don't get it, because their All Lights already is the bathroom.

## 0.8.7

- Stable release of everything through Beta 0.8.6 (the Lighting groups and standalone lights) plus the change below.
- **Update Available** installs a Stable update in place, the way the Beta button does, instead of opening Home Assistant's Updates page. The App asks Home Assistant to install it through the App's update entity, shows **Updating to X…**, and reloads once the new version answers. If Home Assistant can't start the update, the button reads **Update Failed — Open Updates** and opens the Updates page on the next click.

## 0.8.8 (Beta)

- Pages show the thin loading bar at the top while they load, instead of a **Loading …** line. Lighting now has the same bar as Doors, Switches, Environmental and Presence, and its room cards appear once they are ready rather than half loaded. Room Devices drops its **Loading room devices…** line under the bar it already had. Security, Scenes, Room Modes, Climate and Buttons swap their loading lines for the same bar. Errors and "nothing found" messages still show as before.

## 0.8.9 (Beta)

- Lighting: inside a room's card, the room's group reads **Lights** again ("Dining Room Lights" shows as **Lights** under the Dining Room heading), the same way Fan Lights and All Lights drop the room name.

## 0.8.10 (Beta)

- The sidebar no longer shows the **Server / Page / Data** opening times under the version. The version, the BETA badge and the temperature stay.
