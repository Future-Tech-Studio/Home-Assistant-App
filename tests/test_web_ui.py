"""Release-gate tests for the Future Homes Tech App interface."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).parents[1]
WEB_INDEX = ROOT / "future_homes_tech_app" / "web" / "index.html"
WEB_ROOT = WEB_INDEX.parent
CONFIG_PATH = ROOT / "future_homes_tech_app" / "config.yaml"
SERVER_PATH = ROOT / "future_homes_tech_app" / "server.py"


class WebInterfaceTests(unittest.TestCase):
    def test_door_mode_assignments_and_deferred_picker_save(self):
        html = WEB_INDEX.read_text()
        self.assertIn("isPantryRoom(payload) || hasModeAssignments", html)
        self.assertIn('select.dataset.pendingActionSave = "true"', html)
        self.assertIn("delete select.dataset.pendingActionSave", html)

    """Protect current navigation, caching, and interaction architecture."""

    def test_blank_dashboard_and_transparent_mobile_header(self) -> None:
        home = self.html.split('id="view-home">', 1)[1].split('</section>', 1)[0]
        self.assertEqual(home.strip(), '')
        self.assertIn('top: var(--app-safe-top); background: transparent; border: 0; box-shadow: none; backdrop-filter: none; -webkit-backdrop-filter: none;', self.html)

    def test_mobile_header_respects_device_safe_area(self) -> None:
        self.assertIn('viewport-fit=cover', self.html)
        self.assertIn('--app-safe-top: env(safe-area-inset-top, 0px)', self.html)
        self.assertIn('top: calc(var(--app-safe-top) + 5px)', self.html)
        self.assertIn('top: calc(var(--app-safe-top) + 8px)', self.html)
        self.assertIn('top: calc(var(--app-safe-top) + 25px)', self.html)
        self.assertIn('body main { margin-top: var(--app-safe-top); }', self.html)

    def test_configurator_header_and_flat_alarm_sections(self) -> None:
        self.assertIn('id="home-floor-picker" aria-label="Home Configurator floor"', self.html)
        self.assertIn('prepend(document.getElementById("home-configurator-header"))', self.html)
        self.assertIn('card.open = card.dataset.floor === event.target.value', self.html)
        self.assertIn('floorPicker.value = selectedFloor', self.html)
        self.assertIn('<section id="alarm-door-card" aria-label="Door Sensors">', self.html)
        self.assertIn('<section id="alarm-device-card" aria-label="Device Sensors" hidden>', self.html)
        self.assertNotIn('class="house-mode-card fridge-alarm-category" id="alarm-', self.html)

    def test_buttons_have_a_dedicated_lazy_settings_page(self) -> None:
        self.assertIn('data-view="buttons">Buttons</button>', self.menu)
        self.assertIn('id="view-buttons" hidden', self.html)
        body = self.html.split('function buildRoomConfiguratorBody', 1)[1].split('async function hydrateRoomConfiguratorCard', 1)[0]
        self.assertNotIn('renderRoomButtonsSection', body)
        self.assertIn('if (view === "buttons") return loadButtonsPage', self.html)
        self.assertIn('if (select) saveSwitchAssignment(select)', self.html)
        self.assertIn('or str(key).split("|", 1)[0] in event_ids', self.server)

    def setUp(self) -> None:
        self.html = WEB_INDEX.read_text(encoding="utf-8")
        self.server = SERVER_PATH.read_text(encoding="utf-8")
        self.menu = self.html.split('<nav class="menu"', 1)[1].split(
            "</nav>",
            1,
        )[0]

    def test_voice_services_share_navigation_and_buttons_use_header(self) -> None:
        self.assertIn('data-view="voice-control">Voice Control</button>', self.menu)
        self.assertNotIn('data-view="homekit"', self.menu)
        self.assertIn('data-voice-provider="homekit"', self.html)
        for stub in ('alexa', 'nest'):
            self.assertNotIn(f'data-voice-provider="{stub}"', self.html)
        self.assertIn('prepend(document.getElementById("buttons-toolbar"))', self.html)
        settings = self.menu.split('id="settings-submenu" hidden>', 1)[1]
        self.assertLess(settings.index('data-view="buttons"'), settings.index('data-view="climate-settings"'))

    def test_navigation_keeps_current_settings(self) -> None:
        """Expose supported screens and keep Settings expandable."""
        for view in (
            "home",
            "lighting",
            "security",
            "voice-control",
            "climate-settings",
            "scenes",
            "rooms",
            "unifi",
        ):
            self.assertIn(f'data-view="{view}"', self.html)
        self.assertIn('id="settings-toggle"', self.html)
        for removed in ("dashboards", "action-timeline", "device-health", "climate", "shades"):
            self.assertNotIn(f'data-view="{removed}"', self.html)
        self.assertIn('aria-controls="settings-submenu"', self.html)
        self.assertIn(
            'class="settings-submenu" id="settings-submenu" hidden',
            self.html,
        )
        self.assertIn('data-view="rooms">Home Configurator</button>', self.html)

    def test_retired_settings_screens_are_absent(self) -> None:
        """Do not ship obsolete standalone editors or their routes."""
        for view in (
            "automations",
            "blueprints",
            "entities",
            "groups",
        ):
            self.assertNotIn(f'data-view="{view}"', self.menu)
            self.assertNotIn(f'id="view-{view}"', self.html)
        self.assertNotIn("preloadSettingsViews", self.html)
        self.assertNotIn('requestJson("api/control-automations"', self.html)
        self.assertNotIn("api/door-light-groups", self.html)
        for route in (
            "/api/action-catalog",
            "/api/control-automations",
            "/api/door-light-groups",
            "/api/room-entities",
        ):
            self.assertNotIn(route, self.server)

    def test_displayed_version_matches_addon_metadata(self) -> None:
        """Keep the browser client and Supervisor package versions aligned."""
        match = re.search(r"^version:\s*([^\s]+)", CONFIG_PATH.read_text(), re.M)
        self.assertIsNotNone(match)
        version = match.group(1)
        self.assertIn(f'<div class="brand-version">V {version}</div>', self.html)
        self.assertIn(f'const CLIENT_VERSION = "{version}"', self.html)

    def test_shell_script_is_deferred_and_nonce_protected(self) -> None:
        """Allow first paint before application initialization."""
        self.assertIn('<style nonce="__FHT_CSP_NONCE__">', self.html)
        self.assertIn(
            '<script type="module" nonce="__FHT_CSP_NONCE__">',
            self.html,
        )
        self.assertNotRegex(self.html, r'\sstyle="')
        self.assertNotRegex(self.html, r'\sonclick="')

    def test_all_network_requests_use_the_bounded_json_gateway(self) -> None:
        """Keep timeout, error, and no-store handling centralized."""
        self.assertEqual(self.html.count("fetch("), 1)
        self.assertIn("async function requestJson(path, options = {})", self.html)
        self.assertIn("const controller = new AbortController()", self.html)
        self.assertIn('cache: "no-store"', self.html)
        self.assertIn("async function saveJson(path, payload", self.html)

    def test_startup_renders_shell_before_idle_warmups(self) -> None:
        """Warm useful caches without blocking initial navigation."""
        self.assertIn("const moduleStartedAt = performance.now()", self.html)
        self.assertIn('performance.getEntriesByType("navigation")', self.html)
        self.assertIn('runSafely(loadBrandTemperature, "initial temperature")', self.html)
        self.assertIn('runSafely(loadAppInfo, "initial app information")', self.html)
        self.assertNotIn('runWhenIdle(loadEntityInventory', self.html)
        self.assertIn('requestJson("api/menu/status")', self.html)
        self.assertIn(
            'runWhenIdle(preloadRoomConfiguratorIndex, "Home Configurator index warmup"',
            self.html,
        )
        self.assertNotIn("await preload", self.html)

    def test_live_updates_replace_one_second_full_polling(self) -> None:
        """Use revision long-polling with a conservative fallback interval."""
        self.assertIn("async function watchLiveStateRevisions()", self.html)
        self.assertIn("api/live/revision?after=", self.html)
        self.assertIn("const LIVE_STATE_FALLBACK_INTERVAL_MS = 30000", self.html)
        self.assertNotIn("setInterval(loadLighting, 1000", self.html)
        self.assertNotIn("setInterval(loadSecurity, 1000", self.html)

    def test_home_configurator_uses_small_index_and_lazy_room_payloads(self) -> None:
        """Preload floors but fetch only the room a user expands."""
        self.assertIn("async function fetchRoomConfiguratorIndex(force = false)", self.html)
        self.assertIn("if (roomConfiguratorIndex && !force)", self.html)
        self.assertIn("api/home-configurator/index", self.html)
        self.assertIn("api/home-configurator/room?room=", self.html)
        self.assertIn("const roomConfiguratorPayloads = new Map()", self.html)
        self.assertIn("async function hydrateRoomConfiguratorCard", self.html)

    def test_whole_home_house_mode_uses_compact_dial_picker(self) -> None:
        """Keep Whole Home boundaries compact and human-readable."""
        self.assertIn('class="house-mode-card"', self.html)
        self.assertIn('class="house-mode-offset-select"', self.html)
        self.assertIn('data-house-mode="${mode}"', self.html)
        self.assertIn('["day", "night"].map((mode) =>', self.html)
        self.assertIn("function houseModeOffsetOptions(mode, selected)", self.html)
        self.assertIn(
            "Array.from({ length: 13 }, (_, index) => (index - 6) * 15)",
            self.html,
        )
        self.assertIn("async function saveHouseModeOffset(select)", self.html)
        self.assertIn("house-sleep-source-select", self.html)
        self.assertIn("house-sleep-picker", self.html)
        self.assertIn("Clear Bedrooms", self.html)
        self.assertIn("select.classList.contains(\"house-sleep-source-select\")", self.html)
        self.assertIn("Bedroom Sleep Modes", self.html)
        self.assertIn("settings.sleep_mode_sources", self.html)
        self.assertIn("leftIsWholeHome ? -1 : 1", self.html)
        self.assertIn("justify-content: center", self.html)
        self.assertNotIn("house-mode-dialog", self.html)
        self.assertNotIn("house-mode-dial-chevron", self.html)
        self.assertNotIn("data-house-save", self.html)
        self.assertNotIn("Negative minutes", self.html)

    def test_floor_titles_are_larger_and_device_alarms_stays_open(self) -> None:
        """Render legacy Whole Home alarm aliases with the House Mode card."""
        self.assertIn("font-size: 19px", self.html)
        self.assertNotIn("<h3>Device Alarms</h3>", self.html)
        self.assertIn('id="alarm-device-card" aria-label="Device Sensors"', self.html)
        self.assertIn('id="alarm-device-card"', self.html)
        self.assertIn('.filter(room => ![room.name, room.display_name].some(isDeviceAlarmRoomName))', self.html)
        self.assertIn('await loadApiPayload("api/fridge-alarms")', self.html)
        self.assertIn('["bridges", "device alarms", "fridges"].includes(', self.html)
        self.assertIn("function isDeviceAlarmRoomName(name)", self.html)
        self.assertIn("(name) => isDeviceAlarmRoomName(name)", self.html)
        self.assertIn(
            '(card.open || card.matches(".whole-home-static-room-card, section.room-configurator-card"))',
            self.html,
        )
        self.assertIn(
            'class="house-mode-card room-names-card"',
            self.html,
        )

    def test_home_configurator_hides_counts_and_empty_unassigned_floor(self) -> None:
        """Keep floor navigation clean and suppress empty Unassigned."""
        self.assertNotIn('id="room-count"', self.html)
        self.assertNotIn('`${floor.rooms.length} ${floor.rooms.length === 1 ? "room" : "rooms"}`', self.html)
        self.assertIn('String(floor.name || "").trim().toLowerCase() !== "unassigned"', self.html)
        self.assertIn('|| (floor.rooms || []).length > 0', self.html)

    def test_device_alarms_offer_persistent_refrigerator_rules(self) -> None:
        """Expose flat sensor alarms with persistent audible output rules."""
        self.assertIn("function renderFridgeAlarmPanel(payload)", self.html)
        self.assertNotIn('<summary>Refrigerators</summary>', self.html)
        self.assertIn("Refrigerator Door Sensors", self.html)
        self.assertIn("Refrigerator Environmental Sensors", self.html)
        self.assertIn("Door Open Alert", self.html)
        self.assertIn("Temperature Alert", self.html)
        self.assertIn("No audible alert", self.html)
        self.assertIn('alert_behavior: "until_clear"', self.html)
        self.assertIn('data-fridge-field="alert_targets"', self.html)
        self.assertIn("fridge-alarm-output-select", self.html)
        self.assertIn("Clear Outputs", self.html)
        self.assertIn("row.querySelectorAll('[data-fridge-field=\"alert_targets\"]:checked')", self.html)
        self.assertIn('class="device-output-options"', self.html)
        self.assertIn('data-fridge-field="unifi_webhook"', self.html)
        self.assertNotIn('data-fridge-field="alert_behavior"', self.html)
        self.assertIn('saveJson("api/fridge-alarms"', self.html)
        self.assertIn(
            "if (isFridgeAlarmRoom(payload)) return renderFridgeAlarmPanel(payload);",
            self.html,
        )

    def test_pantry_uses_compact_door_actions_without_modes_or_wake(self) -> None:
        """Keep Pantry focused on door state and assigned actions."""
        self.assertIn("function isPantryRoom(payload)", self.html)
        self.assertNotIn("pantryHeaderStatus(roomPayload)", self.html)
        self.assertIn("existingStatus?.remove();", self.html)
        self.assertIn("function pantryHeaderStatus(payload)", self.html)
        self.assertNotIn('["Room Modes", !pantry', self.html)
        self.assertNotIn('["Wake Up Routine", !pantry', self.html)
        self.assertIn("Door Open", self.html)
        self.assertIn("actions assigned", self.html)
        self.assertIn('picker.classList.add("pantry-action-picker")', self.html)
        self.assertIn('["day", "night", "sleep"]', self.html)
        self.assertIn('renderPantryDoorMode(payload, door, mode)', self.html)
        self.assertIn('class="pantry-door-mode-enabled"', self.html)
        self.assertIn('class="pantry-door-brightness"', self.html)
        self.assertIn('class="pantry-door-color-button"', self.html)
        self.assertIn("function openPantryColorDialog(card)", self.html)
        self.assertIn("activePantryColorCard", self.html)
        self.assertIn('card.querySelector(".pantry-door-color-mode").value = mode', self.html)
        self.assertIn('action_setting: pantryDoorModeSetting(card)', self.html)

    def test_expanded_home_configurator_sections_render_as_complete_cards(self) -> None:
        """Join each open feature header and body into one polished card."""
        self.assertIn("details.home-configurator-feature[open] > summary", self.html)
        self.assertIn("details.home-configurator-feature[open] > .home-configurator-feature-body", self.html)
        self.assertIn("border-radius: 9px 9px 0 0", self.html)
        self.assertIn("border-radius: 0 0 9px 9px", self.html)

    def test_action_picker_renders_above_room_and_floor_cards(self) -> None:
        """Prevent the expanded multi-action menu from being covered by later cards."""
        self.assertIn(".home-configurator-floor-card[open]", self.html)
        self.assertIn(".home-configurator-floor-card:has(.action-multi-picker[open])", self.html)
        self.assertIn(".room-configurator-card:has(.action-multi-picker[open])", self.html)
        self.assertNotIn("`${name} — ${context || targetEntityId(entity)}`", self.html)

    def test_room_modes_have_their_own_settings_page(self) -> None:
        """Move the room checklist out of Home Configurator, retaining choices."""
        self.assertIn('data-view="room-modes">Room Modes</button>', self.html)
        self.assertIn('id="view-room-modes"', self.html)
        self.assertIn("function renderRoomModeCard(room, catalog, settings)", self.html)
        self.assertNotIn("function renderRoomModeSection(payload)", self.html)
        self.assertNotIn('class="home-configurator-feature room-configurator-mode-panel"', self.html)
        self.assertIn('data-room-mode="${escapeHtml(mode.id)}"', self.html)
        self.assertIn("saveRoomModes(button.closest", self.html)

    def test_alarm_settings_page_has_navigation_and_isolated_saving(self) -> None:
        self.assertIn('data-view="alarm">Alarm</button>', self.html)
        self.assertIn('id="view-alarm"', self.html)
        self.assertIn('if (view === "alarm") return loadAlarmModes', self.html)
        self.assertIn('alarmView.hidden = view !== "alarm"', self.html)
        self.assertIn('mode: checkbox.dataset.alarmMode', self.html)
        self.assertIn('#view-alarm .room-mode-card,', self.html)
        menu = self.html.split('id="settings-submenu" hidden>', 1)[1].split('</div>', 1)[0]
        self.assertLess(menu.index('data-view="alarm"'), menu.index('data-view="buttons"'))
        self.assertIn('id="alarm-door-card" aria-label="Door Sensors"', self.html)
        self.assertIn('refreshes.push(refreshAlarmDoorStates())', self.html)

    def test_alarm_layout_stacks_modes_and_aligns_sensor_status(self) -> None:
        self.assertNotIn('#alarm-door-card {\n        background: transparent;', self.html)
        self.assertIn('#view-alarm .alarm-sensor-option:has(input:checked) {\n        background: transparent;', self.html)
        self.assertNotIn('#view-alarm .room-mode-option:has(input:checked),', self.html)
        self.assertIn('#alarm-mode-list { grid-template-columns: minmax(0, 1fr); }', self.html)
        self.assertIn('grid-template-columns: 18px 84px minmax(0, 1fr)', self.html)
        self.assertIn('width: 84px; height: 26px', self.html)
        self.assertIn('.alarm-sensor-options { grid-template-columns: minmax(0, 1fr); padding: 3px 0; }', self.html)

    def test_lighting_packs_natural_height_cards_without_sensor_requests(self) -> None:
        self.assertIn('.lighting-area-grid.is-masonry', self.html)
        self.assertIn('grid-auto-rows: 1px', self.html)
        self.assertIn('new ResizeObserver(() => scheduleLightingLayout())', self.html)
        self.assertIn('lightingLayoutObserver?.disconnect()', self.html)
        self.assertIn('if (view === "lighting") scheduleLightingLayout()', self.html)

    def test_room_mode_autosave_has_no_routine_footer(self) -> None:
        renderer = self.html.split('function renderRoomModeCard(', 1)[1].split('function renderAlarmModeCards(', 1)[0]
        self.assertNotIn('room-mode-card-footer', renderer)
        self.assertNotIn('enabled ·', renderer)
        self.assertIn('room-mode-save-error', renderer)
        self.assertIn('role="alert" hidden', renderer)

    def test_room_mode_cards_match_house_mode_glass(self) -> None:
        card_style = self.html.split("#view-room-modes .room-mode-card {", 1)[1].split("}", 1)[0]
        self.assertIn("border-color: rgb(94 192 255 / 42%)", card_style)
        self.assertIn("border-left-color: #35aef7", card_style)
        self.assertIn("background: rgb(4 13 23 / 40%)", card_style)
        self.assertIn("#view-room-modes .room-mode-option:has(input:checked)", self.html)

    def test_room_mode_badge_is_hidden_until_an_enabled_mode_is_active(self) -> None:
        """Never render or restore a Not Set room-mode badge."""
        self.assertNotIn('room.current_mode || "Not Set"', self.html)
        self.assertNotIn('roomPayload.current_mode || "Not Set"', self.html)
        self.assertNotIn('room.current_mode ? `<span class="room-current-mode">', self.html)
        self.assertIn("mode.remove();", self.html)

    def test_new_wake_actions_reuse_the_selected_rooms_catalog(self) -> None:
        """Populate newly added wake blocks without another inventory request."""
        self.assertIn("const wakeRoutineCatalogs = new Map()", self.html)
        self.assertNotIn("wakeRoutineCatalogs.set(room, wakeCatalog)", self.html)
        self.assertIn(
            "wakeRoutineCatalogs.get(panel.dataset.area) || {}",
            self.html,
        )

    def test_background_room_refresh_preserves_open_sections_and_drafts(self) -> None:
        """Do not collapse an editor while live state arrives."""
        self.assertIn("const interactionRevision = roomInteractionRevisions.get(card)", self.html)
        self.assertIn('card.dataset.userDirty !== "true"', self.html)
        self.assertIn("openSections.has(summary.textContent.trim())", self.html)
        self.assertIn("background: true", self.html)
        self.assertIn("replaceBody: false", self.html)

    def test_failed_view_loads_remain_retryable(self) -> None:
        """Do not mark a settings view loaded after its renderer reports failure."""
        self.assertIn("loadedViews.delete(view)", self.html)
        self.assertIn('state: previousState?.lastGoodAt ? "stale" : "error"', self.html)
        for function_name, next_function in (
            ("loadScenes", "roomModeType"),
            ("loadRoomModes", "saveRoomModes"),
            ("loadClimateSettings", "saveClimateAction"),
            ("loadUnifiResources", "formatProtectTimestamp"),
        ):
            start = self.html.index(f"async function {function_name}")
            end = self.html.index(f"function {next_function}", start)
            self.assertIn("throw error;", self.html[start:end])

    def test_room_features_are_alphabetical_and_progressively_disclosed(self) -> None:
        """Keep each room compact and arrange supported editors consistently."""
        body_start = self.html.index("function buildRoomConfiguratorBody")
        body_end = self.html.index("async function hydrateRoomConfiguratorCard", body_start)
        body = self.html[body_start:body_end]
        self.assertNotIn("renderWakeRoutinePanel", body)
        self.assertNotIn('"Room Modes"', body)
        self.assertNotIn('"Door Actions"', body)
        self.assertNotIn('"Switches"', body)
        for title in ("Buttons", "Door Actions", "Presence", "Switches"):
            self.assertIn(f"<summary>{title}</summary>", self.html)

    def test_switch_page_expands_all_areas_with_bounded_initial_loading(self) -> None:
        start = self.html.index("async function loadRoomControlsPage")
        end = self.html.index("function roomControlRequestPath", start)
        body = self.html[start:end]
        self.assertIn('["switches", "presence", "doors"].includes(kind) ? `<section class="switches-area"', body)
        self.assertIn('class="switches-area-heading"', body)
        self.assertIn("Math.min(3, pending.length)", body)
        self.assertIn("await hydrateRoomControlsCard(card, inventory.rooms_ready", body)
        self.assertIn('#switches-list .room-controls-body { grid-template-columns: repeat(2, minmax(0, 1fr))', self.html)
        self.assertIn('#switches-list .room-controls-body { grid-template-columns: minmax(0, 1fr); }', self.html)

    def test_door_and_switch_pages_use_scoped_room_editors(self) -> None:
        for view in ("doors", "switches"):
            self.assertIn(f'data-view="{view}"', self.menu)
            self.assertIn(f'id="view-{view}"', self.html)
            self.assertIn(f'id="{view}-toolbar"', self.html)
        self.assertIn("api/room-controls?kind=${kind}", self.html)
        self.assertIn("&room=${encodeURIComponent(card.dataset.controlRoom)}", self.html)
        self.assertIn("hydrateRoomControlsCard(event.target)", self.html)
        self.assertIn(".prepend(document.getElementById(`${kind}-toolbar`))", self.html)
        start = self.html.index("async function refreshRoomControlStates")
        end = self.html.index('for (const kind of ["doors", "switches"])', start)
        refresh = self.html[start:end]
        self.assertNotIn("body.innerHTML", refresh)
        self.assertNotIn("attachEditorCatalog", refresh)
        self.assertIn("button.disabled", refresh)

    def test_switches_require_a_switch_domain_and_device_name(self) -> None:
        """Exclude fan wrappers, cameras, and doorbells from Switches."""
        self.assertIn('if (entity.domain !== "switch") return false', self.html)
        self.assertIn('String(entity.device_name || "").trim()', self.html)
        self.assertIn('/\\bswitch\\b/i.test(searchableName)', self.html)
        self.assertIn('!/\\b(camera|doorbell)\\b/i.test(searchableName)', self.html)
        self.assertIn('return /\\bswitch\\b/i.test(String(entity.device_name || "").trim())', self.html)
        self.assertIn('isActualSwitchControl(entity) || isInovelliEventControl(entity)', self.html)

    def test_action_picker_supports_multiple_visible_targets_and_clear(self) -> None:
        """Show saved choices at a glance and persist multiple stable IDs."""
        self.assertIn("<select multiple", self.html)
        self.assertIn('picker.className = "action-multi-picker"', self.html)
        self.assertIn('clearButton.textContent = "Clear Actions"', self.html)
        self.assertIn('menuFooter.className = "action-multi-menu-footer"', self.html)
        self.assertIn("menuFooter.append(clearButton)", self.html)
        self.assertIn("actionMultiSelectSummary(select)", self.html)
        self.assertIn("actionMultiSelectIds(select)", self.html)
        self.assertIn("const uniqueValues = [...new Set(values)]", self.html)
        self.assertIn('setting: "actions"', self.html)

    def test_room_buttons_group_four_gestures_per_button_card(self) -> None:
        """Avoid repeating the device name on every button gesture row."""
        start = self.html.index("function renderRoomButtonsSection")
        end = self.html.index("function renderPresenceCatalogOptions", start)
        buttons = self.html[start:end]
        self.assertIn('class="button-control-card"', buttons)
        self.assertIn('class="button-control-title"', buttons)
        self.assertIn('class="button-action-row"', buttons)
        self.assertIn("roomButtonLabel(button, trigger)", buttons)
        for label in ("Single Press", "Double Press", "Long Press", "Long Release"):
            self.assertIn(label, self.html)
        self.assertNotIn("`${buttonLabel}, ${gestureLabel}`", buttons)

    def test_action_catalog_orders_groups_first_and_numbered_lights_last(self) -> None:
        """Keep room-first groups above other actions and numbered lights last."""
        start = self.html.index("function renderActionCatalogOptions")
        end = self.html.index("function renderActionCatalogSelect", start)
        options = self.html[start:end]
        self.assertLess(
            options.index('Light Groups">'),
            options.index('Fans &amp; Plugs'),
        )
        self.assertLess(
            options.index('<optgroup label="Wake Overrides">'),
            options.index('<optgroup label="Individual Lights">'),
        )
        self.assertIn("roomFirstActionTargets", options)
        self.assertIn("Other Rooms · Light Groups", options)
        self.assertIn("actionCatalogOptionMarkup", options)
        self.assertIn("Unavailable Saved Targets", options)

    def test_action_picker_uses_wide_scannable_rows(self) -> None:
        """Render room-prioritized targets as polished, readable menu rows."""
        self.assertIn("width: min(500px, calc(100vw - 32px))", self.html)
        self.assertIn('copy.className = "action-multi-option-copy"', self.html)
        self.assertIn('text.className = "action-multi-option-name"', self.html)
        self.assertIn('context.className = "action-multi-option-context"', self.html)
        self.assertIn('"is-selected"', self.html)
        self.assertIn("function actionTargetBelongsToRoom", self.html)

    def test_lighting_uses_live_projection_and_optimistic_controls(self) -> None:
        """Render fast room cards and show immediate action feedback."""
        self.assertIn('requestJson("api/lighting/status"', self.html)
        self.assertIn('if (payload.stale)', self.html)
        self.assertIn("const lightingPendingActions = new Map()", self.html)
        self.assertIn('class="lighting-control-card is-${statusClass}', self.html)
        self.assertIn("lighting-name-toggle", self.html)
        self.assertIn("lighting-brightness-button", self.html)
        self.assertIn("lighting-item-range", self.html)

    def test_lighting_removes_sensor_rows_and_retains_border_states(self) -> None:
        """Keep lighting controls but omit room sensor header work."""
        self.assertIn("border-left: 4px solid #fff", self.html)
        self.assertIn("border-left-color: #35aef7", self.html)
        self.assertIn("border-left-color: var(--danger)", self.html)
        self.assertNotIn("lighting-room-status-row", self.html)
        self.assertNotIn("lighting-opening-bubble", self.html)
        self.assertNotIn("lighting-lux-bubble", self.html)
        self.assertNotIn("lightingRoomStatus", self.html)

    def test_security_and_exterior_door_truth_fail_closed(self) -> None:
        """Reject stale safety data instead of leaving a false green state."""
        self.assertIn('requestJson("api/security/status"', self.html)
        self.assertIn('throw new Error(payload.last_error || "Door sensor status is stale.")', self.html)
        self.assertIn("markExteriorDoorStatusUnavailable()", self.html)
        self.assertIn("security-door-card", self.html)
        self.assertIn("is-unavailable", self.html)

    def test_battery_inventory_is_cached_sorted_and_editable(self) -> None:
        """Load one projected inventory and expose missing battery types."""
        self.assertIn('requestJson("api/batteries"', self.html)
        self.assertIn(".sort((left, right) => left.percentage - right.percentage)", self.html)
        self.assertIn("batteryInventoryPromise", self.html)
        self.assertIn('class="battery-type-select"', self.html)
        self.assertIn('saveJson("api/battery-types"', self.html)

    def test_only_settings_pages_show_manual_refresh_buttons(self) -> None:
        """Keep refresh buttons page-local and off dashboard screens."""
        for view in ("homekit", "climate-settings", "scenes", "rooms", "unifi"):
            self.assertIn(f'data-page-refresh="{view}"', self.html)
        for view in ("home", "lighting", "security"):
            self.assertNotIn(f'data-page-refresh="{view}"', self.html)
        self.assertIn("settingsViews.has(activeView)", self.html)
        self.assertIn('button.querySelector(".refresh-label").textContent = "Updated"', self.html)

    def test_background_is_fingerprinted_webp(self) -> None:
        """Use the optimized immutable visual asset."""
        self.assertIn('url("fht-infinite-vertical-warp-4da39efb.webp")', self.html)
        self.assertNotIn('url("fht-infinite-vertical-warp.png")', self.html)
        self.assertTrue(
            (WEB_ROOT / "fht-infinite-vertical-warp-4da39efb.webp").is_file()
        )
        for retired_asset in (
            "fht-groups-data-lanes.png",
            "fht-groups-hyperlane.png",
            "fht-infinite-vertical-warp.png",
        ):
            self.assertFalse((WEB_ROOT / retired_asset).exists())

    def test_ingress_kiosk_and_exit_behavior_remain_available(self) -> None:
        """Preserve the embedded Home Assistant navigation behavior."""
        self.assertIn("function enterKioskMode()", self.html)
        self.assertIn('id="exit-app"', self.html)
        self.assertIn('HOME_ASSISTANT_SETTINGS_PATH = "/config"', self.html)
        self.assertIn("window.top.location.assign(settingsUrl.href)", self.html)


if __name__ == "__main__":
    unittest.main()
