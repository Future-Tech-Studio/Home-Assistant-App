const fs = require('node:fs');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.FHT_PLAYWRIGHT || 'playwright');

// Room Configurator → Environmental: the picked room's exhaust fans with their timer,
// presence and humidity settings. The Environmental menu page is gone.
(async () => {
  const html = fs.readFileSync('future_homes_tech_app/web/index.html', 'utf8');
  const browser = await chromium.launch({ headless: true });
  try {
    for (const width of [1280, 390]) {
      const page = await browser.newPage({ viewport: { width, height: 900 } });
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      const savedTimers = [];
      const savedHumidity = [];
      const savedPresence = [];
      const entities = [
        { entity_id: 'switch.bedroom_6_exhaust', domain: 'switch', device_id: 'd1', device_name: 'Bedroom 6 Switch 2', friendly_name: 'Bedroom 6 Exhaust Fan', state: 'off', area: "Chloe's Bedroom", original_area: 'Bedroom 6', wired_load_names: { 'fan.exhaust': 'Exhaust Fan' } },
        { entity_id: 'switch.bedroom_6_lamp', domain: 'switch', device_id: 'd2', device_name: 'Bedroom 6 Switch 1', friendly_name: 'Bedroom 6 Lamp', state: 'off', area: "Chloe's Bedroom", original_area: 'Bedroom 6' },
        { entity_id: 'switch.laundry_fan', domain: 'switch', device_id: 'd3', device_name: 'Laundry Switch', friendly_name: 'Laundry Switch Switch 3', state: 'on', area: 'Laundry', wired_load_names: { 'fan.laundry_exhaust': 'Laundry Exhaust Fan' } },
        { entity_id: 'switch.master_toilet', domain: 'switch', device_id: 'd4', device_name: 'Bathroom Toilet Switch', friendly_name: 'Master Bedroom Bathroom Toilet Switch Switch 2', state: 'off', area: 'Master Bedroom', wired_load_names: { 'fan.toilet': 'Master Bedroom Bathroom Toilet Exhaust Fan' } },
      ];
      await page.route('**/*', route => {
        const request = route.request();
        const url = new URL(request.url());
        if (url.pathname === '/') return route.fulfill({ contentType: 'text/html', body: html });
        if (/\.(png|webp|jpg)$/.test(url.pathname)) return route.fulfill({ status: 404, body: '' });
        if (url.pathname === '/api/home-configurator/index') return route.fulfill({ json: { ok: true, room_count: 3, house_mode: 'Day', security_mode: 'Disarmed', house_settings: {}, floors: [
          { name: 'Upstairs', floor_id: 'upstairs', rooms: [
            { name: 'Bedroom 6', display_name: "Chloe's Bedroom", mode_type: '', current_mode: '' },
            { name: 'Laundry', display_name: 'Laundry', mode_type: '', current_mode: '' },
            { name: 'Kitchen', display_name: 'Kitchen', mode_type: '', current_mode: '' },
          ] },
        ] } });
        if (url.pathname === '/api/room-controls' && url.searchParams.get('kind') === 'switches') return route.fulfill({ json: { ok: true, rooms_ready: true, aliases: { 'Bedroom 6': "Chloe's Bedroom" }, entities, humidity_sensors: [{ entity_id: 'sensor.bedroom_6_humidity', friendly_name: 'Bedroom 6 Humidity', state: '71', room: 'Bedroom 6' }], presence_sensors: [{ entity_id: 'binary_sensor.bedroom_6_toilet_presence', friendly_name: 'Bedroom 6 Toilet Presence', state: 'off', room: 'Bedroom 6' }], control_settings: { exhaust_timers: { 'switch.laundry_fan': 20 }, exhaust_humidity: {} }, catalog_revision: 1 } });
        if (url.pathname === '/api/fridge-alarms') return route.fulfill({ json: { ok: true, fridge_alarms: {
          devices: [{ name: 'Garage Fridge', door_sensors: [{ entity_id: 'binary_sensor.garage_fridge_door', friendly_name: 'Garage Fridge Door', state: 'off' }], temperature_sensors: [] }],
          settings: {}, alarm_targets: { sirens: [], chimes: [] }, webhook_configured: false, phone_targets: [], phone_targets_error: null } } });
        if (url.pathname === '/api/switch-light-groups') {
          const body = request.postDataJSON();
          if (body.setting === 'exhaust_timer') savedTimers.push(body);
          if (body.setting === 'exhaust_presence') savedPresence.push(body);
          if (body.setting === 'exhaust_humidity') {
            savedHumidity.push(body);
            if (body.stop_below === 70) return route.fulfill({ status: 400, json: { ok: false, error: 'Stop below must be lower than Start above.' } });
          }
          return route.fulfill({ json: { ok: true } });
        }
        return route.fulfill({ json: { ok: true, entities: [], floors: [], rooms: [], settings: {}, entries: [] } });
      });
      await page.goto('http://fht.test/');
      await page.waitForTimeout(800);
      if (width < 800) await page.locator('#mobile-nav-toggle').click();
      await page.locator('#settings-toggle').click();
      const menu = await page.locator('#settings-submenu [data-view]').evaluateAll(items => items.map(item => item.textContent.trim()));
      assert.ok(!menu.includes('Environmental'), 'Environmental is no longer a menu page');
      assert.equal(await page.locator('#settings-submenu [data-view="environment"]').count(), 0);
      assert.equal(menu.indexOf('Switches'), -1, 'Switches live on Room Configurator now');
      await page.locator('[data-view="room-config"]').click();
      await page.waitForFunction(() => [...document.querySelectorAll('#room-config-picker option')].some(option => option.value === 'Bedroom 6'));
      await page.locator('#room-config-picker').selectOption('Bedroom 6');
      const card = page.locator('#room-config-list [data-room-config-environment]');
      assert.equal(await card.locator('h2').innerText(), 'Environmental');
      const list = page.locator('#room-config-environment');
      await list.locator('.control-device-card').first().waitFor();
      assert.deepEqual(await list.locator('.control-device-title').allTextContents(), ['Exhaust Fan'], "Only the picked room's fans, named after the fan");
      assert.equal(await page.locator('#room-config-list button', { hasText: /^Save$/ }).count(), 0, 'Changes save on their own');
      const bedroom = list.locator('.control-device-card').first();
      const timer = bedroom.locator('.exhaust-timer-select');
      assert.equal(await timer.locator('option').count(), 121);
      await timer.selectOption('5');
      await page.waitForFunction(() => document.querySelector('#room-config-environment .exhaust-timer-select').dataset.saved === '5');
      assert.deepEqual(savedTimers.at(-1), { setting: 'exhaust_timer', assignment_id: 'switch.bedroom_6_exhaust', minutes: 5 });
      assert.ok((await bedroom.locator('.exhaust-timer-field').innerText()).startsWith('Manual fan timer'));
      // Presence: the fan starts after the activation delay and runs for the run time, which seeing someone again doesn't restart.
      const presence = bedroom.locator('.exhaust-presence-field');
      assert.ok((await presence.locator('label').nth(2).innerText()).startsWith('Run time'), 'The second delay is a fixed run time');
      assert.equal(await presence.locator('.exhaust-presence-clear option').count(), 60, 'Run time is 1 to 60 minutes');
      assert.deepEqual(await presence.locator('.exhaust-presence-sensor option').allTextContents(), ['None', 'Toilet Presence']);
      assert.equal(await presence.locator('.exhaust-presence-activation').isDisabled(), true, 'Delays wait for a sensor');
      assert.equal(await presence.locator('.exhaust-presence-activation').inputValue(), '2');
      assert.equal(await presence.locator('.exhaust-presence-clear').inputValue(), '5');
      await presence.locator('.exhaust-presence-sensor').selectOption('binary_sensor.bedroom_6_toilet_presence');
      await page.waitForFunction(() => document.querySelector('#room-config-environment .exhaust-presence-field').dataset.savedSensor === 'binary_sensor.bedroom_6_toilet_presence');
      assert.deepEqual(savedPresence.at(-1), { setting: 'exhaust_presence', assignment_id: 'switch.bedroom_6_exhaust', sensor: 'binary_sensor.bedroom_6_toilet_presence', activation_minutes: 2, clear_minutes: 5 });
      await presence.locator('.exhaust-presence-clear').selectOption('10');
      await page.waitForFunction(() => document.querySelector('#room-config-environment .exhaust-presence-field').dataset.savedClear === '10');
      assert.equal(savedPresence.at(-1).clear_minutes, 10);
      const humidity = bedroom.locator('.exhaust-humidity-field');
      const humiditySensor = humidity.locator('.exhaust-humidity-sensor');
      assert.deepEqual(await humiditySensor.locator('option').allTextContents(), ['None', 'Bedroom 6 Humidity']);
      assert.equal(await humidity.locator('.exhaust-humidity-start').isDisabled(), true, 'Levels wait for a sensor');
      assert.equal(await humidity.locator('.exhaust-humidity-start').inputValue(), '65');
      assert.equal(await humidity.locator('.exhaust-humidity-stop').inputValue(), '55');
      await humiditySensor.selectOption('sensor.bedroom_6_humidity');
      await page.waitForFunction(() => document.querySelector('#room-config-environment .exhaust-humidity-field').dataset.savedSensor === 'sensor.bedroom_6_humidity');
      assert.deepEqual(savedHumidity.at(-1), { setting: 'exhaust_humidity', assignment_id: 'switch.bedroom_6_exhaust', sensor: 'sensor.bedroom_6_humidity', start_above: 65, stop_below: 55 });
      assert.equal(await humidity.locator('.exhaust-humidity-reading').textContent(), '71%');
      assert.equal(await humidity.locator('.exhaust-humidity-start').isDisabled(), false);
      await humidity.locator('.exhaust-humidity-stop').selectOption('60');
      await page.waitForFunction(() => document.querySelector('#room-config-environment .exhaust-humidity-field').dataset.savedStop === '60');
      page.once('dialog', dialog => dialog.dismiss());
      await humidity.locator('.exhaust-humidity-stop').selectOption('70');
      await page.waitForFunction(() => !document.querySelector('#room-config-environment .exhaust-humidity-stop').disabled);
      assert.equal(await humidity.locator('.exhaust-humidity-stop').inputValue(), '60', 'A rejected level is put back');
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true, 'No horizontal overflow');
      if (width < 800) {
        const sensor = await humiditySensor.boundingBox();
        const start = await humidity.locator('.exhaust-humidity-start').boundingBox();
        assert.ok(start.y >= sensor.y + sensor.height - 1, 'Levels stack under the sensor on a phone');
      }
      // Same glass device cards as the Switches page.
      const look = await page.evaluate(() => {
        const pick = (element, names) => Object.fromEntries(names.map(name => [name, getComputedStyle(element)[name]]));
        return pick(document.querySelector('#room-config-environment .control-device-card'), ['borderLeftWidth', 'borderRadius']);
      });
      assert.deepEqual(look, { borderLeftWidth: '4px', borderRadius: '9px' });
      assert.equal(await page.locator('#room-config-environment .exhaust-humidity-reading').first().evaluate(element => getComputedStyle(element).color), 'rgb(255, 255, 255)', 'The humidity reading is plain white');
      if (process.env.FHT_SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.FHT_SCREENSHOT_DIR}/environment-${width}.png`, fullPage: true });
      // Another room: its own fan, without the sensors it doesn't have.
      await page.locator('#room-config-picker').selectOption('Laundry');
      await page.locator('#room-config-environment [data-environment-fan="switch.laundry_fan"]').waitFor();
      assert.equal(await list.locator('.exhaust-timer-select').inputValue(), '20', 'Saved timers are shown');
      assert.equal(await list.locator('.exhaust-presence-field, .exhaust-humidity-field').count(), 0, 'Rooms without sensors show only the timer');
      await page.locator('#room-config-picker').selectOption('Kitchen');
      await page.waitForFunction(() => /No exhaust fans in this room/.test(document.getElementById('room-config-environment')?.textContent || ''));
      assert.deepEqual(errors, []);
      console.log(`Room Configurator environmental passed at ${width}px`);
      await page.close();
    }
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
