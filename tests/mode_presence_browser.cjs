const fs = require('node:fs');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.FHT_PLAYWRIGHT || 'playwright');

// Room Configurator → a mode's pop-up shows each presence sensor with its own
// on/off, lights, delays, brightness, and tone for that mode, and saves on its own.
(async () => {
  const html = fs.readFileSync('future_homes_tech_app/web/index.html', 'utf8');
  const catalog = { bedroom: [{ id: 'sleep', label: 'Sleep' }, { id: 'movie', label: 'Movie' }] };
  const room = { name: 'Bedroom 3', display_name: "Maverick's Bedroom", mode_type: 'bedroom', current_mode: 'Day' };
  const lights = [
    { entity_id: 'light.fht_bedroom_3_all_lights', friendly_name: 'FHT - Bedroom 3 All Lights', area: 'Bedroom 3' },
    { entity_id: 'light.bedroom_3_fan_light', friendly_name: 'Bedroom 3 Fan Light', area: 'Bedroom 3' },
  ];
  const sensors = [
    { entity_id: 'binary_sensor.fht_bedroom_3_presence_group', domain: 'binary_sensor', friendly_name: 'FHT - Bedroom 3 Presence Group', area: 'Bedroom 3', device_class: 'occupancy', members: ['binary_sensor.bedroom_3_pir_1', 'binary_sensor.bedroom_3_pir_2'], state: 'off' },
    { entity_id: 'binary_sensor.bedroom_3_pir_1', domain: 'binary_sensor', friendly_name: 'Bedroom 3 PIR 1', area: 'Bedroom 3', device_class: 'occupancy', state: 'off' },
    { entity_id: 'binary_sensor.bedroom_3_pir_2', domain: 'binary_sensor', friendly_name: 'Bedroom 3 PIR 2', area: 'Bedroom 3', device_class: 'occupancy', state: 'off' },
  ];
  const browser = await chromium.launch({ headless: true });
  try {
    for (const width of [1280, 390]) {
      const page = await browser.newPage({ viewport: { width, height: 900 } });
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      const posts = [];
      const presence = {
        assignments: { 'binary_sensor.fht_bedroom_3_presence_group': ['light.fht_bedroom_3_all_lights'] },
        timings: { 'binary_sensor.fht_bedroom_3_presence_group': { activation_delay: 0, clear_delay: 120, parent_groups: [] } },
        mode_settings: { 'binary_sensor.fht_bedroom_3_presence_group': {
          day: { enabled: true, brightness: 100, color_mode: 'current', color_kelvin: 4000 },
          night: { enabled: true, brightness: 80, color_mode: 'kelvin', color_kelvin: 2700 },
          sleep: { enabled: true, brightness: 5, color_mode: 'current', color_kelvin: 4000 },
        } },
      };
      await page.route('**/*', route => {
        const request = route.request();
        const url = new URL(request.url());
        if (url.pathname === '/') return route.fulfill({ contentType: 'text/html', body: html });
        if (/\.(png|webp|jpg)$/.test(url.pathname)) return route.fulfill({ status: 404, body: '' });
        if (url.pathname === '/api/home-configurator/index') {
          return route.fulfill({ json: { ok: true, room_count: 1, house_settings: {}, floors: [{ name: 'Upstairs', floor_id: 'upstairs', rooms: [room] }] } });
        }
        if (url.pathname === '/api/room-modes') {
          return route.fulfill({ json: { ok: true, rooms: [room], catalog, settings: { 'Bedroom 3': ['sleep'] }, current_modes: { 'Bedroom 3': 'Day' }, house_settings: {} } });
        }
        if (url.pathname === '/api/room-scenes') {
          return route.fulfill({ json: { ok: true, catalog_revision: 1, scenes: ['day', 'night', 'sleep'].map(mode => ({ area: 'Bedroom 3', mode, display_name: room.display_name, label: mode[0].toUpperCase() + mode.slice(1), settings: { targets: [], brightness_pct: 100 }, configured: false })) } });
        }
        if (url.pathname === '/api/room-controls' && url.searchParams.get('kind') === 'presence') {
          return route.fulfill({ json: { ok: true, room: 'Bedroom 3', display_name: room.display_name, entities: sensors, presence, catalog_revision: 1 } });
        }
        if (url.pathname === '/api/presence-light-groups' && request.method() === 'POST') {
          const body = request.postDataJSON();
          posts.push(body);
          presence.mode_settings[body.presence_entity_id] = body.mode_settings;
          return route.fulfill({ json: { ok: true, saved: true, assignments: { [body.presence_entity_id]: body.target_entity_ids }, timings: presence.timings, mode_settings: { [body.presence_entity_id]: body.mode_settings } } });
        }
        if (url.pathname === '/api/home-configurator/catalog') return route.fulfill({ json: { ok: true, revision: 1, action_catalog: { light_groups: lights, individual_lights: [], entity_targets: [], room_modes: [], wake_overrides: [] }, wake_catalog: {}, toddler_entities: {}, alarm_targets: [] } });
        return route.fulfill({ json: { ok: true, entities: [], floors: [], rooms: [], settings: {} } });
      });
      await page.goto('http://fht.test/');
      await page.waitForTimeout(800);
      if (width < 800) await page.locator('#mobile-nav-toggle').click();
      await page.locator('#settings-toggle').click();
      await page.locator('[data-view="room-config"]').click();
      const card = page.locator('#room-config-list [data-room-mode-card][data-area="Bedroom 3"]');
      await card.waitFor();
      const dialog = page.locator('#room-mode-dialog');

      // Night: the group shows its saved Night settings and the shared lights and delays.
      await card.locator('[data-room-mode-configure="night"]').click();
      await page.waitForSelector('#room-mode-dialog[open]');
      const section = dialog.locator('[data-room-mode-presence]');
      await section.waitFor();
      assert.equal(await section.locator('[data-mode-presence-card]').count(), 3, 'The group and both PIRs show');
      const group = section.locator('[data-mode-presence-card="binary_sensor.fht_bedroom_3_presence_group"]');
      assert.equal(await group.locator('.mode-presence-enabled').isChecked(), true);
      assert.equal(await group.locator('.mode-presence-brightness').inputValue(), '80');
      assert.equal(await group.locator('.presence-mode-tone').inputValue(), '2700', 'Warm tone from the saved Night setting');
      assert.equal(await group.locator('.mode-presence-delay[data-delay="clear_delay"]').inputValue(), '2', 'Clear Delay starts from the shared setting');
      assert.deepEqual(await group.locator('.mode-presence-targets').evaluate(select => [...select.selectedOptions].map(option => option.value)), ['light.fht_bedroom_3_all_lights']);
      const pir = section.locator('[data-mode-presence-card="binary_sensor.bedroom_3_pir_1"]');
      assert.equal(await pir.locator('.mode-presence-settings').isVisible(), true, 'A PIR with the default Night setting is on');

      await group.locator('.mode-presence-delay[data-delay="clear_delay"]').selectOption('5');
      await page.waitForTimeout(400);
      let saved = posts.at(-1);
      assert.equal(saved.presence_entity_id, 'binary_sensor.fht_bedroom_3_presence_group');
      assert.equal(saved.mode_settings.night.clear_delay, 300);
      assert.equal(saved.mode_settings.night.brightness, 80);
      assert.equal(saved.mode_settings.night.color_mode, 'kelvin');
      assert.deepEqual(saved.mode_settings.night.targets, ['light.fht_bedroom_3_all_lights']);
      assert.equal(saved.clear_delay, 120, 'The shared delay is left alone');
      assert.equal(saved.mode_settings.day.clear_delay, undefined, 'Other modes are not changed');
      if (process.env.FHT_SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.FHT_SCREENSHOT_DIR}/mode-presence-night-${width}.png`, fullPage: false });
      await page.keyboard.press('Escape');
      await page.waitForFunction(() => !document.getElementById('room-mode-dialog').open);

      // Sleep: turning the group off saves Sleep only and hides its settings.
      await card.locator('[data-room-mode-configure="sleep"]').click();
      await page.waitForSelector('#room-mode-dialog[open]');
      await section.waitFor();
      assert.equal(await group.locator('.mode-presence-brightness').inputValue(), '5');
      await group.locator('.mode-presence-enabled').uncheck();
      await page.waitForTimeout(400);
      saved = posts.at(-1);
      assert.equal(saved.mode_settings.sleep.enabled, false);
      assert.equal(saved.mode_settings.night.clear_delay, 300, 'Night keeps its new delay');
      assert.equal(await group.locator('.mode-presence-settings').isVisible(), false);
      if (process.env.FHT_SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.FHT_SCREENSHOT_DIR}/mode-presence-sleep-${width}.png`, fullPage: false });
      assert.deepEqual(errors, []);
      await page.close();
      console.log(`Mode presence passed at ${width}px`);
    }
  } finally {
    await browser.close();
  }
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
