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
    const savedHolds = [];
    await page.route("**/api/switch-light-groups", async route => {
      if (route.request().postDataJSON().setting === "exhaust_timer") savedTimers.push(route.request().postDataJSON());
      if (route.request().postDataJSON().setting === "exhaust_humidity") {
        savedHumidity.push(route.request().postDataJSON());
        if (route.request().postDataJSON().stop_below === 70) return route.fulfill({status: 400, json: {ok: false, error: "Stop below must be lower than Start above."}});
      }
      if (route.request().postDataJSON().setting === "hold") {
        savedHolds.push(route.request().postDataJSON());
        return route.fulfill({json: {ok: true, action_settings: {[route.request().postDataJSON().assignment_id]: {hold: route.request().postDataJSON().hold}}}});
      }
      if (route.request().postDataJSON().door_modes) savedDoorCards.push(route.request().postDataJSON());
      savedActions.push(route.request().postDataJSON().actions);
      await route.fulfill({json: {ok: true}});
    });
    const humiditySensors = [{entity_id: "sensor.bedroom_6_humidity", friendly_name: "Bedroom 6 Humidity", state: "71.4", room: "Bedroom 6"}, {entity_id: "sensor.kitchen_humidity", friendly_name: "Kitchen Humidity", state: "40", room: "Kitchen"}];
    entities.push({ entity_id: "event.bedroom_6_switch_button_up", domain: "event", device_id: "inovelli", device_name: "Bedroom 6 Inovelli Switch", friendly_name: "Bedroom 6 Switch Up", event_types: ["multi_press_1", "multi_press_2", "multi_press_3", "multi_press_4", "multi_press_5", "long_press", "long_release"], state: "unknown", area: "Bedroom 6", original_area: "Bedroom 6" });
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
    assert.equal(await page.locator('[data-view="switches"]').count(), 0, "Switches live on Room Configurator now");
    await page.locator('[data-view="room-config"]').click();
    await page.waitForFunction(() => [...document.querySelectorAll('#room-config-picker option')].some(option => option.value === 'Bedroom 6'));
    await page.locator('#room-config-picker').selectOption('Bedroom 6');
    await page.locator('[data-room-config-switches]').waitFor({state: "visible"});
    await page.waitForFunction(() => document.querySelector('#room-config-switches [data-control-room]')?.dataset.ready === "true");
    assert.equal(await page.locator('[data-room-config-switches] h2').innerText(), "Switches");
    const list = page.locator("#room-config-switches");
    assert(!(await list.innerText()).includes("Loading actions"));
    assert.equal(await page.locator("#exit-app").isVisible(), true);
    assert.equal(await page.locator(".page-actions").evaluate(element => getComputedStyle(element).backgroundColor), "rgba(0, 0, 0, 0)");
    assert.equal(await page.locator("#exit-app").evaluate(element => getComputedStyle(element).backgroundColor), "rgba(0, 0, 0, 0)");
    assert.equal(await list.locator("details[data-control-room]").count(), 0);
    assert.equal(await list.locator(".switches-area-heading").count(), 0, "The picked room is the card's room, so no room heading");
    assert.equal(await list.locator(".control-device-card:not(.switch-gesture-card)").count(), 2);
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
    assert.equal(await list.locator(".inovelli-controller").count(), 0, "Multi-action switches no longer render as one big card");
    const gestureCards = list.locator('.switch-gesture-card');
    assert.deepEqual(await gestureCards.locator(".control-channel-name").allTextContents(), ["Single Press", "Double Press", "Triple Press", "4× Press", "5× Press", "Long Press", "Long Release"], "One card per button action");
    assert.deepEqual([...new Set(await gestureCards.locator(".control-device-title").allTextContents())], ["Bedroom 6 Switch Up"]);
    // Only a long press that also reports its release can brighten or dim while held.
    const holdSelect = list.locator(".switch-hold-select");
    assert.equal(await holdSelect.count(), 1);
    assert.equal(await gestureCards.nth(5).locator(".switch-hold-select").count(), 1, "The hold choice sits on the Long Press card");
    assert.deepEqual(await holdSelect.locator("option").allTextContents(), ["Turn On / Off", "Brighten until released", "Dim until released"]);
    await holdSelect.selectOption("brighten");
    await page.waitForFunction(() => document.querySelector(".switch-hold-select").dataset.saved === "brighten");
    assert.deepEqual(savedHolds.at(-1), {setting: "hold", assignment_id: "event.bedroom_6_switch_button_up|long_press", hold: "brighten"});
    const firstGesture = await gestureCards.nth(0).boundingBox();
    const secondGesture = await gestureCards.nth(1).boundingBox();
    assert(Math.abs(firstGesture.y - secondGesture.y) < 2 && secondGesture.x > firstGesture.x, "Button actions sit two to a row on desktop");
    assert.equal(loaded.size, 1, "Only the picked room's switches load");
    const cards = list.locator(".switches-area").first().locator(".control-device-card");
    const first = await cards.nth(0).boundingBox();
    const second = await cards.nth(1).boundingBox();
    assert(Math.abs(first.y - second.y) < 2 && second.x > first.x, "Two device columns on desktop");
    assert.equal(await list.locator(".room-controls-body").first().evaluate(element => getComputedStyle(element).paddingTop), "6px");
    // A room with no switches shows no Switches card.
    await page.locator('#room-config-picker').selectOption('Bedroom 2');
    await page.waitForFunction(() => document.querySelector('[data-room-config-switches]')?.hidden === true);
    await page.locator('#room-config-picker').selectOption('Bedroom 6');
    await page.waitForFunction(() => document.querySelector('#room-config-switches [data-control-room]')?.dataset.ready === "true");
    for (const selector of [".control-device-card", ".switch-gesture-card"]) {
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
    await page.waitForFunction(() => !document.querySelector('#room-config-switches select[data-assignment-id="switch.room_0_1"]').disabled);
    assert.deepEqual(savedActions.at(-1), ["light_group:light.vanity"]);
    assert.equal(await page.locator('#room-config-switches .exhaust-timer-select, #room-config-switches .exhaust-humidity-field').count(), 0, "Exhaust controls live on the Environment page now");
    assert.equal(await list.locator(".action-multi-summary-text").first().textContent(), "Closet Light, Bathroom Vanity Light", "The collapsed summary drops the room name the card already shows");
    await list.locator(".action-multi-picker summary").first().click();
    await menu.getByRole("button", {name: "Clear Actions", exact: true}).click();
    await list.locator(".action-multi-picker summary").first().click();
    await page.waitForFunction(() => !document.querySelector('#room-config-switches select[data-assignment-id="switch.room_0_1"]').disabled);
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
    assert.deepEqual(await page.locator('#settings-submenu [data-view]').evaluateAll(elements => elements.map(element => element.textContent.trim())), ['Room Devices', 'Home Configurator', 'Room Configurator', 'Alarm', 'Buttons', 'Climate', 'Unifi', 'Users', 'Voice Control']);
    assert.equal(await page.locator('.topbar').evaluate(element => getComputedStyle(element).borderRightWidth), '0px');
    await page.waitForTimeout(200);
    await page.screenshot({path: '/tmp/fht-592-menu-glass.png'});
    await page.waitForTimeout(220);
    await page.screenshot({ path: "/tmp/fht-navigation-0.5.44-open.png" });
    await page.locator('[data-view="room-config"]').click();
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
    await page.route("**/api/room-controls?kind=presence*", async route => {
      const room = new URL(route.request().url()).searchParams.get("room");
      if (room === null) await new Promise(resolve => setTimeout(resolve, 500));
      await route.fulfill({json: {ok: true, rooms_ready: true, room, enabled_room_modes: ['chill'], enabled_room_modes_by_room: {"Bedroom 6": ['chill']}, display_name: "Chloe's Bedroom", aliases: {"Bedroom 6": "Chloe's Bedroom"}, catalog_revision: 1,
        entities: [{entity_id: "binary_sensor.bedroom_6_presence", domain: "binary_sensor", device_class: "occupancy", area: "Bedroom 6", friendly_name: "Bedroom 6 Presence Occupancy (2)", state: "off"}, {entity_id: "binary_sensor.fht_bedroom_6_group_presence", domain: "binary_sensor", device_class: "occupancy", area: "Bedroom 6", friendly_name: "FHT - Bedroom 6 Group Presence"}],
        presence: {assignments: {"binary_sensor.bedroom_6_presence": ["light.closet"]}, timings: {}, mode_settings: {}}}});
    });
    // Presence settings live in each mode's pop-up; there is no Presence page.
    assert.equal(await page.locator('[data-view="presence"]').count(), 0, 'Presence has no menu page');
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
    // Doors live on Room Configurator: pick the room there.
    if (!(await page.locator('[data-view="room-config"]').isVisible())) await page.locator('#settings-toggle').click();
    await page.locator('[data-view="room-config"]').click();
    await page.waitForFunction(() => [...document.querySelectorAll('#room-config-picker option')].some(option => option.value === 'Bedroom 6'));
    await page.locator('#room-config-picker').selectOption('Bedroom 6');
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
    assert.equal(await page.locator('#room-config-doors summary').count(), 0);
    // Doors cards stack one after another with no room heading between them.
    assert.equal(await page.locator('#room-config-doors .switches-area-heading').count(), 0);
    assert.equal(await page.locator('.page-actions').evaluate(element => getComputedStyle(element).backgroundColor), 'rgba(0, 0, 0, 0)');
    await page.locator('#room-config-doors .door-action-group-select').waitFor({state: 'attached'});
    assert.equal(await page.locator('#room-config-doors .door-action-status-bubble').count(), 0);
    const doorValues = await page.locator('#room-config-doors .door-action-group-select option').evaluateAll(options => options.map(option => option.value).filter(Boolean));
    assert.equal(await page.locator('#room-config-doors [data-door-options]').isVisible(), false);
    assert.equal(await page.locator('#room-config-doors .presence-card').count(), 0);
    assert.deepEqual(await page.locator('#room-config-doors .door-settings-row').evaluate(element => [getComputedStyle(element).backgroundColor, getComputedStyle(element).borderLeftWidth]), ['rgba(0, 0, 0, 0)', '0px']);
    assert.deepEqual(await page.locator('#room-config-doors .door-settings-label').evaluateAll(elements => elements.map(element => getComputedStyle(element).fontWeight)), ['900', '900']);
    assert.equal(await page.locator('#room-config-doors .activation-delay-input, #room-config-doors .clear-delay-input').count(), 0);
    assert.deepEqual(doorValues.sort(), ['light_group:light.closet', 'light_group:light.vanity']);
    await page.locator('#room-config-doors .action-multi-summary').click();
    const doorMenu = page.locator('#room-config-doors .action-multi-menu');
    await doorMenu.waitFor({state: 'visible'});
    await doorMenu.locator('input[data-action-option]').first().check();
    assert.equal(await page.locator('#room-config-doors .action-multi-summary-id').innerText(), '');
    assert.equal(await page.locator('#room-config-doors .action-multi-summary-id').isVisible(), false);
    assert.ok(!(await page.locator('#room-config-doors .action-multi-summary').innerText()).includes('light.'));
    assert.equal(await doorMenu.evaluate(element => element.matches(':popover-open') || (element.tagName === 'DIALOG' && element.open)), true);
    await page.keyboard.press('Escape');
    await doorMenu.waitFor({state: 'hidden'});
    assert.equal(await page.locator('#room-config-doors [data-door-options]').isVisible(), true);
    // The Doors card keeps the action and timeout; brightness per mode lives in each mode's pop-up.
    assert.equal(await page.locator('#room-config-doors [data-door-rule]').count(), 0);
    assert.equal(await page.locator('#room-config-doors .presence-mode-tone').count(), 0);
    assert.equal(await page.locator('#room-config-doors .door-mode-hint').isVisible(), true);
    const doorSavesBefore = savedDoorCards.length;
    await page.locator('#room-config-doors .door-timeout').selectOption('5');
    const timeoutStyle = await page.locator('#room-config-doors .door-timeout').evaluate(element => { const style = getComputedStyle(element); return [style.height, style.fontSize, style.fontWeight, style.paddingLeft]; });
    assert.deepEqual(timeoutStyle, await page.locator('#room-config-doors .action-multi-summary').evaluate(element => { const style = getComputedStyle(element); return [style.height, style.fontSize, style.fontWeight, style.paddingLeft]; }));
    for (let attempt = 0; attempt < 100 && savedDoorCards.at(-1)?.timeout_minutes !== 5; attempt += 1) await page.waitForTimeout(50);
    assert.ok(savedDoorCards.length > doorSavesBefore);
    const doorTimeoutSave = savedDoorCards.at(-1);
    assert.equal(doorTimeoutSave.assignment_id, 'door:binary_sensor.closet_door');
    assert.equal(doorTimeoutSave.timeout_minutes, 5);
    // Every mode's saved light settings ride along unchanged.
    assert.deepEqual(Object.keys(doorTimeoutSave.door_modes), ['room:bedroom_6:sleep', 'day', 'night', 'room:bedroom_6:quiet']);
    assert.equal(doorTimeoutSave.door_modes.day.color_mode, 'current');
    await page.locator('#room-config-doors .bedroom-door-light-list').evaluate(element => element.append(element.firstElementChild.cloneNode(true)));
    assert.equal(await page.locator('#room-config-doors .bedroom-door-light-list').evaluate(element => getComputedStyle(element).gridTemplateColumns.split(' ').length), 1, 'Doors in a room stack on desktop too');
    // Desktop is one column as well: the room card stays and a blue line separates the doors.
    assert.deepEqual(await page.locator('#room-config-doors .door-settings-row').evaluateAll(rows => rows.map(row => [getComputedStyle(row).borderLeftWidth, getComputedStyle(row).borderTopWidth, getComputedStyle(row).borderTopColor])),
      [['0px', '0px', 'rgb(237, 244, 248)'], ['0px', '2px', 'rgb(53, 174, 247)']]);
    await page.screenshot({path: '/tmp/fht-doors-desktop.png'});
    await page.setViewportSize({width: 390, height: 844});
    assert.equal(await page.locator('#room-config-doors .bedroom-door-light-list').evaluate(element => getComputedStyle(element).gridTemplateColumns.split(' ').length), 1);
    // One column: the room card returns and a blue line separates the doors.
    assert.deepEqual(await page.locator('#room-config-doors .door-settings-row').evaluateAll(rows => rows.map(row => [getComputedStyle(row).borderLeftWidth, getComputedStyle(row).borderTopWidth, getComputedStyle(row).borderTopColor])),
      [['0px', '0px', 'rgb(237, 244, 248)'], ['0px', '2px', 'rgb(53, 174, 247)']]);
    await page.waitForTimeout(150);
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
    await page.waitForFunction(() => document.querySelectorAll('#room-configurator-list [data-house-settings] .house-mode-time-row').length > 0);
    assert.equal(await page.locator('#home-configurator-header').isVisible(), false);
    for (const color of ['red', 'green', 'blue']) {
      await page.locator('#app-color-select').selectOption(color);
      await page.waitForFunction(color => document.documentElement.dataset.appColor === color, color);
      assert.equal(savedAppColor, color);
      // Door mode rows now live in the mode pop-up; the same checkbox and slider styles apply everywhere.
      await page.evaluate(() => { if (!document.getElementById('accent-probe')) document.body.insertAdjacentHTML('beforeend', '<div id="accent-probe"><input type="checkbox"><input type="range"></div>'); });
      for (const selector of ['#accent-probe input[type="checkbox"]', '#accent-probe input[type="range"]']) {
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
    assert.equal(await page.locator('#room-configurator-list :is(.room-names-title, .room-names-card, .room-alias-input)').count(), 0, 'Room names live on Room Configurator now');
    assert.equal(await page.locator('[data-house-settings] .whole-home-modes-title').count(), 0);
    assert.equal(await page.locator('[data-house-settings] .house-mode-time-row').first().evaluate(element => getComputedStyle(element).borderTopWidth), '0px');
    assert.equal(await page.locator('.whole-home-floor-card > .home-configurator-floor-heading').count(), 0);
    assert.deepEqual(await page.locator('select[data-floor-id="first"] option').evaluateAll(options => options.map(option => option.value)), ['', 'input_select.fht_bedroom_6_mode']);
    assert.deepEqual(await page.locator('select[data-floor-id="second"] option').evaluateAll(options => options.map(option => option.value)), ['', 'input_select.fht_bedroom_2_mode']);
    assert.equal(await page.locator('#room-configurator-list > section.home-configurator-floor-card:visible').count(), 1);
    assert.equal(await page.locator('#room-configurator-list details.room-configurator-card').count(), 0);
    assert.equal(await page.locator('#room-configurator-list [data-wake-routine], #room-configurator-list [data-lazy-section]').count(), 0);
    assert.equal(await page.locator('#room-state').isVisible(), false);
    for (const selector of ['#room-configurator-list > section.home-configurator-floor-card', '#room-config-doors .switches-area']) {
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
      for (const selector of ['.house-mode-dial-list']) {
        assert.equal(await page.locator(selector).evaluate(element => getComputedStyle(element).gridTemplateColumns.split(' ').length), contentBox.width >= 640 ? 2 : 1);
      }
      const modesBox = await page.locator('[data-house-settings]').boundingBox();
      for (const title of await page.locator('#room-configurator-list .whole-home-modes-title').all()) {
        assert.equal(await title.evaluate(element => element.nextElementSibling.getBoundingClientRect().top - element.getBoundingClientRect().bottom), 8);
      }
      const referenceField = await page.locator('.house-mode-offset-select').first().boundingBox();
      for (const row of await page.locator('.house-mode-time-row').all()) {
        const alignment = await row.evaluate(element => {
          const label = element.querySelector(':scope > span');
          const field = element.querySelector('.house-mode-offset-select, .action-multi-summary');
          const labelStyle = getComputedStyle(label);
          const fieldStyle = getComputedStyle(field);
          return [label.getBoundingClientRect().left + parseFloat(labelStyle.paddingLeft), field.getBoundingClientRect().left + parseFloat(fieldStyle.borderLeftWidth) + parseFloat(fieldStyle.paddingLeft)];
        });
        assert.ok(Math.abs(alignment[0] - alignment[1]) < 1);
      }
      for (const dropdown of await page.locator('.house-mode-offset-select').all()) {
        assert.equal(await dropdown.evaluate(element => getComputedStyle(element).color), 'rgb(255, 255, 255)');
      }
      for (const field of await page.locator('#room-configurator-list .action-multi-summary').all()) {
        const box = await field.boundingBox();
        assert.equal(box.height, referenceField.height);
        assert.ok(Math.abs(box.width - referenceField.width) < 1);
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
        assert.equal(await page.locator('main').evaluate(element => getComputedStyle(element).paddingTop), width < 600 ? '54px' : '60px');
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
