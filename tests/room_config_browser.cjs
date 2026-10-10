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
      const posts = { modes: [], aliases: [], scenes: [], doors: [] };
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
          const doorModes = [{ id: 'day', label: 'Day' }, { id: 'night', label: 'Night' }];
          const doorsHere = room === 'Bedroom 3' ? [door] : [];
          return route.fulfill({ json: { ok: true, room, display_name: room, entities: doorsHere, door_sensors: doorsHere, door_mode_options: doorModes, enabled_room_modes: [], catalog_revision: 1, control_settings: {} } });
        }
        if (url.pathname === '/api/switch-light-groups' && request.method() === 'POST') {
          posts.doors.push(request.postDataJSON());
          return page.evaluate(() => { window.__doorSaves = (window.__doorSaves || 0) + 1; }).then(() => route.fulfill({ json: { ok: true } }));
        }
        if (url.pathname === '/api/room-aliases' && request.method() === 'POST') {
          posts.aliases.push(request.postDataJSON());
          return route.fulfill({ json: { ok: true } });
        }
        if (url.pathname === '/api/room-scenes') {
          if (request.method() === 'POST') { posts.scenes.push(request.postDataJSON()); return route.fulfill({ json: { ok: true, settings: {} } }); }
          return route.fulfill({ json: { ok: true, catalog_revision: 1, scenes: enabled.map(mode => ({ area: 'Bedroom 3', mode, display_name: "Maverick's Bedroom", label: catalog.bedroom.find(item => item.id === mode)?.label || mode, settings: { targets: [], brightness_pct: 100 }, configured: false })) } });
        }
        if (url.pathname === '/api/home-configurator/catalog') return route.fulfill({ json: { ok: true, revision: 1, action_catalog: { light_groups: [], individual_lights: [], entity_targets: [], room_modes: [], wake_overrides: [] }, wake_catalog: {}, toddler_entities: {}, alarm_targets: [] } });
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
      const modes = page.locator('#room-config-list [data-room-mode-card][data-area="Bedroom 3"]');
      assert.equal(await modes.locator('h2').innerText(), 'Room Modes');
      assert.equal(await modes.locator('[data-room-mode="sleep"]').isChecked(), true);
      assert.equal(await page.locator('#room-config-list button', { hasText: /^Save$/ }).count(), 0, 'No Save buttons');

      // Turning a mode on saves straight away and opens its settings.
      await modes.locator('[data-room-mode="quiet"]').check();
      await page.waitForSelector('#room-mode-dialog[open]');
      assert.deepEqual(posts.modes.at(-1), { area: 'Bedroom 3', enabled_modes: ['sleep', 'quiet'], mode_scope: 'room' });
      assert.equal(await page.locator('#room-mode-dialog-title').innerText(), "Maverick's Bedroom · Quiet");
      await page.locator('#room-mode-dialog-close').click();
      await page.waitForFunction(() => !document.getElementById('room-mode-dialog').open);

      // The room's doors are on the page, with the same controls as the Doors page, and they save on their own.
      const doors = page.locator('#room-config-list [data-room-config-doors]');
      await doors.locator('.door-timeout').waitFor({ state: 'attached' });
      assert.equal(await page.locator('#room-config-list [data-room-config-scenes], #room-config-list [data-room-scene-card]').count(), 0, 'No Scenes card');
      assert.deepEqual(doorRequests, ['Bedroom 3']);
      await doors.locator('.door-timeout').evaluate(select => { select.value = '5'; select.dispatchEvent(new Event('change', { bubbles: true })); });
      await page.waitForFunction(() => window.__doorSaves > 0);
      assert.equal(posts.doors.at(-1).assignment_id, 'door:binary_sensor.bedroom_3_door');
      assert.equal(posts.doors.at(-1).timeout_minutes, 5);
      const menuNow = await page.locator('#settings-submenu [data-view]').evaluateAll(buttons => buttons.map(button => button.dataset.view));
      assert.ok(!menuNow.includes('room-modes') && !menuNow.includes('scenes'), 'Room Modes and Scenes pages are gone');

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
      assert.match(await doors.evaluate(card => getComputedStyle(card).gridColumn), /1 \/ -1|span/, 'Doors spans the page');
      await picker.selectOption('Kitchen');
      await page.locator('[data-room-config-card][data-room="Kitchen"]').waitFor();
      assert.match(await page.locator('#room-config-list .room-config-note').first().innerText(), /bedrooms/);
      await page.waitForFunction(() => /No doors/.test(document.querySelector('#room-config-list [data-room-config-doors]')?.textContent || ''));
      assert.equal(await page.evaluate(() => localStorage.getItem('fht-room-config-room')), 'Kitchen', 'The picked room is remembered');
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true, 'No horizontal overflow');
      assert.deepEqual(errors, []);
      console.log(`Room Configurator passed at ${width}px`);
      await page.close();
    }
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
