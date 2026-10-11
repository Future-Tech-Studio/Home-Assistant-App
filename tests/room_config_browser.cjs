const fs = require('node:fs');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.FHT_PLAYWRIGHT || 'playwright');

// Room Configurator: a room picker under Home Configurator, with the picked room's
// name and modes. Changes save on their own; there is no Save button.
(async () => {
  const html = fs.readFileSync('future_homes_tech_app/web/index.html', 'utf8');
  const catalog = { bedroom: [{ id: 'sleep', label: 'Sleep' }, { id: 'quiet', label: 'Quiet' }] };
  const browser = await chromium.launch({ headless: true });
  try {
    for (const width of [1280, 390]) {
      const page = await browser.newPage({ viewport: { width, height: 900 } });
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      let enabled = ['sleep'];
      const posts = { modes: [], aliases: [], scenes: [], doors: [], presence: [], schedules: [] };
      const doorRequests = [];
      await page.route('**/*', route => {
        const request = route.request();
        const url = new URL(request.url());
        if (url.pathname === '/') return route.fulfill({ contentType: 'text/html', body: html });
        if (/\.(png|webp|jpg)$/.test(url.pathname)) return route.fulfill({ status: 404, body: '' });
        if (url.pathname === '/api/home-configurator/index') {
          return route.fulfill({ json: { ok: true, room_count: 3, house_mode: 'Day', security_mode: 'Disarmed', house_settings: {}, floors: [
            { name: 'Whole Home', floor_id: '', rooms: [] },
            { name: 'Upstairs', floor_id: 'upstairs', rooms: [
              { name: 'Bedroom 3', display_name: "Maverick's Bedroom", mode_type: 'bedroom', current_mode: 'Day' },
              { name: 'Bathroom 2', display_name: 'Bathroom 2', mode_type: '', current_mode: '' },
            ] },
            { name: 'Main Floor', floor_id: 'main', rooms: [{ name: 'Kitchen', display_name: 'Kitchen', mode_type: '', current_mode: '' }] },
          ] } });
        }
        if (url.pathname === '/api/room-modes') {
          if (request.method() === 'POST') {
            const body = request.postDataJSON();
            posts.modes.push(body);
            enabled = body.enabled_modes;
            return route.fulfill({ json: { ok: true, settings: { 'Bedroom 3': enabled } } });
          }
          return route.fulfill({ json: { ok: true, rooms: [{ name: 'Bedroom 3', display_name: "Maverick's Bedroom", mode_type: 'bedroom', current_mode: 'Day' }], catalog, settings: { 'Bedroom 3': enabled }, current_modes: { 'Bedroom 3': 'Day' }, house_settings: {} } });
        }
        if (url.pathname === '/api/room-controls' && url.searchParams.get('kind') === 'doors') {
          const room = url.searchParams.get('room');
          doorRequests.push(room);
          const door = { entity_id: 'binary_sensor.bedroom_3_door', domain: 'binary_sensor', area: 'Bedroom 3', original_area: 'Bedroom 3', friendly_name: 'Bedroom 3 Door', state: 'off' };
          const doorModes = [{ id: 'day', label: 'Day' }, { id: 'night', label: 'Night' }, { id: 'room:bedroom_3:sleep', label: 'Sleep Mode' }];
          const doorsHere = room === 'Bedroom 3' ? [door] : [];
          // The door already turns the room's lights on: 100% in Day, 50% in Night.
          const doorId = 'door:binary_sensor.bedroom_3_door';
          const lights = ['light.fht_bedroom_3_lights'];
          const control_settings = {
            action_assignments: { [`${doorId}|day`]: lights, [`${doorId}|night`]: lights },
            action_settings: { [`${doorId}|day`]: { enabled: true, brightness_pct: 100, timeout_minutes: 0 }, [`${doorId}|night`]: { enabled: true, brightness_pct: 50, timeout_minutes: 0 } },
          };
          return route.fulfill({ json: { ok: true, room, display_name: room, entities: doorsHere, door_sensors: doorsHere, door_mode_options: doorModes, enabled_room_modes: [], catalog_revision: 1, control_settings } });
        }
        if (url.pathname === '/api/room-controls' && url.searchParams.get('kind') === 'presence') {
          const room = url.searchParams.get('room');
          const sensor = { entity_id: 'binary_sensor.bedroom_3_presence', domain: 'binary_sensor', device_class: 'occupancy', area: 'Bedroom 3', original_area: 'Bedroom 3', friendly_name: 'Bedroom 3 Presence', state: 'off' };
          return route.fulfill({ json: { ok: true, room, display_name: room, entities: room === 'Bedroom 3' ? [sensor] : [], enabled_room_modes: [], catalog_revision: 1,
            presence: { assignments: { 'binary_sensor.bedroom_3_presence': ['light.fht_bedroom_3_lights'] }, timings: {}, mode_settings: {} } } });
        }
        if (url.pathname === '/api/presence-light-groups' && request.method() === 'POST') {
          posts.presence.push(request.postDataJSON());
          return route.fulfill({ json: { ok: true } });
        }
        if (url.pathname === '/api/switch-light-groups' && request.method() === 'POST') {
          posts.doors.push(request.postDataJSON());
          return page.evaluate(() => { window.__doorSaves = (window.__doorSaves || 0) + 1; }).then(() => route.fulfill({ json: { ok: true } }));
        }
        if (url.pathname === '/api/room-mode-schedules' && request.method() === 'POST') {
          const body = request.postDataJSON();
          posts.schedules.push(body);
          return route.fulfill({ json: { ok: true, schedules: { [body.area]: { [body.mode]: body.schedule } } } });
        }
        if (url.pathname === '/api/room-aliases' && request.method() === 'POST') {
          posts.aliases.push(request.postDataJSON());
          return route.fulfill({ json: { ok: true } });
        }
        if (url.pathname === '/api/room-scenes') {
          if (request.method() === 'POST') { posts.scenes.push(request.postDataJSON()); return route.fulfill({ json: { ok: true, settings: {} } }); }
          const roomDevices = { 'Bedroom 3': [
            { entity_id: 'fan.bedroom_3_ceiling_fan', domain: 'fan', name: 'Ceiling Fan' },
            { entity_id: 'cover.bedroom_3_shade', domain: 'cover', name: 'Window Shade' },
            { entity_id: 'lock.bedroom_3_door', domain: 'lock', name: 'Door Lock' },
          ] };
          return route.fulfill({ json: { ok: true, catalog_revision: 1, room_devices: roomDevices, scenes: ['day', 'night', ...enabled].map(mode => ({ area: 'Bedroom 3', mode, display_name: "Maverick's Bedroom", label: { day: 'Day', night: 'Night' }[mode] || catalog.bedroom.find(item => item.id === mode)?.label || mode, settings: { targets: [], brightness_pct: 100 }, configured: false })) } });
        }
        if (url.pathname === '/api/home-configurator/catalog') return route.fulfill({ json: { ok: true, revision: 1, action_catalog: { light_groups: [{ entity_id: 'light.fht_bedroom_3_lights', friendly_name: "Maverick's Bedroom Lights", area: 'Bedroom 3' }], individual_lights: [], entity_targets: [], room_modes: [], wake_overrides: [] }, wake_catalog: {}, toddler_entities: {}, alarm_targets: [] } });
        return route.fulfill({ json: { ok: true, entities: [], floors: [], rooms: [], settings: {} } });
      });
      await page.goto('http://fht.test/');
      await page.waitForTimeout(800);
      if (width < 800) await page.locator('#mobile-nav-toggle').click();
      await page.locator('#settings-toggle').click();
      const menu = await page.locator('#settings-submenu [data-view]').evaluateAll(buttons => buttons.map(button => button.dataset.view));
      assert.equal(menu[menu.indexOf('rooms') + 1], 'room-config', 'Room Configurator sits right under Home Configurator');
      await page.locator('[data-view="room-config"]').click();

      const picker = page.locator('#room-config-picker');
      await page.waitForFunction(() => !document.getElementById('room-config-picker').disabled);
      assert.deepEqual(await picker.locator('optgroup').evaluateAll(groups => groups.map(group => group.label)), ['Upstairs', 'Main Floor'], 'Rooms are grouped by floor, without Whole Home');
      assert.equal(await picker.inputValue(), 'Bedroom 3');
      const roomCard = page.locator('[data-room-config-card][data-room="Bedroom 3"]');
      await roomCard.waitFor();
      assert.deepEqual(await roomCard.locator('.room-config-field > span').allInnerTexts(), ['Display Name', 'Current Mode'], 'Room card shows only the display name and current mode');
      const modes = page.locator('#room-config-list [data-room-mode-card][data-area="Bedroom 3"]');
      assert.equal(await modes.locator('h2').innerText(), 'Room Modes');
      assert.equal(await modes.locator('[data-room-mode="sleep"]').isChecked(), true);
      assert.equal(await page.locator('#room-config-list button', { hasText: /^Save$/ }).count(), 0, 'No Save buttons');
      // The house's Day and Night lead the list, always on, each with its own settings.
      assert.deepEqual(await modes.locator('.room-mode-option').evaluateAll(options => options.slice(0, 3).map(option => option.textContent.replace('⚙', '').trim())), ['Day', 'Night', 'Sleep']);
      assert.equal(await modes.locator('[data-room-house-mode="night"]').isDisabled(), true);
      assert.equal(await modes.locator('[data-room-house-mode="night"]').isChecked(), true);
      await modes.locator('[data-room-mode-configure="night"]').click();
      await page.waitForSelector('#room-mode-dialog[open] .room-scene-device-row');
      assert.equal(await page.locator('#room-mode-dialog-title').innerText(), "Maverick's Bedroom · Night");
      assert.equal(await page.locator('#room-mode-dialog [data-mode-schedule]').count(), 0, 'House Day and Night follow the house, not a schedule');
      await page.locator('[data-room-scene-device="fan.bedroom_3_ceiling_fan"]').selectOption('off');
      for (let tries = 0; tries < 50 && posts.scenes.at(-1)?.mode !== 'night'; tries += 1) await page.waitForTimeout(50);
      assert.deepEqual([posts.scenes.at(-1).mode, posts.scenes.at(-1).settings.devices], ['night', { 'fan.bedroom_3_ceiling_fan': 'off' }]);
      // The pop-up carries each door's light for this mode, starting from what was saved.
      const doorRule = page.locator('#room-mode-dialog [data-room-mode-doors] [data-door-rule="night"]');
      await doorRule.waitFor();
      assert.equal(await doorRule.locator('output').innerText(), '50%');
      assert.equal(await doorRule.locator('.door-rule-enabled').isChecked(), true);
      await doorRule.locator('.door-rule-brightness').evaluate(input => { input.value = '30'; input.dispatchEvent(new Event('input', { bubbles: true })); input.dispatchEvent(new Event('change', { bubbles: true })); });
      for (let tries = 0; tries < 50 && posts.doors.at(-1)?.door_modes?.night?.brightness_pct !== 30; tries += 1) await page.waitForTimeout(50);
      const nightSave = posts.doors.at(-1);
      assert.equal(nightSave.assignment_id, 'door:binary_sensor.bedroom_3_door');
      assert.equal(nightSave.door_modes.night.brightness_pct, 30, 'Night brightness saves on its own');
      assert.equal(nightSave.door_modes.day.brightness_pct, 100, 'Day keeps its brightness');
      assert.deepEqual(nightSave.actions, ['light.fht_bedroom_3_lights'], 'The door keeps its action');
      if (process.env.FHT_SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.FHT_SCREENSHOT_DIR}/room-mode-night-${width}.png` });
      await page.locator('#room-mode-dialog-close').click();
      await page.waitForFunction(() => !document.getElementById('room-mode-dialog').open);
      assert.equal(posts.modes.length, 0, 'Day and Night never change the saved room modes');

      // Turning a mode on saves straight away and opens its settings.
      await modes.locator('[data-room-mode="quiet"]').check();
      await page.waitForSelector('#room-mode-dialog[open]');
      assert.deepEqual(posts.modes.at(-1), { area: 'Bedroom 3', enabled_modes: ['sleep', 'quiet'], mode_scope: 'room' });
      assert.equal(await page.locator('#room-mode-dialog-title').innerText(), "Maverick's Bedroom · Quiet");
      // Every device in the room is listed with "Leave as is" or a state, and a choice saves on its own.
      const deviceRows = page.locator('#room-mode-dialog .room-scene-device-row');
      await deviceRows.first().waitFor();
      assert.deepEqual(await deviceRows.locator('span').allTextContents(), ['Ceiling Fan', 'Window Shade', 'Door Lock']);
      assert.deepEqual(await deviceRows.locator('select').evaluateAll(selects => selects.map(select => [...select.options].map(option => option.text))),
        [['Leave as is', 'On', 'Off'], ['Leave as is', 'Open', 'Closed'], ['Leave as is', 'Locked']]);
      await page.locator('[data-room-scene-device="fan.bedroom_3_ceiling_fan"]').selectOption('on');
      await page.waitForFunction(() => /runs when this mode starts/.test(document.querySelector('#room-mode-dialog .room-scene-feedback')?.textContent || ''));
      assert.deepEqual(posts.scenes.at(-1).settings.devices, { 'fan.bedroom_3_ceiling_fan': 'on' });
      assert.equal(posts.scenes.at(-1).mode, 'quiet');
      await page.locator('[data-room-scene-device="cover.bedroom_3_shade"]').selectOption('closed');
      for (let tries = 0; tries < 50 && !posts.scenes.at(-1).settings.devices['cover.bedroom_3_shade']; tries += 1) await page.waitForTimeout(50);
      assert.deepEqual(posts.scenes.at(-1).settings.devices, { 'fan.bedroom_3_ceiling_fan': 'on', 'cover.bedroom_3_shade': 'closed' });
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true, 'Pop-up fits the screen');
      if (process.env.FHT_SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.FHT_SCREENSHOT_DIR}/room-mode-devices-${width}.png` });

      // The mode can start on a weekly schedule, set at the top of its pop-up; changes save on their own.
      const schedule = page.locator('#room-mode-dialog [data-mode-schedule]');
      assert.equal(await page.locator('#room-mode-dialog-body > *').first().evaluate(node => node.hasAttribute('data-mode-schedule')), true, 'Schedule sits at the top');
      assert.equal(await schedule.locator('[data-mode-schedule-body]').isHidden(), true);
      await schedule.locator('[data-mode-schedule-enabled]').check();
      assert.deepEqual(await schedule.locator('tbody th').allTextContents(), ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']);
      assert.equal(await schedule.locator('[data-mode-schedule-day-enabled]:checked').count(), 7, 'Turning the schedule on picks every day');
      await schedule.locator('[data-mode-schedule-pick="weekdays"]').click();
      const checkedDays = () => schedule.locator('[data-mode-schedule-day]').evaluateAll(rows => rows.filter(row => row.querySelector('input').checked).map(row => row.dataset.modeScheduleDay));
      assert.deepEqual(await checkedDays(), ['monday', 'tuesday', 'wednesday', 'thursday', 'friday']);
      await schedule.locator('[data-mode-schedule-day="monday"] [data-mode-schedule-time]').click();
      await page.waitForSelector('#climate-time-dialog[open]');
      await page.locator('#climate-time-hour').selectOption('8');
      await page.locator('#climate-time-minute').selectOption('30');
      await page.locator('#climate-time-period').selectOption('PM');
      await page.locator('#climate-time-save').click();
      await page.waitForFunction(() => !document.getElementById('climate-time-dialog').open);
      await schedule.locator('[data-mode-schedule-day="monday"] [data-mode-schedule-copy]').click();
      assert.deepEqual(await schedule.locator('[data-mode-schedule-time]').allTextContents(), Array(7).fill('8:30 PM'), 'Apply to all copies Monday\'s time');
      await page.waitForFunction(() => document.querySelector('[data-mode-schedule-status]')?.textContent === 'Saved');
      const saved = posts.schedules.at(-1);
      assert.deepEqual([saved.area, saved.mode, saved.schedule.enabled], ['Bedroom 3', 'quiet', true]);
      assert.deepEqual(saved.schedule.days.monday, { enabled: true, time: '20:30' });
      assert.deepEqual(saved.schedule.days.saturday, { enabled: false, time: '20:30' });
      assert.ok(posts.schedules.length <= 3, 'Quick edits are saved together');
      await schedule.locator('[data-mode-schedule-pick="weekend"]').click();
      assert.deepEqual(await checkedDays(), ['sunday', 'saturday']);
      await page.waitForFunction(() => document.querySelector('[data-mode-schedule-status]')?.textContent === 'Saved');
      await schedule.locator('[data-mode-schedule-pick="all"]').click();
      await page.waitForFunction(() => document.querySelector('[data-mode-schedule-status]')?.textContent === 'Saved');
      assert.equal(Object.values(posts.schedules.at(-1).schedule.days).every(day => day.enabled), true);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true, 'Schedule fits the screen');
      assert.equal(await schedule.evaluate(node => node.scrollWidth <= node.clientWidth + 1), true, 'Schedule table fits the pop-up');
      if (process.env.FHT_SCREENSHOT_DIR) {
        await page.locator('#room-mode-dialog').evaluate(dialog => { dialog.scrollTop = 0; });
        await page.screenshot({ path: `${process.env.FHT_SCREENSHOT_DIR}/mode-schedule-${width}.png` });
      }
      // A tap inside the card leaves it open; a tap outside the card closes it.
      await page.locator('#room-mode-dialog-title').click();
      assert.equal(await page.locator('#room-mode-dialog').evaluate(dialog => dialog.open), true, 'A tap inside keeps the pop-up open');
      await page.mouse.click(4, 4);
      await page.waitForFunction(() => !document.getElementById('room-mode-dialog').open);

      // The room's doors are on the page, with the same controls as the Doors page, and they save on their own.
      const doors = page.locator('#room-config-list [data-room-config-doors]');
      await doors.locator('.door-timeout').waitFor({ state: 'attached' });
      assert.equal(await page.locator('#room-config-list [data-room-config-scenes], #room-config-list [data-room-scene-card]').count(), 0, 'No Scenes card');
      assert.deepEqual([...new Set(doorRequests)], ['Bedroom 3']);
      assert.equal(await doors.locator('.door-rule-brightness').count(), 0, 'Door brightness lives in each mode, not on the Doors card');
      await doors.locator('.door-timeout').evaluate(select => { select.value = '5'; select.dispatchEvent(new Event('change', { bubbles: true })); });
      await page.waitForFunction(() => window.__doorSaves > 0);
      assert.equal(posts.doors.at(-1).assignment_id, 'door:binary_sensor.bedroom_3_door');
      assert.equal(posts.doors.at(-1).timeout_minutes, 5);
      if (process.env.FHT_SCREENSHOT_DIR) await doors.screenshot({ path: `${process.env.FHT_SCREENSHOT_DIR}/doors-card-${width}.png` });
      const menuNow = await page.locator('#settings-submenu [data-view]').evaluateAll(buttons => buttons.map(button => button.dataset.view));
      assert.ok(!menuNow.includes('room-modes') && !menuNow.includes('scenes'), 'Room Modes and Scenes pages are gone');

      // Presence sits under Doors with the same controls as the old Presence page, and a change saves on its own.
      assert.ok(!menuNow.includes('presence'), 'Presence has no menu page');
      const presence = page.locator('#room-config-list [data-room-config-presence]');
      assert.equal(await presence.locator('h2').innerText(), 'Presence');
      assert.equal(await page.locator('#room-config-list > article').evaluateAll(cards => cards.at(-1).matches('[data-room-config-presence]')), true, 'Presence comes after Doors');
      const sensor = presence.locator('[data-presence-card="binary_sensor.bedroom_3_presence"]');
      await sensor.locator('.activation-delay-input').waitFor();
      assert.deepEqual(await sensor.locator('.presence-group-select').evaluate(select => [...select.selectedOptions].map(option => option.value)), ['light.fht_bedroom_3_lights']);
      await sensor.locator('.activation-delay-input').selectOption('3');
      await page.waitForFunction(() => document.querySelector('[data-room-config-presence-state]')?.textContent === 'Presence assignment saved.');
      assert.equal(posts.presence.at(-1).presence_entity_id, 'binary_sensor.bedroom_3_presence');
      assert.equal(posts.presence.at(-1).activation_delay, 180);
      assert.deepEqual(posts.presence.at(-1).target_entity_ids, ['light.fht_bedroom_3_lights']);
      await sensor.locator('.presence-mode-brightness[data-presence-mode="night"]').evaluate(slider => { slider.value = '40'; slider.dispatchEvent(new Event('input', { bubbles: true })); });
      assert.equal(await sensor.locator('.presence-mode-rule', { has: page.locator('[data-presence-mode="night"]') }).locator('output').innerText(), '40%');
      assert.equal(await page.locator('#room-config-list button', { hasText: /^Save$/ }).count(), 0, 'Presence has no Save button');

      // The display name saves when the field is left.
      const alias = roomCard.locator('.room-alias-input');
      await alias.fill('Maverick Room');
      await alias.press('Enter');
      await page.waitForFunction(() => document.querySelector('[data-room-config-card] .room-mode-save-status')?.textContent === 'Display name saved.');
      assert.deepEqual(posts.aliases.at(-1), { room: 'Bedroom 3', alias: 'Maverick Room' });
      assert.equal(await picker.locator('option[value="Bedroom 3"]').innerText(), 'Maverick Room');

      // A room without modes says so; the two cards stack on a phone and sit side by side on a wide screen.
      if (process.env.FHT_SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.FHT_SCREENSHOT_DIR}/room-config-${width}.png`, fullPage: true });
      const columns = await page.evaluate(() => getComputedStyle(document.getElementById('room-config-list')).gridTemplateColumns.split(' ').length);
      assert.equal(columns, width < 980 ? 1 : 2);
      const widths = await page.evaluate(() => ['[data-room-config-card]', '[data-room-mode-card]', '[data-room-config-doors]'].map(selector => Math.round(document.querySelector(`#room-config-list ${selector}`).getBoundingClientRect().width)));
      assert.ok(Math.abs(widths[2] - widths[0]) <= 1 && Math.abs(widths[1] - widths[0]) <= 1, `Doors is one column wide, like Room and Room Modes (${widths})`);
      assert.match(await presence.evaluate(card => getComputedStyle(card).gridColumn), /1 \/ -1|span/, 'Presence spans the page');
      await picker.selectOption('Kitchen');
      await page.locator('[data-room-config-card][data-room="Kitchen"]').waitFor();
      assert.match(await page.locator('#room-config-list .room-config-note').first().innerText(), /parent room/);
      await page.waitForFunction(() => /No doors/.test(document.querySelector('#room-config-list [data-room-config-doors]')?.textContent || ''));
      await page.waitForFunction(() => /No exhaust fans in this room/.test(document.querySelector('#room-config-list [data-room-config-environment]')?.textContent || ''));
      await page.waitForFunction(() => document.querySelector('#room-config-list [data-room-config-presence] .room-controls-body')?.textContent.trim() === 'No presence sensors in this room.');
      assert.equal(await page.evaluate(() => localStorage.getItem('fht-room-config-room')), 'Kitchen', 'The picked room is remembered');
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true, 'No horizontal overflow');
      assert.deepEqual(errors, []);
      console.log(`Room Configurator passed at ${width}px`);
      // A door save can still be in flight as the page closes; let it go quietly.
      await page.unrouteAll({ behavior: "ignoreErrors" });
      await page.close();
    }
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
