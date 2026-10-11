const fs = require('node:fs');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.FHT_PLAYWRIGHT || 'playwright');

// Room Configurator: a kitchen has its own modes, and any room can pick a parent room.
// A room with a parent shows the parent's modes it doesn't have itself, marked "from"
// the parent, each with its own settings pop-up. Picking a parent saves on its own.
(async () => {
  const html = fs.readFileSync('future_homes_tech_app/web/index.html', 'utf8');
  const catalog = {
    bedroom: [{ id: 'sleep', label: 'Sleep' }, { id: 'relax', label: 'Relax' }, { id: 'wake_up', label: 'Wake Up' }],
    kitchen: [{ id: 'sleep', label: 'Sleep' }, { id: 'cooking', label: 'Cooking' }, { id: 'dining', label: 'Dining' }, { id: 'entertaining', label: 'Entertaining' }, { id: 'movie', label: 'Movie' }],
  };
  const labels = Object.fromEntries(Object.values(catalog).flat().map(mode => [mode.id, mode.label]));
  const floorRooms = [
    { name: 'Kitchen', display_name: 'Kitchen', mode_type: 'kitchen', current_mode: 'Day' },
    { name: 'Dining Room', display_name: 'Dining Room', mode_type: '', current_mode: 'Day' },
    { name: 'Hallway', display_name: 'Hallway', mode_type: '', current_mode: 'Day' },
  ];
  const browser = await chromium.launch({ headless: true });
  try {
    for (const width of [1280, 390]) {
      const page = await browser.newPage({ viewport: { width, height: 900 } });
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      const settings = { Kitchen: ['cooking', 'movie', 'sleep'] };
      const parents = {};
      const parentPosts = [];
      const inherited = () => Object.fromEntries(Object.entries(parents).map(([child, parent]) => [child, (settings[parent] || []).filter(mode => !(settings[child] || []).includes(mode))]));
      await page.route('**/*', route => {
        const request = route.request();
        const url = new URL(request.url());
        if (url.pathname === '/') return route.fulfill({ contentType: 'text/html', body: html });
        if (/\.(png|webp|jpg)$/.test(url.pathname)) return route.fulfill({ status: 404, body: '' });
        if (url.pathname === '/api/home-configurator/index') {
          return route.fulfill({ json: { ok: true, room_count: 3, house_mode: 'Day', security_mode: 'Disarmed', house_settings: {}, floors: [
            { name: 'Main Floor', floor_id: 'main', rooms: floorRooms },
          ] } });
        }
        if (url.pathname === '/api/room-parents' && request.method() === 'POST') {
          const body = request.postDataJSON();
          parentPosts.push(body);
          if (body.parent) parents[body.area] = body.parent; else delete parents[body.area];
          return route.fulfill({ json: { ok: true, parents, inherited: inherited() } });
        }
        if (url.pathname === '/api/room-modes') {
          const rooms = floorRooms.filter(room => room.mode_type || parents[room.name] || settings[room.name]);
          return route.fulfill({ json: { ok: true, rooms, catalog, settings, parents, inherited: inherited(), schedules: {}, current_modes: {}, house_settings: {} } });
        }
        if (url.pathname === '/api/room-scenes') {
          const scenes = floorRooms.flatMap(room => ['day', 'night', ...(settings[room.name] || []), ...(inherited()[room.name] || [])].map(mode => ({
            area: room.name, mode, display_name: room.display_name, label: { day: 'Day', night: 'Night' }[mode] || labels[mode], settings: { targets: [], brightness_pct: 100 }, configured: false,
          })));
          return route.fulfill({ json: { ok: true, catalog_revision: 1, room_devices: { 'Dining Room': [{ entity_id: 'cover.dining_shade', domain: 'cover', name: 'Window Shade' }] }, scenes } });
        }
        if (url.pathname === '/api/room-controls') {
          const room = url.searchParams.get('room');
          return route.fulfill({ json: { ok: true, room, display_name: room, entities: [], door_sensors: [], door_mode_options: [], enabled_room_modes: [], catalog_revision: 1, control_settings: {}, presence: { assignments: {}, timings: {}, mode_settings: {} } } });
        }
        if (url.pathname === '/api/home-configurator/catalog') return route.fulfill({ json: { ok: true, revision: 1, action_catalog: { light_groups: [], individual_lights: [], entity_targets: [], room_modes: [], wake_overrides: [] }, wake_catalog: {}, toddler_entities: {}, alarm_targets: [] } });
        return route.fulfill({ json: { ok: true, entities: [], floors: [], rooms: [], settings: {} } });
      });
      await page.addInitScript(() => { try { localStorage.setItem('fht-room-config-room', 'Kitchen'); } catch (_) {} });
      await page.goto('http://fht.test/');
      await page.waitForTimeout(800);
      if (width < 800) await page.locator('#mobile-nav-toggle').click();
      await page.locator('#settings-toggle').click();
      await page.locator('[data-view="room-config"]').click();
      const picker = page.locator('#room-config-picker');
      await page.waitForFunction(() => !document.getElementById('room-config-picker').disabled);
      await picker.selectOption('Kitchen');

      // The kitchen's own modes.
      const kitchen = page.locator('#room-config-list [data-room-mode-card][data-area="Kitchen"]');
      await kitchen.waitFor();
      assert.deepEqual(await kitchen.locator('[data-room-mode]').evaluateAll(boxes => boxes.map(box => box.dataset.roomMode)),
        ['sleep', 'cooking', 'dining', 'entertaining', 'movie']);
      assert.equal(await kitchen.locator('[data-room-mode="cooking"]').isChecked(), true);
      assert.equal(await kitchen.locator('[data-room-parent]').inputValue(), '', 'The kitchen has no parent room yet');
      if (process.env.FHT_SCREENSHOT_DIR) await kitchen.screenshot({ path: `${process.env.FHT_SCREENSHOT_DIR}/kitchen-modes-${width}.png` });

      // A dining room with no modes of its own picks the kitchen as its parent.
      await picker.selectOption('Dining Room');
      const dining = page.locator('#room-config-list [data-room-mode-card][data-area="Dining Room"]');
      await dining.waitFor();
      assert.equal(await dining.locator('[data-room-mode]').count(), 0, 'No modes of its own');
      assert.deepEqual(await dining.locator('[data-room-parent] option').evaluateAll(options => options.map(option => option.value)), ['', 'Kitchen', 'Hallway'], 'Every other room can be the parent');
      await dining.locator('[data-room-parent]').selectOption('Kitchen');
      await page.waitForSelector('#room-config-list [data-room-mode-card][data-area="Dining Room"] [data-room-inherited-mode]');
      assert.deepEqual(parentPosts, [{ area: 'Dining Room', parent: 'Kitchen' }], 'The parent saves on its own');
      const inheritedModes = dining.locator('[data-room-inherited-mode]');
      assert.deepEqual(await inheritedModes.evaluateAll(boxes => boxes.map(box => [box.dataset.roomInheritedMode, box.checked, box.disabled])),
        [['cooking', true, true], ['movie', true, true], ['sleep', true, true]]);
      assert.match(await dining.locator('.room-mode-inherited', { hasText: 'Movie' }).innerText(), /from Kitchen/);
      assert.equal(await dining.locator('[data-room-parent]').inputValue(), 'Kitchen');
      if (process.env.FHT_SCREENSHOT_DIR) await dining.screenshot({ path: `${process.env.FHT_SCREENSHOT_DIR}/dining-parent-${width}.png` });

      // Each mode taken from the parent has its own settings for this room.
      await dining.locator('[data-room-mode-configure="movie"]').click();
      await page.waitForSelector('#room-mode-dialog[open]');
      await page.waitForFunction(() => !document.getElementById('room-mode-dialog-body').textContent.includes('Loading'));
      assert.equal(await page.locator('#room-mode-dialog-title').innerText(), 'Dining Room · Movie');
      assert.equal(await page.locator('#room-mode-dialog [data-mode-schedule]').count(), 1, 'It can be scheduled like any mode');
      if (process.env.FHT_SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.FHT_SCREENSHOT_DIR}/dining-movie-${width}.png` });
      await page.locator('#room-mode-dialog-close').click();

      // Clearing the parent takes its modes away.
      await dining.locator('[data-room-parent]').selectOption('');
      await page.waitForFunction(() => !document.querySelector('#room-config-list [data-room-inherited-mode]'));
      assert.deepEqual(parentPosts.at(-1), { area: 'Dining Room', parent: '' });
      assert.deepEqual(errors, []);
      await page.close();
    }
    console.log('Kitchen modes and parent rooms passed');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exit(1); });
