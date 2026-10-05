const assert = require("node:assert/strict");
const { chromium } = require(process.env.FHT_PLAYWRIGHT || "playwright");

async function main() {
  const browser = await chromium.launch({ headless: true });
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    const page = await context.newPage();
    let savedAppColor = 'blue';
    await page.route('**/api/app-color', async route => {
      if (route.request().method() === 'POST') savedAppColor = route.request().postDataJSON().color;
      await route.fulfill({json: {ok: true, color: savedAppColor}});
    });
    if (process.env.FHT_TEST_POPOVER_FALLBACK) await page.addInitScript(() => { delete HTMLElement.prototype.showPopover; });
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    const entities = ["Bedroom 6", "Kitchen", "Laundry", "Office"].flatMap((area, index) => [1, 2].map(device => ({ entity_id: `switch.room_${index}_${device}`, domain: "switch", device_id: `device_${index}_${device}`, device_name: `${area} Switch ${device}`, friendly_name: `${area} Switch ${device} Button 1`, state: "off", area, original_area: area })));
    entities[0].wired_load_ids = ["light.closet"];
    entities[0].wired_load_names = {"light.closet": "Closet Light"};
    const savedActions = [];
    entities[1].wired_load_names = {"fan.exhaust": "Exhaust Fan"};
    const savedTimers = [];
    const savedDoorCards = [];
    const savedHumidity = [];
    await page.route("**/api/switch-light-groups", async route => {
      if (route.request().postDataJSON().setting === "exhaust_timer") savedTimers.push(route.request().postDataJSON());
      if (route.request().postDataJSON().setting === "exhaust_humidity") {
        savedHumidity.push(route.request().postDataJSON());
        if (route.request().postDataJSON().stop_below === 70) return route.fulfill({status: 400, json: {ok: false, error: "Stop below must be lower than Start above."}});
      }
      if (route.request().postDataJSON().door_modes) savedDoorCards.push(route.request().postDataJSON());
      savedActions.push(route.request().postDataJSON().actions);
      await route.fulfill({json: {ok: true}});
    });
    const humiditySensors = [{entity_id: "sensor.bedroom_6_humidity", friendly_name: "Bedroom 6 Humidity", state: "71.4", room: "Bedroom 6"}, {entity_id: "sensor.kitchen_humidity", friendly_name: "Kitchen Humidity", state: "40", room: "Kitchen"}];
    entities.push({ entity_id: "event.kitchen_switch_button_up", domain: "event", device_id: "inovelli", device_name: "Kitchen Inovelli Switch", friendly_name: "Kitchen Switch Up", event_types: ["multi_press_1", "multi_press_2"], state: "unknown", area: "Kitchen" });
    let inflight = 0;
    let peak = 0;
    const loaded = new Set();
    await page.route("**/api/room-controls?*", async route => {
      const room = new URL(route.request().url()).searchParams.get("room");
      if (room === null) await new Promise(resolve => setTimeout(resolve, 500));
      if (room !== null) {
        inflight += 1;
        peak = Math.max(peak, inflight);
        await new Promise(resolve => setTimeout(resolve, 100));
        loaded.add(room);
        inflight -= 1;
      }
      await route.fulfill({ json: { ok: true, rooms_ready: true, room, display_name: room === "Bedroom 6" ? "Chloe's Bedroom" : room, aliases: { "Bedroom 6": "Chloe's Bedroom" }, entities: entities.filter(entity => room === null || entity.area === room).map(entity => entity.area === "Bedroom 6" ? {...entity, original_area: "Bedroom 6", area: "Chloe's Bedroom"} : entity), humidity_sensors: humiditySensors, assignments: {}, catalog_revision: 1 } });
    });
    await page.route("**/api/home-configurator/catalog", route => route.fulfill({ json: { ok: true, revision: 1, action_catalog: { light_groups: [{entity_id: "light.closet", friendly_name: "Closet Light", area: "Bedroom 6"}, {entity_id: "light.vanity", friendly_name: "Chloe's Bedroom Bathroom Vanity Light", area: "Bedroom 6"}], lights: [], loads: [], room_modes: [{area: "Bedroom 6", entity_id: "input_select.fht_bedroom_6_mode", options: ["Sleep", "Movie"]}] } } }));
    await page.route('**/api/home-configurator/index*', route => route.fulfill({json: {ok: true, room_count: 2, house_mode: 'Day', sleep_mode_options: [{entity_id: 'input_select.fht_bedroom_6_mode', label: "Chloe's Bedroom", floor_id: 'first'}, {entity_id: 'input_select.fht_bedroom_2_mode', label: "Bailey's Bedroom", floor_id: 'second'}], floors: [{name: 'Whole Home', rooms: []}, {floor_id: 'first', name: 'First Floor', rooms: [{name: 'Bedroom 6', display_name: "Chloe's Bedroom"}]}, {floor_id: 'second', name: 'Second Floor', rooms: [{name: 'Bedroom 2', display_name: "Bailey's Bedroom"}]}]}}));
    await page.route('**/api/home-configurator/room?*', route => {
      const room = new URL(route.request().url()).searchParams.get('room');
      return route.fulfill({json: {ok: true, room, entities: [], alias: room, wake_routine: {}}});
    });
    await page.goto(process.env.FHT_SWITCHES_URL, { waitUntil: "domcontentloaded" });
    await page.locator("#settings-toggle").click();
    await page.locator('[data-view="switches"]').click();
    await page.locator("#switches-load-progress").waitFor({state: "visible"});
    assert.equal(await page.locator("#switches-load-progress").evaluate(element => getComputedStyle(element).accentColor), "rgb(255, 255, 255)");
    assert.equal(await page.locator("#switches-load-progress").evaluate(element => getComputedStyle(element).appearance), "none");
    assert.equal(await page.locator("#switches-load-progress").evaluate(element => element.hasAttribute("value")), false);
    await page.waitForFunction(() => document.querySelectorAll('#switches-list [data-ready="true"]').length === 4);
    await page.locator("#switches-load-progress").waitFor({state: "hidden"});
    assert.equal(await page.locator("#switches-load-progress").getAttribute("max"), "4");
    assert.equal(await page.locator("#switches-load-progress").getAttribute("value"), "4");
    assert(!(await page.locator("#switches-list").innerText()).includes("Loading actions"));
    const list = page.locator("#switches-list");
    assert.equal(await page.locator("#switches-toolbar").isVisible(), false);
    assert.equal(await page.locator("#exit-app").isVisible(), true);
    assert.equal(await page.locator(".page-actions").evaluate(element => getComputedStyle(element).backgroundColor), "rgba(0, 0, 0, 0)");
    assert.equal(await page.locator("#exit-app").evaluate(element => getComputedStyle(element).backgroundColor), "rgba(0, 0, 0, 0)");
    assert.equal(await list.locator("details[data-control-room]").count(), 0);
    assert.equal(await list.locator(".control-device-card").count(), 8);
    assert.equal(await list.locator(".control-status-button").count(), 0);
    async function assertCompactRows() {
      const row = list.locator(".control-channel-row").first();
      assert.equal(await row.evaluate(element => getComputedStyle(element).borderTopWidth), "0px");
      const label = await row.locator(".control-channel-name").boundingBox();
      const picker = await row.locator(".action-multi-picker").boundingBox();
      assert(picker.x > label.x && Math.abs((label.y + label.height / 2) - (picker.y + picker.height / 2)) < 2, "Label and dropdown share one row");
      assert.equal(await row.locator(".action-multi-summary-id").isVisible(), false);
    }
    await assertCompactRows();
    assert.equal(await list.locator(".inovelli-controller").count(), 1);
    assert.equal(await list.locator(".inovelli-controller .gesture-assignment").count(), 2);
    assert.equal(loaded.size, 0, "Switches reuse the initial snapshot without per-room requests");
    assert(peak <= 3, "Room requests stay bounded");
    assert.deepEqual(await list.locator(".switches-area-heading").allTextContents(), ["Chloe's Bedroom", "Kitchen", "Laundry", "Office"]);
    const cards = list.locator(".switches-area").first().locator(".control-device-card");
    const first = await cards.nth(0).boundingBox();
    const second = await cards.nth(1).boundingBox();
    assert(Math.abs(first.y - second.y) < 2 && second.x > first.x, "Two device columns on desktop");
    assert.equal(await list.locator(".switches-area-heading").first().evaluate(element => getComputedStyle(element).textAlign), "center");
    assert.equal(await page.locator('#switches-toolbar [data-page-refresh]').count(), 0);
    assert.equal(await list.locator(".switches-area-heading").first().evaluate(element => getComputedStyle(element).marginTop), "3px");
    assert.equal(await list.locator(".switches-area-heading").first().evaluate(element => getComputedStyle(element).paddingTop), "2px");
    assert.equal(await list.evaluate(element => getComputedStyle(element).gap), "8px");
    assert.equal(await list.locator(".room-controls-body").first().evaluate(element => getComputedStyle(element).paddingTop), "6px");
    assert.equal(await list.locator(".switches-area-heading").first().evaluate(element => getComputedStyle(element).backgroundColor), "rgba(0, 0, 0, 0)");
    for (const selector of [".control-device-card", ".inovelli-controller"]) {
      assert.equal(await list.locator(selector).first().evaluate(element => getComputedStyle(element).backgroundColor), "rgba(4, 13, 23, 0.25)");
      assert.equal(await list.locator(selector).first().evaluate(element => getComputedStyle(element).backdropFilter), "blur(3px)");
    }
    await list.locator(".action-multi-picker summary").first().click();
    const menu = list.locator(".action-multi-menu").first();
    await menu.waitFor({ state: "visible" });
    assert.equal(await menu.getByText("Closet Light · Wired load", {exact: true}).count(), 1);
    assert.equal(await menu.locator('input[value="light_group:light.closet"]').count(), 0);
    await menu.locator('input[value="light_group:light.vanity"]').check();
    assert.equal(savedActions.length, 0, "Checkbox edits remain local until the picker closes");
    await list.locator(".action-multi-picker summary").first().click();
    await page.waitForFunction(() => !document.querySelector('#switches-list select[data-assignment-id="switch.room_0_1"]').disabled);
    assert.deepEqual(savedActions.at(-1), ["light_group:light.vanity"]);
    assert.equal(await page.locator('#switches-list .exhaust-timer-select, #switches-list .exhaust-humidity-field').count(), 0, "Exhaust controls live on the Environment page now");
    assert.equal(await list.locator(".action-multi-summary-text").first().textContent(), "Closet Light, Bathroom Vanity Light", "The collapsed summary drops the room name the card already shows");
    await list.locator(".action-multi-picker summary").first().click();
    await menu.getByRole("button", {name: "Clear Actions", exact: true}).click();
    await list.locator(".action-multi-picker summary").first().click();
    await page.waitForFunction(() => !document.querySelector('#switches-list select[data-assignment-id="switch.room_0_1"]').disabled);
    assert.deepEqual(savedActions.at(-1), []);
    await list.locator(".action-multi-picker summary").first().click();
    await menu.waitFor({ state: "visible" });
    assert.equal(await list.locator(".action-multi-summary-text").first().textContent(), "Closet Light");
    assert.equal(await menu.getByText("No action / clear all", {exact: true}).count(), 0);
    assert.equal(await menu.getByRole("button", {name: "Clear Actions", exact: true}).count(), 1);
    assert.equal(await menu.locator(".action-multi-group-title").first().textContent(), "Chloe's Bedroom");
    assert.equal(await menu.getByText("Sleep Mode", {exact: true}).count(), 1);
    assert.equal(await menu.getByText("Movie Mode", {exact: true}).count(), 1);
    if (!process.env.FHT_TEST_POPOVER_FALLBACK) {
      await list.locator(".action-multi-picker summary").first().click();
      await menu.waitFor({ state: "hidden" });
      await page.waitForTimeout(100);
      assert.equal(await menu.isVisible(), false);
      await list.locator(".action-multi-picker summary").first().click();
      await menu.waitFor({ state: "visible" });
    }
    await menu.evaluate(element => {
      for (let index = 0; index < 15; index += 1) {
        const option = document.createElement("p");
        option.textContent = `Fixture light group ${index + 1}`;
        element.append(option);
      }
    });
    await page.setViewportSize({ width: 640, height: 894 });
    await page.waitForTimeout(100);
    assert.equal(await menu.evaluate(element => element.matches(":popover-open") || (element.tagName === "DIALOG" && element.open)), true);
    // The menu repositions after the resize settles, so wait for it rather than a fixed delay.
    const menuPlaced = await menu.evaluate(element => new Promise(resolve => {
      const deadline = performance.now() + 3000;
      const check = () => {
        const bounds = element.getBoundingClientRect();
        const sidebar = document.querySelector(".topbar").getBoundingClientRect();
        const placed = bounds.left >= sidebar.right && bounds.right <= innerWidth
          && element.contains(document.elementFromPoint(bounds.left + 15, bounds.bottom - 25));
        if (placed || performance.now() > deadline) resolve(placed);
        else requestAnimationFrame(check);
      };
      check();
    }));
    assert.equal(menuPlaced, true, "Menu stays out of the sidebar and above overlapping glass devices on iPad split view");
    await page.screenshot({ path: "/tmp/fht-switches-0.5.39-ipad.png" });
    await page.keyboard.press("Escape");
    await menu.waitFor({ state: "hidden" });
    await list.locator(".action-multi-picker summary").first().click();
    await menu.waitFor({ state: "visible" });
    await page.setViewportSize({ width: 390, height: 844 });
    await assertCompactRows();
    const mobileFirst = await cards.nth(0).boundingBox();
    const mobileSecond = await cards.nth(1).boundingBox();
    assert(mobileSecond.y > mobileFirst.y && Math.abs(mobileSecond.x - mobileFirst.x) < 2, "One device column on mobile");
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true);
    await page.keyboard.press("Escape");
    await menu.waitFor({ state: "hidden" });
    await list.locator(".action-multi-picker summary").first().click();
    await menu.waitFor({ state: "visible" });
    await page.screenshot({ path: "/tmp/fht-switches-0.5.39-mobile.png" });
    await page.keyboard.press("Escape");
    const navigationToggle = page.locator("#mobile-nav-toggle");
    assert.equal(await page.locator("#app-navigation").evaluate(element => element.inert), true);
    await navigationToggle.click();
    assert.equal(await navigationToggle.getAttribute("aria-expanded"), "true");
    assert.equal(await page.locator('.topbar .brand > img').isVisible(), false);
    assert.equal(await navigationToggle.isVisible(), true);
    assert.equal(await page.locator('#mobile-nav-backdrop').evaluate(element => getComputedStyle(element).top), '0px');
    assert.deepEqual(await page.locator('#settings-submenu [data-view]').evaluateAll(elements => elements.map(element => element.textContent.trim())), ['Room Devices', 'Home Configurator', 'Portal Configurator', 'Doors', 'Switches', 'Environmental', 'Presence', 'Alarm', 'Buttons', 'Climate', 'Room Modes', 'Safe Cleanup', 'Scenes', 'Unifi', 'Users', 'Voice Control']);
    assert.equal(await page.locator('.topbar').evaluate(element => getComputedStyle(element).borderRightWidth), '0px');
    await page.waitForTimeout(200);
    await page.screenshot({path: '/tmp/fht-592-menu-glass.png'});
    await page.waitForTimeout(220);
    await page.screenshot({ path: "/tmp/fht-navigation-0.5.44-open.png" });
    await page.locator('[data-view="switches"]').click();
    assert.equal(await navigationToggle.getAttribute("aria-expanded"), "false");
    await navigationToggle.click();
    await navigationToggle.click();
    assert.equal(await navigationToggle.getAttribute("aria-expanded"), "false");
    await navigationToggle.click();
    await page.keyboard.press("Escape");
    assert.equal(await navigationToggle.getAttribute("aria-expanded"), "false");
    await page.waitForTimeout(220);
    await page.screenshot({ path: "/tmp/fht-navigation-0.5.44-closed.png" });
    await page.setViewportSize({width: 1280, height: 900});
    await page.waitForFunction(() => !document.getElementById("app-navigation").inert);
    assert.equal(await page.locator("#app-navigation").evaluate(element => element.inert), false);
    assert.equal(await navigationToggle.isVisible(), false);
    let presenceSave;
    let presenceSaveCount = 0;
    await page.route("**/api/presence-light-groups", async route => {
      presenceSave = route.request().postDataJSON();
      presenceSaveCount += 1;
      await route.fulfill({json: {ok: true}});
    });
    let presenceRoomRequests = 0;
    await page.route("**/api/room-controls?kind=presence*", async route => {
      const room = new URL(route.request().url()).searchParams.get("room");
      if (room === null) await new Promise(resolve => setTimeout(resolve, 500)); else presenceRoomRequests += 1;
      await route.fulfill({json: {ok: true, rooms_ready: true, room, enabled_room_modes: ['chill'], enabled_room_modes_by_room: {"Bedroom 6": ['chill']}, display_name: "Chloe's Bedroom", aliases: {"Bedroom 6": "Chloe's Bedroom"}, catalog_revision: 1,
        entities: [{entity_id: "binary_sensor.bedroom_6_presence", domain: "binary_sensor", device_class: "occupancy", area: "Bedroom 6", friendly_name: "Bedroom 6 Presence Occupancy (2)", state: "off"}, {entity_id: "binary_sensor.fht_bedroom_6_group_presence", domain: "binary_sensor", device_class: "occupancy", area: "Bedroom 6", friendly_name: "FHT - Bedroom 6 Group Presence"}],
        presence: {assignments: {"binary_sensor.bedroom_6_presence": ["light.closet"]}, timings: {}, mode_settings: {}}}});
    });
    await page.locator('[data-view="presence"]').click();
    await page.locator('#presence-load-progress').waitFor({state: 'visible'});
    assert.equal(await page.locator('#presence-load-progress').evaluate(element => getComputedStyle(element).accentColor), 'rgb(255, 255, 255)');
    assert.equal(await page.locator('#presence-toolbar').isVisible(), false);
    assert.equal(await page.locator('main').evaluate(element => getComputedStyle(element).paddingTop), '44px');
    assert.equal(await page.locator('#open-updates').isVisible(), true);
    assert.equal(await page.locator('#exit-app').isVisible(), true);
    assert.equal(await page.locator('#view-presence > h1').count(), 0);
    const presence = page.locator('#presence-list [data-presence-card="binary_sensor.bedroom_6_presence"]');
    await presence.waitFor({timeout: 5000}).catch(async error => { console.error(await page.locator('#view-presence').innerText(), errors); throw error; });
    await page.locator('#presence-load-progress').waitFor({state: 'hidden'});
    assert.equal(presenceRoomRequests, 0, 'Presence renders every room from one snapshot without per-room requests');
    assert.equal(await page.locator('#presence-list [data-presence-card]').first().getAttribute('data-presence-card'), 'binary_sensor.fht_bedroom_6_group_presence');
    assert.equal(await page.locator('#presence-list .is-presence-group').evaluate(element => getComputedStyle(element).gridColumn), '1 / -1');
    assert.equal(await presence.locator('.presence-card-heading').innerText(), 'Presence');
    assert.equal(await presence.locator('.action-multi-summary-id').first().isVisible(), false);
    assert.equal(await presence.locator('.group-status').count(), 0);
    assert.equal(await presence.locator('.presence-mode-enabled[data-presence-mode="chill"]').count(), 1);
    assert.equal(await presence.locator('option[value^="room_mode:"]').count(), 0);
    assert.equal(await page.locator('#presence-list .switches-area-heading').innerText(), "Chloe's Bedroom");
    await presence.locator('.action-multi-summary').first().click();
    const presenceMenu = presence.locator('.action-multi-menu').first();
    await presenceMenu.waitFor({state: 'visible'});
    assert.equal(await presenceMenu.evaluate(element => element.matches(':popover-open') || (element.tagName === 'DIALOG' && element.open)), true);
    assert.equal(await presenceMenu.evaluate(element => {
      const bounds = element.getBoundingClientRect();
      return element.contains(document.elementFromPoint(bounds.left + 15, bounds.top + 20));
    }), true, 'Presence menu is hit-testable above its glass card');
    if (!process.env.FHT_TEST_POPOVER_FALLBACK) {
      await presence.locator('.action-multi-summary').first().click();
    } else await page.keyboard.press('Escape');
    await presenceMenu.waitFor({state: 'hidden'});
    // Delays are minute dropdowns, saved in seconds.
    await presence.locator('.activation-delay-input').selectOption('7');
    await page.waitForFunction(() => document.getElementById('presence-state').textContent === 'Presence assignment saved.');
    assert.equal(Number(presenceSave.activation_delay), 420);
    assert.equal(presenceSave.presence_entity_id, 'binary_sensor.bedroom_6_presence');
    assert.deepEqual(presenceSave.target_entity_ids, ['light.closet']);
    assert.deepEqual(presenceSave.mode_settings.chill, {enabled: false, brightness: 100, color_mode: 'current', color_kelvin: 4000});
    assert.equal(await presence.locator('.presence-mode-rules').isVisible(), true);
    await presence.locator('.presence-group-select').selectOption([], {force: true});
    await presence.locator('.presence-mode-rules').waitFor({state: 'hidden'});
    assert.equal(await presence.locator('.activation-delay-input').isVisible(), false);
    assert.equal(await presence.locator('.clear-delay-input').isVisible(), false);
    await page.waitForFunction(() => !document.querySelector('#presence-list .presence-group-select').disabled);
    assert.deepEqual(presenceSave.target_entity_ids, []);
    assert.deepEqual(presenceSave.mode_settings.chill, {enabled: false, brightness: 100, color_mode: 'current', color_kelvin: 4000});
    await presence.locator('.presence-group-select').selectOption(['light.closet'], {force: true});
    await presence.locator('.presence-mode-rules').waitFor({state: 'visible'});
    assert.equal(await presence.locator('.activation-delay-input').isVisible(), true);
    assert.equal(await presence.locator('.clear-delay-input').isVisible(), true);
    assert.equal(await presence.locator('.activation-delay-input').inputValue(), '7');
    // Picking actions on a sensor that had none turns every mode on at 100%.
    await page.waitForFunction(() => !document.querySelector('#presence-list .presence-group-select').disabled);
    assert.deepEqual(presenceSave.target_entity_ids, ['light.closet']);
    assert.ok(Object.keys(presenceSave.mode_settings).length > 0);
    assert.ok(Object.values(presenceSave.mode_settings).every(setting => setting.enabled && setting.brightness === 100), 'New actions default every mode on at 100%');
    assert.ok(await presence.locator('.presence-mode-enabled').evaluateAll(toggles => toggles.every(toggle => toggle.checked)));
    assert.ok(await presence.locator('.presence-mode-output').evaluateAll(outputs => outputs.every(output => output.textContent === '100%')));
    // Color tone per mode: every rule starts at Current, presets save as Kelvin,
    // Adaptive follows the daylight and Custom… opens the tone dialog.
    async function waitForPresenceSave(previousCount) {
      for (let attempt = 0; attempt < 100 && presenceSaveCount === previousCount; attempt += 1) await page.waitForTimeout(50);
      assert.ok(presenceSaveCount > previousCount, 'Presence save sent');
      await page.waitForFunction(() => ![...document.querySelectorAll('#presence-list .presence-mode-tone')].some(select => select.disabled));
    }
    const toneSelects = presence.locator('.presence-mode-tone');
    assert.equal(await toneSelects.count(), 4);
    assert.deepEqual(await toneSelects.evaluateAll(selects => selects.map(select => select.value)), ['current', 'current', 'current', 'current']);
    const nightTone = presence.locator('.presence-mode-tone[aria-label="Night color tone"]');
    const nightRule = presence.locator('.presence-mode-rule', {has: page.locator('.presence-mode-tone[aria-label="Night color tone"]')});
    assert.deepEqual(await nightTone.locator('option').allTextContents(), ['Current', 'Warm', 'Neutral', 'Cool', 'Adaptive', 'Custom…']);
    const wideRule = await nightRule.boundingBox();
    const wideTone = await nightTone.boundingBox();
    const wideSlider = await nightRule.locator('.presence-mode-brightness').boundingBox();
    assert.ok(wideRule.height <= 36, `One line per mode on desktop (${wideRule.height}px)`);
    assert.ok(wideTone.x > wideSlider.x + wideSlider.width, 'Tone picker sits after the brightness on desktop');
    let saves = presenceSaveCount;
    await nightTone.selectOption('2700');
    await waitForPresenceSave(saves);
    assert.equal(presenceSave.mode_settings.night.color_mode, 'kelvin');
    assert.equal(presenceSave.mode_settings.night.color_kelvin, 2700);
    assert.equal(presenceSave.mode_settings.day.color_mode, 'current');
    saves = presenceSaveCount;
    await nightTone.selectOption('adaptive');
    await waitForPresenceSave(saves);
    assert.equal(presenceSave.mode_settings.night.color_mode, 'adaptive');
    saves = presenceSaveCount;
    await nightTone.selectOption('custom');
    const toneDialog = page.locator('#light-color-dialog');
    await toneDialog.waitFor({state: 'visible'});
    assert.equal(await page.locator('#light-color-dialog-title').innerText(), 'Night Tone');
    assert.equal(await page.locator('#light-color-custom').isVisible(), false, 'Only Kelvin and Adaptive apply to a mode');
    assert.equal(await page.locator('#light-color-adaptive').isChecked(), true);
    await page.locator('#light-color-adaptive').uncheck();
    assert.equal(await page.locator('#light-color-kelvin').isVisible(), true);
    await page.locator('#light-color-kelvin').evaluate(input => { input.value = '3200'; input.dispatchEvent(new Event('input', {bubbles: true})); });
    assert.equal(await page.locator('#light-color-kelvin-value').innerText(), '3200K');
    assert.equal(presenceSaveCount, saves, 'Choosing Custom… saves nothing until Apply');
    await page.locator('#light-color-apply').click();
    await toneDialog.waitFor({state: 'hidden'});
    await waitForPresenceSave(saves);
    assert.equal(presenceSave.mode_settings.night.color_mode, 'kelvin');
    assert.equal(presenceSave.mode_settings.night.color_kelvin, 3200);
    assert.equal(await nightTone.inputValue(), 'custom');
    assert.equal(await nightTone.evaluate(select => select.selectedOptions[0].textContent), '3200 K');
    saves = presenceSaveCount;
    await nightTone.selectOption('4000');
    await waitForPresenceSave(saves);
    assert.equal(presenceSave.mode_settings.night.color_kelvin, 4000);
    assert.equal(await nightTone.locator('option[value="custom"]').textContent(), 'Custom…');
    // Closing the dialog without Apply puts the picker back to what was saved.
    saves = presenceSaveCount;
    await nightTone.selectOption('custom');
    await toneDialog.waitFor({state: 'visible'});
    assert.equal(await page.locator('#light-color-kelvin').inputValue(), '4000');
    await page.locator('#light-color-dialog-close').click();
    await toneDialog.waitFor({state: 'hidden'});
    // The dialog's close event (which restores the picker) is dispatched a task later.
    await page.waitForFunction(() => document.querySelector('#presence-list [data-presence-card="binary_sensor.bedroom_6_presence"] .presence-mode-tone[aria-label="Night color tone"]').value === '4000');
    assert.equal(presenceSaveCount, saves, 'Cancelling the dialog saves nothing');
    // Phones keep each rule compact: label and tone on one line, slider and % below, no sideways scroll.
    await page.setViewportSize({width: 390, height: 844});
    await page.waitForTimeout(150);
    const phoneRule = await nightRule.boundingBox();
    const phoneTone = await nightTone.boundingBox();
    const phoneToggle = await nightRule.locator('.presence-mode-toggle').boundingBox();
    const phoneSlider = await nightRule.locator('.presence-mode-brightness').boundingBox();
    assert.ok(phoneRule.height <= 64, `Compact rule on phone (${phoneRule.height}px)`);
    assert.ok(Math.abs((phoneTone.y + phoneTone.height / 2) - (phoneToggle.y + phoneToggle.height / 2)) < 8, 'Tone shares the label line on phone');
    assert.ok(phoneSlider.y >= phoneToggle.y + phoneToggle.height - 1, 'Slider sits under the label on phone');
    assert.ok(phoneSlider.width >= 180, `Slider keeps its width on phone (${phoneSlider.width}px)`);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true);
    await page.screenshot({path: '/tmp/fht-presence-tone-mobile.png'});
    await page.setViewportSize({width: 1280, height: 900});
    await page.waitForFunction(() => !document.getElementById("app-navigation").inert);
    let doorRoomRequests = 0;
    await page.route("**/api/room-controls?kind=doors*", async route => {
      const room = new URL(route.request().url()).searchParams.get('room');
      if (room !== null) doorRoomRequests += 1;
      // An aliased room: the snapshot carries the display name in area and keys its maps by the area name.
      const door = {entity_id: 'binary_sensor.closet_door', domain: 'binary_sensor', area: "Chloe's Bedroom", original_area: 'Bedroom 6', friendly_name: 'Bedroom 6 Closet Door', state: 'on'};
      const doorModes = [{id:'day',label:'Day'},{id:'night',label:'Night'},{id:'sleep',label:'Whole Home Sleep'},{id:'floor:first',label:'First Floor Sleep'},{id:'room:bedroom_6:quiet',label:'Quiet Mode'},{id:'room:bedroom_6:sleep',label:'Sleep Mode'}];
      await new Promise(resolve => setTimeout(resolve, 350));
      await route.fulfill({json: {ok: true, rooms_ready: true, room, display_name: "Chloe's Bedroom", aliases: {'Bedroom 6': "Chloe's Bedroom"}, entities: [door], door_sensors: [door], door_mode_options: doorModes, door_mode_options_by_room: {'Bedroom 6': doorModes}, enabled_room_modes_by_room: {'Bedroom 6': ['quiet', 'sleep']}, catalog_revision: 1, control_settings: {}}});
    });
    await page.locator('[data-view="doors"]').click();
    const orderedDoors = await page.evaluate(source => {
      const functions = ['stripControlAreaPrefix', 'doorActionLabel', 'renderRoomDoorActionsSection']
        .map(name => source.match(new RegExp(`      function ${name}\\([\\s\\S]*?\\n      }`))[0]).join('\n');
      const render = new Function(`${functions}; const renderDoorPresenceCard = (payload, door, label) => '<span class="bedroom-door-light-name">' + label + '</span>'; return renderRoomDoorActionsSection;`)();
      return ["Bedroom 3 Door Sensor", "Maverick's Bedroom Door Sensor"].map(mainName => {
        const payload = {room: 'Bedroom 3', display_name: "Maverick's Bedroom", door_mode_options: [], control_settings: {}, door_sensors: [
          {entity_id: 'binary_sensor.closet', friendly_name: 'Bedroom 3 Closet Door'},
          {entity_id: 'binary_sensor.main', friendly_name: mainName},
          {entity_id: 'binary_sensor.balcony', friendly_name: 'Bedroom 3 Balcony Door'}
        ]};
        const container = document.createElement('div');
        container.innerHTML = render(payload);
        return [...container.querySelectorAll('.bedroom-door-light-name')].map(element => element.textContent);
      });
    }, require('node:fs').readFileSync(require('node:path').join(__dirname, '../future_homes_tech_app/web/index.html'), 'utf8'));
    assert.deepEqual(orderedDoors, Array(2).fill(["Maverick's Door", 'Balcony Door', 'Closet Door']));
    await page.locator('#doors-load-progress:not([hidden])').waitFor({state: 'visible'});
    assert.equal(await page.locator('#doors-list').evaluate(element => getComputedStyle(element).visibility), 'hidden');
    assert.equal((await page.locator('#doors-list').innerText()).includes('Loading actions'), false);
    assert.equal(await page.locator('#doors-list summary').count(), 0);
    assert.equal(await page.locator('[data-page-refresh="doors"]').count(), 0);
    assert.equal(await page.locator('.page-actions').evaluate(element => getComputedStyle(element).backgroundColor), 'rgba(0, 0, 0, 0)');
    await page.locator('#doors-list .door-action-group-select').waitFor({state: 'attached'});
    assert.equal(await page.locator('#doors-list .door-action-status-bubble').count(), 0);
    const doorValues = await page.locator('#doors-list .door-action-group-select option').evaluateAll(options => options.map(option => option.value).filter(Boolean));
    assert.equal(await page.locator('#doors-list [data-door-options]').isVisible(), false);
    assert.equal(await page.locator('#doors-list .presence-card').count(), 0);
    assert.deepEqual(await page.locator('#doors-list .door-settings-row').evaluate(element => [getComputedStyle(element).backgroundColor, getComputedStyle(element).borderLeftWidth]), ['rgba(0, 0, 0, 0)', '0px']);
    assert.deepEqual(await page.locator('#doors-list .door-settings-label').evaluateAll(elements => elements.map(element => getComputedStyle(element).fontWeight)), ['900', '900']);
    assert.equal(await page.locator('#doors-list .activation-delay-input, #doors-list .clear-delay-input').count(), 0);
    assert.deepEqual(doorValues.sort(), ['light_group:light.closet', 'light_group:light.vanity']);
    await page.locator('#doors-list .action-multi-summary').click();
    const doorMenu = page.locator('#doors-list .action-multi-menu');
    await doorMenu.waitFor({state: 'visible'});
    await doorMenu.locator('input[data-action-option]').first().check();
    assert.equal(await page.locator('#doors-list .action-multi-summary-id').innerText(), '');
    assert.equal(await page.locator('#doors-list .action-multi-summary-id').isVisible(), false);
    assert.ok(!(await page.locator('#doors-list .action-multi-summary').innerText()).includes('light.'));
    assert.equal(await doorMenu.evaluate(element => element.matches(':popover-open') || (element.tagName === 'DIALOG' && element.open)), true);
    await page.keyboard.press('Escape');
    await doorMenu.waitFor({state: 'hidden'});
    await page.locator('#doors-load-progress').waitFor({state: 'hidden'});
    assert.equal(doorRoomRequests, 0, 'Doors render every room from one snapshot without per-room requests');
    assert.equal(await page.locator('#doors-list').evaluate(element => getComputedStyle(element).visibility), 'visible');
    const doorStyle = await page.locator('#doors-list .doors-room-card').first().evaluate(element => {
      const style = getComputedStyle(element);
      return {background: style.backgroundColor, blur: style.backdropFilter, border: style.borderLeftWidth, color: style.borderLeftColor};
    });
    assert.deepEqual(doorStyle, {background: 'rgba(4, 13, 23, 0.25)', blur: 'blur(3px)', border: '4px', color: 'rgb(53, 174, 247)'});
    assert.equal(await page.locator('#doors-list').evaluate(element => getComputedStyle(element).gridTemplateColumns.split(' ').length), 2);
    assert.equal(await page.locator('#doors-list [data-door-options]').isVisible(), true);
    assert.equal(await page.locator('#doors-list [data-door-rule]').count(), 4);
    assert.deepEqual(await page.locator('#doors-list [data-door-rule]').evaluateAll(rows => rows.map(row => row.dataset.doorRule)), ['room:bedroom_6:sleep', 'day', 'night', 'room:bedroom_6:quiet']);
    assert.equal(await page.locator('#doors-list .door-mode-divider').count(), 1);
    await page.locator('#doors-list .door-timeout').selectOption('5');
    const timeoutStyle = await page.locator('#doors-list .door-timeout').evaluate(element => { const style = getComputedStyle(element); return [style.height, style.fontSize, style.fontWeight, style.paddingLeft]; });
    assert.deepEqual(timeoutStyle, await page.locator('#doors-list .action-multi-summary').evaluate(element => { const style = getComputedStyle(element); return [style.height, style.fontSize, style.fontWeight, style.paddingLeft]; }));
    // Door rules carry the same tone picker; a preset saves as Kelvin beside the brightness.
    const doorNightTone = page.locator('#doors-list [data-door-rule="night"] .presence-mode-tone');
    assert.equal(await page.locator('#doors-list .presence-mode-tone').count(), 4);
    assert.deepEqual(await doorNightTone.locator('option').allTextContents(), ['Current', 'Warm', 'Neutral', 'Cool', 'Adaptive', 'Custom…']);
    assert.ok((await page.locator('#doors-list [data-door-rule="night"]').boundingBox()).height <= 36, 'One line per door mode on desktop');
    const doorSavesBefore = savedDoorCards.length;
    await doorNightTone.selectOption('5500');
    for (let attempt = 0; attempt < 100 && savedDoorCards.length === doorSavesBefore; attempt += 1) await page.waitForTimeout(50);
    const doorToneSave = savedDoorCards.at(-1);
    assert.equal(doorToneSave.assignment_id, 'door:binary_sensor.closet_door');
    assert.equal(doorToneSave.timeout_minutes, 5);
    assert.equal(doorToneSave.door_modes.night.color_mode, 'kelvin');
    assert.equal(doorToneSave.door_modes.night.color_kelvin, 5500);
    assert.equal(doorToneSave.door_modes.day.color_mode, 'current');
    await page.locator('#doors-list .bedroom-door-light-list').evaluate(element => element.append(element.firstElementChild.cloneNode(true)));
    assert.equal(await page.locator('#doors-list .switches-area').evaluate(element => getComputedStyle(element).gridColumn), '1 / -1');
    assert.equal(await page.locator('#doors-list .bedroom-door-light-list').evaluate(element => getComputedStyle(element).gridTemplateColumns.split(' ').length), 2);
    // Two columns: each door is its own card with the left highlight; the room card falls away.
    assert.deepEqual(await page.locator('#doors-list .door-settings-row').evaluateAll(rows => rows.map(row => [getComputedStyle(row).borderLeftWidth, getComputedStyle(row).backgroundColor, getComputedStyle(row).borderTopWidth])),
      [['4px', 'rgba(4, 13, 23, 0.25)', '1px'], ['4px', 'rgba(4, 13, 23, 0.25)', '1px']]);
    assert.equal(await page.locator('#doors-list .doors-room-card').first().evaluate(element => getComputedStyle(element).backgroundColor), 'rgba(0, 0, 0, 0)');
    await page.setViewportSize({width: 390, height: 844});
    assert.equal(await page.locator('#doors-list .bedroom-door-light-list').evaluate(element => getComputedStyle(element).gridTemplateColumns.split(' ').length), 1);
    // One column: the room card returns and a blue line separates the doors.
    assert.equal(await page.locator('#doors-list .doors-room-card').first().evaluate(element => getComputedStyle(element).borderLeftWidth), '4px');
    assert.deepEqual(await page.locator('#doors-list .door-settings-row').evaluateAll(rows => rows.map(row => [getComputedStyle(row).borderLeftWidth, getComputedStyle(row).borderTopWidth, getComputedStyle(row).borderTopColor])),
      [['0px', '0px', 'rgb(237, 244, 248)'], ['0px', '2px', 'rgb(53, 174, 247)']]);
    assert.equal(await page.locator('#doors-list').evaluate(element => getComputedStyle(element).gridTemplateColumns.split(' ').length), 1);
    await page.waitForTimeout(150);
    const phoneDoorRule = await page.locator('#doors-list [data-door-rule="night"]').first().boundingBox();
    assert.ok(phoneDoorRule.height <= 64, `Compact door rule on phone (${phoneDoorRule.height}px)`);
    assert.ok((await page.locator('#doors-list [data-door-rule="night"] .door-rule-brightness').first().boundingBox()).width >= 180, 'Door slider keeps its width on phone');
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true);
    await page.screenshot({path: '/tmp/fht-doors-tone-mobile.png'});
    await page.setViewportSize({width: 1280, height: 900});
    await page.locator('[data-view="home"]').click();
    await page.setViewportSize({width: 390, height: 844});
    assert.equal((await page.locator('#view-home').innerText()).trim(), '');
    const headerStyle = await page.locator('.page-actions').evaluate(element => {
      const style = getComputedStyle(element);
      return {background: style.backgroundColor, blur: style.backdropFilter, border: style.borderBottomWidth};
    });
    assert.deepEqual(headerStyle, {background: 'rgba(0, 0, 0, 0)', blur: 'none', border: '0px'});
    assert.equal(await navigationToggle.isVisible(), true);
    assert.equal(await page.locator('#exit-app').isVisible(), true);
    assert.equal(await page.locator('#open-updates').isVisible(), true);
    await page.evaluate(() => { window.fhtExitEmbedded = destination => { window.testExitDestination = destination; return true; }; });
    await page.locator('#open-updates').click();
    assert.equal(await page.evaluate(() => window.testExitDestination), '/config/updates');
    await page.locator('#exit-app').click();
    assert.equal(await page.evaluate(() => window.testExitDestination), '/config');
    await page.setViewportSize({width: 1280, height: 900});
    if (!(await page.locator('[data-view="rooms"]').isVisible())) await page.locator('#settings-toggle').click();
    await page.locator('[data-view="rooms"]').click();
    await page.waitForFunction(() => document.querySelectorAll('#room-configurator-list .room-alias-input').length === 2);
    assert.equal(await page.locator('#home-configurator-header').isVisible(), false);
    for (const color of ['red', 'green', 'blue']) {
      await page.locator('#app-color-select').selectOption(color);
      await page.waitForFunction(color => document.documentElement.dataset.appColor === color, color);
      assert.equal(savedAppColor, color);
      for (const selector of ['#doors-list .door-rule-enabled', '#doors-list .door-rule-brightness']) {
        assert.equal(await page.locator(selector).first().evaluate(element => getComputedStyle(element).accentColor), {blue:'rgb(53, 174, 247)', red:'rgb(255, 69, 69)', green:'rgb(57, 223, 101)'}[color]);
      }
      assert.equal(await page.evaluate(() => localStorage.getItem('fht-app-color')), color);
      const logo = color === 'blue' ? 'future-homes-tech-logo.png' : `app-logo-${color}.png`;
      assert.ok((await navigationToggle.locator('img').getAttribute('src')).endsWith(logo));
      if (color !== 'blue') {
        for (const button of await page.locator('.menu-button').all()) {
          assert.equal(await button.evaluate(element => getComputedStyle(element).color), color === 'red' ? 'rgb(255, 69, 69)' : 'rgb(57, 223, 101)');
        }
        assert.ok(await page.locator('body').evaluate((element, color) => getComputedStyle(element).backgroundImage.includes(`app-background-${color}.webp`), color));
        assert.equal(await page.locator('[data-house-settings]').evaluate(element => getComputedStyle(element).borderLeftColor), color === 'red' ? 'rgb(255, 69, 69)' : 'rgb(57, 223, 101)');
      }
    }
    assert.equal(await page.locator('.whole-home-modes-title').first().innerText(), 'Whole Home Modes');
    assert.equal(await page.locator('.room-names-title').innerText(), 'Room Names');
    assert.equal(await page.locator('.room-names-card .room-names-title').count(), 0);
    assert.equal(await page.locator('[data-house-settings] .whole-home-modes-title').count(), 0);
    assert.equal(await page.locator('[data-house-settings] .house-mode-time-row').first().evaluate(element => getComputedStyle(element).borderTopWidth), '0px');
    assert.equal(await page.locator('.whole-home-floor-card > .home-configurator-floor-heading').count(), 0);
    assert.deepEqual(await page.locator('select[data-floor-id="first"] option').evaluateAll(options => options.map(option => option.value)), ['', 'input_select.fht_bedroom_6_mode']);
    assert.deepEqual(await page.locator('select[data-floor-id="second"] option').evaluateAll(options => options.map(option => option.value)), ['', 'input_select.fht_bedroom_2_mode']);
    assert.equal(await page.locator('#room-configurator-list > section.home-configurator-floor-card:visible').count(), 1);
    assert.equal(await page.locator('.room-names-card').count(), 1);
    assert.deepEqual(await page.locator('.room-name-row > span').allTextContents(), ['Bedroom 2', 'Bedroom 6']);
    assert.deepEqual(await page.locator('.room-name-row input').evaluateAll(inputs => inputs.map(input => input.value)), ["Bailey's Bedroom", "Chloe's Bedroom"]);
    assert.equal(await page.locator('.room-names-card').evaluate(element => getComputedStyle(element).borderLeftWidth), '4px');
    assert.equal(await page.locator('#room-configurator-list details.room-configurator-card').count(), 0);
    assert.equal(await page.locator('#room-configurator-list [data-wake-routine], #room-configurator-list [data-lazy-section]').count(), 0);
    assert.equal(await page.locator('#room-state').isVisible(), false);
    for (const selector of ['#room-configurator-list > section.home-configurator-floor-card', '#doors-list .switches-area', '#presence-list .switches-area']) {
      assert.deepEqual(await page.locator(selector).first().evaluate(element => {
        const style = getComputedStyle(element);
        return [style.backgroundColor, style.borderTopWidth, style.backdropFilter];
      }), ['rgba(0, 0, 0, 0)', '0px', 'none']);
    }
    await page.locator('#rooms-load-progress').waitFor({state: 'hidden'});
    await page.setViewportSize({width: 390, height: 844});
    assert.equal(await page.locator('#room-configurator-list .home-configurator-floor-rooms').first().evaluate(element => getComputedStyle(element).gridTemplateColumns.split(' ').length), 1);
    if (await navigationToggle.getAttribute('aria-expanded') === 'true') await navigationToggle.click();
    await page.waitForTimeout(250);
    await page.screenshot({path: '/tmp/fht-598-configurator.png'});
    await page.evaluate(() => { document.querySelector('main').style.minHeight = '2400px'; window.scrollTo(0, 300); });
    await page.waitForTimeout(100);
    assert.ok(await page.locator('#exit-app').evaluate(element => element.getBoundingClientRect().bottom <= 0));
    const beforeReveal = await page.evaluate(() => window.scrollY);
    assert.equal(await page.locator('.page-actions').evaluate(element => getComputedStyle(element, '::before').maskImage), 'linear-gradient(rgb(0, 0, 0), rgba(0, 0, 0, 0))');
    assert.equal(await page.locator('.page-actions').evaluate(element => getComputedStyle(element, '::before').backgroundColor), 'rgba(0, 0, 0, 0.85)');
    assert.equal(await page.locator('.page-actions').evaluate(element => getComputedStyle(element, '::before').backdropFilter), 'blur(10px)');
    assert.equal(await page.locator('.page-actions').evaluate(element => getComputedStyle(element, '::before').translate), await page.locator('#exit-app').evaluate(element => getComputedStyle(element).translate));
    await page.mouse.move(5, 400);
    await page.mouse.wheel(0, -160);
    await page.waitForTimeout(100);
    assert.equal(await page.evaluate(() => window.scrollY), beforeReveal);
    assert.equal(await page.evaluate(() => parseFloat(document.body.style.getPropertyValue('--room-header-offset'))), 0);
    await page.mouse.wheel(0, -60);
    await page.waitForTimeout(100);
    assert.ok(await page.evaluate(() => window.scrollY) < beforeReveal);
    await page.evaluate(() => { document.querySelector('main').style.minHeight = ''; window.scrollTo(0, 0); });
    await page.waitForTimeout(100);
    for (const width of [1440, 900, 768, 600, 390]) {
      await page.setViewportSize({width, height: 900});
      const contentBox = await page.locator('#room-configurator-list').boundingBox();
      for (const selector of ['.house-mode-dial-list', '.room-names-list']) {
        assert.equal(await page.locator(selector).evaluate(element => getComputedStyle(element).gridTemplateColumns.split(' ').length), contentBox.width >= 640 ? 2 : 1);
      }
      const modesBox = await page.locator('[data-house-settings]').boundingBox();
      const namesBox = await page.locator('.room-names-card').boundingBox();
      for (const title of await page.locator('.whole-home-modes-title').all()) {
        assert.equal(await title.evaluate(element => element.nextElementSibling.getBoundingClientRect().top - element.getBoundingClientRect().bottom), 8);
      }
      const referenceField = await page.locator('.house-mode-offset-select').first().boundingBox();
      for (const row of await page.locator('.house-mode-time-row, .room-name-row').all()) {
        const alignment = await row.evaluate(element => {
          const label = element.querySelector(':scope > span');
          const field = element.querySelector('.house-mode-offset-select, .action-multi-summary, .room-alias-input');
          const labelStyle = getComputedStyle(label);
          const fieldStyle = getComputedStyle(field);
          return [label.getBoundingClientRect().left + parseFloat(labelStyle.paddingLeft), field.getBoundingClientRect().left + parseFloat(fieldStyle.borderLeftWidth) + parseFloat(fieldStyle.paddingLeft)];
        });
        assert.ok(Math.abs(alignment[0] - alignment[1]) < 1);
      }
      for (const dropdown of await page.locator('.house-mode-offset-select').all()) {
        assert.equal(await dropdown.evaluate(element => getComputedStyle(element).color), 'rgb(255, 255, 255)');
      }
      const referenceFont = await page.locator('.house-mode-time-title').first().evaluate(element => {
        const style = getComputedStyle(element);
        return [style.fontFamily, style.fontSize, style.fontWeight, style.color];
      });
      for (const field of await page.locator('#room-configurator-list .room-alias-input, #room-configurator-list .action-multi-summary').all()) {
        const box = await field.boundingBox();
        assert.equal(box.height, referenceField.height);
        assert.ok(Math.abs(box.width - referenceField.width) < 1);
      }
      assert.deepEqual(await page.locator('.room-name-row > span').first().evaluate(element => {
        const style = getComputedStyle(element);
        return [style.fontFamily, style.fontSize, style.fontWeight, style.color];
      }), referenceFont);
      for (const row of await page.locator('.room-name-row').all()) {
        assert.deepEqual(await row.evaluate(element => {
          const style = getComputedStyle(element);
          return [style.backgroundColor, style.backdropFilter, style.boxShadow, style.borderTopWidth];
        }), ['rgba(0, 0, 0, 0)', 'none', 'none', '0px']);
        const labelBox = await row.locator('span').boundingBox();
        const inputBox = await row.locator('input').boundingBox();
        assert.ok(inputBox.y >= labelBox.y + labelBox.height);
        assert.ok(Math.abs(inputBox.width - labelBox.width) < 1);
      }
      for (const row of await page.locator('[data-house-settings] .house-mode-time-row').all()) {
        const labelBox = await row.locator('.house-mode-time-title').boundingBox();
        const selectorBox = await row.locator('.house-mode-offset-select, .action-multi-picker').boundingBox();
        assert.ok(selectorBox.y >= labelBox.y + labelBox.height);
        assert.ok(Math.abs(selectorBox.width - labelBox.width) < 1);
      }
      const exitBox = await page.locator('#exit-app').boundingBox();
      assert.ok(modesBox.y >= exitBox.y + exitBox.height + 8);
      if (width <= 820) {
        assert.equal(await page.locator('main').evaluate(element => getComputedStyle(element).paddingTop), width < 600 ? '34px' : '48px');
        await page.evaluate(() => document.documentElement.style.setProperty('--app-safe-top', '59px'));
        const safeLogo = await navigationToggle.boundingBox();
        const safeExit = await page.locator('#exit-app').boundingBox();
        const safeCard = await page.locator('[data-house-settings]').boundingBox();
        const safeTitle = await page.locator('.whole-home-modes-title').first().boundingBox();
        assert.ok(safeTitle.y >= safeLogo.y + safeLogo.height);
        assert.equal(safeLogo.y, width >= 600 ? 59 : 42);
        const safeUpdate = await page.locator('#open-updates').boundingBox();
        assert.equal(safeExit.y + safeExit.height / 2, safeLogo.y + safeLogo.height / 2);
        assert.equal(safeUpdate.y + safeUpdate.height / 2, safeLogo.y + safeLogo.height / 2);
        assert.ok(safeCard.y >= safeLogo.y + safeLogo.height + 8);
        await page.evaluate(() => document.documentElement.style.removeProperty('--app-safe-top'));
      }
      assert.ok(Math.abs(modesBox.x - namesBox.x) < 1);
      assert.ok(Math.abs(modesBox.width - namesBox.width) < 1);
      const bars = await page.locator('progress').evaluateAll(elements => elements.map(element => {
        const probe = element.cloneNode(true);
        probe.hidden = false;
        probe.style.display = 'block';
        document.body.append(probe);
        const rect = probe.getBoundingClientRect();
        const sidebar = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--sidebar-width')) || 300;
        probe.remove();
        return {width: rect.width, left: rect.left + rect.width / 2, sidebar};
      }));
      for (const bar of bars) {
        const contentWidth = width > 820 ? width - bar.sidebar : width;
        const expectedWidth = width > 820 ? contentWidth / 2 : Math.min(width / 2, width - 224);
        assert.ok(Math.abs(bar.width - expectedWidth) < 1);
        assert.ok(Math.abs(bar.left - (width > 820 ? bar.sidebar + contentWidth / 2 : width / 2)) < 1);
      }
    }
    assert.deepEqual(errors, []);
    console.log("Switches browser checks passed: automatic area loading, bounded requests, centered aliases, device columns, Inovelli and action pickers.");
  } finally {
    await browser.close();
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
