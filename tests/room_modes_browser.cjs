const fs = require('node:fs');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.FHT_PLAYWRIGHT || 'playwright');

(async () => {
  const html = fs.readFileSync('future_homes_tech_app/web/index.html', 'utf8');
  const catalog = { bedroom: [{ id: 'sleep', label: 'Sleep' }, { id: 'quiet', label: 'Quiet' }, { id: 'toddler', label: 'Toddler' }] };
  const browser = await chromium.launch({ headless: true });
  try {
    for (const width of [1280, 390]) {
      const page = await browser.newPage({ viewport: { width, height: 900 } });
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      let enabled = ['sleep'];
      const posts = { modes: [], bedroom: [], scenes: [] };
      await page.route('**/*', route => {
        const request = route.request();
        const url = new URL(request.url());
        if (url.pathname === '/') return route.fulfill({ contentType: 'text/html', body: html });
        if (/\.(png|webp|jpg)$/.test(url.pathname)) return route.fulfill({ status: 404, body: '' });
        if (url.pathname === '/api/room-modes') {
          if (request.method() === 'POST') {
            const body = request.postDataJSON();
            posts.modes.push(body);
            enabled = body.enabled_modes;
            return route.fulfill({ json: { ok: true, settings: { 'Bedroom 3': enabled } } });
          }
          return route.fulfill({ json: { ok: true, rooms: [{ name: 'Bedroom 3', display_name: "Maverick's Bedroom", mode_type: 'bedroom', current_mode: 'Day' }], catalog, settings: { 'Bedroom 3': enabled }, current_modes: { 'Bedroom 3': 'Day' }, house_settings: {} } });
        }
        if (url.pathname === '/api/bedroom-modes') {
          if (request.method() === 'POST') { posts.bedroom.push(request.postDataJSON()); return route.fulfill({ json: { ok: true, saved: true, settings: {} } }); }
          return route.fulfill({ json: { ok: true, settings: { 'Bedroom 3': { toddler_enabled: false, toddler_brightness: 35 } }, current_modes: { 'Bedroom 3': 'Day' }, house_mode: 'Day', armed_status: {},
            door_sensors: [{ entity_id: 'binary_sensor.bedroom_3_door', friendly_name: 'Bedroom 3 Door', area: 'Bedroom 3' }, { entity_id: 'binary_sensor.kitchen_door', friendly_name: 'Kitchen Door', area: 'Kitchen' }],
            toddler_entities: { lights: [{ entity_id: 'light.bedroom_3_lamp', friendly_name: 'Bedroom 3 Lamp', area: 'Bedroom 3' }], chimes: [], indicator_effects: [], indicator_colors: [], indicator_brightness: [] },
            webhooks: { armed_away: false, armed_stay_kids: false } } });
        }
        if (url.pathname === '/api/room-scenes') {
          if (request.method() === 'POST') { posts.scenes.push(request.postDataJSON()); return route.fulfill({ json: { ok: true, settings: {} } }); }
          return route.fulfill({ json: { ok: true, catalog_revision: 1, scenes: enabled.map(mode => ({ area: 'Bedroom 3', mode, display_name: "Maverick's Bedroom", label: catalog.bedroom.find(item => item.id === mode)?.label || mode, settings: { targets: [], brightness_pct: 100 }, configured: false })) } });
        }
        if (url.pathname === '/api/home-configurator/catalog') return route.fulfill({ json: { ok: true, revision: 1, action_catalog: { light_groups: [{ entity_id: 'light.fht_bedroom_3_all_lights', friendly_name: 'FHT - Bedroom 3 All Lights', area: 'Bedroom 3' }], individual_lights: [], entity_targets: [], room_modes: [], wake_overrides: [] }, wake_catalog: {}, toddler_entities: {}, alarm_targets: [] } });
        return route.fulfill({ json: { ok: true, entities: [], floors: [], rooms: [], settings: {} } });
      });
      await page.goto('http://fht.test/');
      await page.waitForTimeout(800);
      if (width < 800) await page.locator('#mobile-nav-toggle').click();
      await page.locator('#settings-toggle').click();
      await page.locator('[data-view="room-modes"]').click();
      const card = page.locator('[data-room-mode-card][data-area="Bedroom 3"]');
      await card.waitFor();
      const dialog = page.locator('#room-mode-dialog');
      const toddler = card.locator('[data-room-mode="toddler"]');
      assert.equal(await card.locator('[data-room-mode-configure="toddler"]').isVisible(), false, 'Gear hidden while the mode is off');
      assert.equal(await card.locator('[data-room-mode-configure="sleep"]').isVisible(), true, 'Gear shown for an enabled mode');

      // Turning a mode on saves it and opens its settings.
      await toddler.check();
      await page.waitForSelector('#room-mode-dialog[open]');
      assert.deepEqual(posts.modes.at(-1), { area: 'Bedroom 3', enabled_modes: ['sleep', 'toddler'], mode_scope: 'room' });
      assert.equal(await page.locator('#room-mode-dialog-title').innerText(), "Maverick's Bedroom · Toddler");
      await dialog.locator('[data-bedroom-mode-panel="toddler_enabled"]').waitFor({ state: 'visible' });
      assert.equal(await dialog.locator('[data-bedroom-mode-panel]:not([hidden])').count(), 1, 'Only the chosen mode panel shows');
      assert.equal(await dialog.locator('[data-bedroom-field="toddler_enabled"]').isChecked(), true);
      assert.equal(await dialog.locator('.room-mode-card-header').isVisible(), false);
      assert.deepEqual(await dialog.locator('[data-bedroom-field="toddler_door_sensor"] option').evaluateAll(options => options.map(option => option.value).filter(Boolean)), ['binary_sensor.bedroom_3_door'], 'Only this bedroom\'s doors are offered');
      await dialog.locator('[data-bedroom-field="toddler_door_sensor"]').selectOption('binary_sensor.bedroom_3_door');
      await dialog.locator('[data-bedroom-list-field="toddler_light_entities"]').first().check();
      await dialog.locator('.bedroom-mode-save').click();
      await page.waitForFunction(() => document.querySelector('#room-mode-dialog .room-mode-enabled-count')?.textContent === 'Bedroom settings saved');
      const saved = posts.bedroom.at(-1);
      assert.equal(saved.area, 'Bedroom 3');
      assert.equal(saved.settings.toddler_enabled, true);
      assert.equal(saved.settings.toddler_door_sensor, 'binary_sensor.bedroom_3_door');
      assert.deepEqual(saved.settings.toddler_light_entities, ['light.bedroom_3_lamp']);
      if (process.env.FHT_SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.FHT_SCREENSHOT_DIR}/room-mode-dialog-${width}.png` });
      await page.locator('#room-mode-dialog-close').click();
      await page.waitForFunction(() => !document.getElementById('room-mode-dialog').open);
      assert.equal(await page.locator('#room-mode-dialog-body').innerHTML(), '');
      assert.equal(await card.locator('[data-room-mode-configure="toddler"]').isVisible(), true, 'Gear shows once the mode is on');

      // The gear on an ordinary mode opens its Room Scene without toggling the checkbox.
      const modeSaves = posts.modes.length;
      await card.locator('[data-room-mode-configure="sleep"]').click();
      await page.waitForSelector('#room-mode-dialog[open]');
      assert.equal(await page.locator('#room-mode-dialog-title').innerText(), "Maverick's Bedroom · Sleep");
      await dialog.locator('.room-scene-save').waitFor();
      assert.equal(await card.locator('[data-room-mode="sleep"]').isChecked(), true);
      assert.equal(posts.modes.length, modeSaves, 'Opening settings does not re-save the modes');
      await dialog.locator('[data-schedule-field="brightness"]').evaluate(input => { input.value = '40'; input.dispatchEvent(new Event('input', { bubbles: true })); input.dispatchEvent(new Event('change', { bubbles: true })); });
      await dialog.locator('.room-scene-save').click();
      await page.waitForFunction(() => document.querySelector('#room-mode-dialog .room-scene-save')?.textContent === 'Saved');
      assert.equal(posts.scenes.at(-1).area, 'Bedroom 3');
      assert.equal(posts.scenes.at(-1).mode, 'sleep');
      assert.equal(posts.scenes.at(-1).settings.brightness_pct, 40);
      await page.keyboard.press('Escape');
      await page.waitForFunction(() => !document.getElementById('room-mode-dialog').open);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true, 'No horizontal overflow');
      assert.deepEqual(errors, []);
      console.log(`Room Modes pop-up passed at ${width}px`);
      await page.close();
    }
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
