const fs = require('node:fs');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.FHT_PLAYWRIGHT || 'playwright');

// Settings → Environment: exhaust fans by room with their timer and humidity sensor.
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
        if (url.pathname === '/api/room-controls') return route.fulfill({ json: { ok: true, rooms_ready: true, aliases: { 'Bedroom 6': "Chloe's Bedroom" }, entities, humidity_sensors: [{ entity_id: 'sensor.bedroom_6_humidity', friendly_name: 'Bedroom 6 Humidity', state: '71', room: 'Bedroom 6' }], presence_sensors: [{ entity_id: 'binary_sensor.bedroom_6_toilet_presence', friendly_name: 'Bedroom 6 Toilet Presence', state: 'off', room: 'Bedroom 6' }], control_settings: { exhaust_timers: { 'switch.laundry_fan': 20 }, exhaust_humidity: {} }, catalog_revision: 1 } });
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
      assert.deepEqual(menu.slice(2, 5), ['Doors', 'Switches', 'Environmental']);
      assert.equal(menu[menu.indexOf('Environmental') + 1], 'Presence', 'Environmental sits right before Presence');
      await page.locator('[data-view="environment"]').click();
      const list = page.locator('#environment-list');
      await list.locator('.switches-area').first().waitFor();
      assert.deepEqual(await list.locator('.switches-area-heading').allTextContents(), ["Chloe's Bedroom", 'Laundry', 'Master Bedroom']);
      assert.deepEqual(await list.locator('.control-device-title').allTextContents(), ['Exhaust Fan', 'Exhaust Fan', 'Bathroom Toilet Exhaust Fan'], 'Cards are named after the fan, not the switch channel, without the room prefix');
      const bedroom = list.locator('.control-device-card').first();
      const timer = bedroom.locator('.exhaust-timer-select');
      assert.equal(await timer.locator('option').count(), 121);
      assert.equal(await list.locator('.control-device-card').nth(1).locator('.exhaust-timer-select').inputValue(), '20', 'Saved timers are shown');
      await timer.selectOption('5');
      await page.waitForFunction(() => document.querySelector('#environment-list .exhaust-timer-select').dataset.saved === '5');
      assert.deepEqual(savedTimers.at(-1), { setting: 'exhaust_timer', assignment_id: 'switch.bedroom_6_exhaust', minutes: 5 });
      assert.ok((await bedroom.locator('.exhaust-timer-field').innerText()).startsWith('Manual fan timer'));
      // Presence: the fan follows the room's presence sensor, starting after the activation delay and stopping after the clear delay.
      const presence = bedroom.locator('.exhaust-presence-field');
      assert.deepEqual(await presence.locator('.exhaust-presence-sensor option').allTextContents(), ['None', 'Toilet Presence']);
      assert.equal(await presence.locator('.exhaust-presence-activation').isDisabled(), true, 'Delays wait for a sensor');
      assert.equal(await presence.locator('.exhaust-presence-activation').inputValue(), '2');
      assert.equal(await presence.locator('.exhaust-presence-clear').inputValue(), '5');
      await presence.locator('.exhaust-presence-sensor').selectOption('binary_sensor.bedroom_6_toilet_presence');
      await page.waitForFunction(() => document.querySelector('#environment-list .exhaust-presence-field').dataset.savedSensor === 'binary_sensor.bedroom_6_toilet_presence');
      assert.deepEqual(savedPresence.at(-1), { setting: 'exhaust_presence', assignment_id: 'switch.bedroom_6_exhaust', sensor: 'binary_sensor.bedroom_6_toilet_presence', activation_minutes: 2, clear_minutes: 5 });
      await presence.locator('.exhaust-presence-clear').selectOption('10');
      await page.waitForFunction(() => document.querySelector('#environment-list .exhaust-presence-field').dataset.savedClear === '10');
      assert.equal(savedPresence.at(-1).clear_minutes, 10);
      assert.equal(await list.locator('.control-device-card').nth(1).locator('.exhaust-presence-field').count(), 0, 'Rooms without a presence sensor show no presence rows');
      const humidity = bedroom.locator('.exhaust-humidity-field');
      const humiditySensor = humidity.locator('.exhaust-humidity-sensor');
      assert.deepEqual(await humiditySensor.locator('option').allTextContents(), ['None', 'Bedroom 6 Humidity']);
      assert.equal(await list.locator('.control-device-card').nth(1).locator('.exhaust-humidity-field').count(), 0, 'Rooms without a humidity sensor show only the timer');
      assert.equal(await list.locator('.control-device-card').nth(2).locator('.exhaust-humidity-field').count(), 0);
      assert.equal(await humidity.locator('.exhaust-humidity-start').isDisabled(), true, 'Levels wait for a sensor');
      assert.equal(await humidity.locator('.exhaust-humidity-start').inputValue(), '65');
      assert.equal(await humidity.locator('.exhaust-humidity-stop').inputValue(), '55');
      await humiditySensor.selectOption('sensor.bedroom_6_humidity');
      await page.waitForFunction(() => document.querySelector('#environment-list .exhaust-humidity-field').dataset.savedSensor === 'sensor.bedroom_6_humidity');
      assert.deepEqual(savedHumidity.at(-1), { setting: 'exhaust_humidity', assignment_id: 'switch.bedroom_6_exhaust', sensor: 'sensor.bedroom_6_humidity', start_above: 65, stop_below: 55 });
      assert.equal(await humidity.locator('.exhaust-humidity-reading').textContent(), '71%');
      assert.equal(await humidity.locator('.exhaust-humidity-start').isDisabled(), false);
      await humidity.locator('.exhaust-humidity-stop').selectOption('60');
      await page.waitForFunction(() => document.querySelector('#environment-list .exhaust-humidity-field').dataset.savedStop === '60');
      page.once('dialog', dialog => dialog.dismiss());
      await humidity.locator('.exhaust-humidity-stop').selectOption('70');
      await page.waitForFunction(() => !document.querySelector('#environment-list .exhaust-humidity-stop').disabled);
      assert.equal(await humidity.locator('.exhaust-humidity-stop').inputValue(), '60', 'A rejected level is put back');
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true, 'No horizontal overflow');
      if (width < 800) {
        const sensor = await humiditySensor.boundingBox();
        const start = await humidity.locator('.exhaust-humidity-start').boundingBox();
        assert.ok(start.y >= sensor.y + sensor.height - 1, 'Levels stack under the sensor on a phone');
      }
      // Same look as the Switches page: page title in the top bar, centred room heading, glass device cards.
      assert.equal(await page.locator('#environment-toolbar h1').innerText(), 'Environmental');
      assert.ok(await page.locator('#environment-toolbar').evaluate(element => element.closest('.page-actions-primary') !== null), 'Title sits in the top bar like Switches');
      assert.equal(await page.evaluate(() => document.body.classList.contains('environment-view-active')), true);
      const look = await page.evaluate(() => {
        const pick = (element, names) => Object.fromEntries(names.map(name => [name, getComputedStyle(element)[name]]));
        return {
          heading: pick(document.querySelector('#environment-list .switches-area-heading'), ['textAlign', 'fontSize', 'color']),
          card: pick(document.querySelector('#environment-list .control-device-card'), ['backgroundColor', 'borderLeftWidth', 'borderLeftColor', 'borderRadius']),
        };
      });
      assert.deepEqual(look.heading, { textAlign: 'center', fontSize: '20px', color: 'rgb(255, 255, 255)' });
      assert.equal(look.card.borderLeftWidth, '4px');
      assert.equal(await page.locator('#environment-list .exhaust-humidity-reading').first().evaluate(element => getComputedStyle(element).color), 'rgb(255, 255, 255)', 'The humidity reading is plain white');
      if (process.env.FHT_SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.FHT_SCREENSHOT_DIR}/environment-${width}.png`, fullPage: true });
      // Refrigerator door sensors live on Environmental now.
      await page.locator('#view-environment #alarm-device-list .fridge-alarm-sensor').first().waitFor();
      assert.equal(await page.locator('.environment-fridge-heading').innerText(), 'Refrigerators');
      assert.match(await page.locator('#view-environment #alarm-device-list').innerText(), /REFRIGERATOR DOOR SENSORS\s+Garage Fridge/);
      assert.equal(await page.locator('#view-alarm #alarm-device-list').count(), 0, 'Alarm no longer shows the fridge sensors');
      // Doors layout: rooms with one fan sit two to a row on desktop.
      const areaBoxes = await page.locator('#environment-list .switches-area').evaluateAll(areas => areas.map(area => area.getBoundingClientRect()).map(box => ({ x: Math.round(box.x), y: Math.round(box.y) })));
      if (width >= 1280) {
        assert.ok(areaBoxes[0].y === areaBoxes[1].y && areaBoxes[1].x > areaBoxes[0].x, 'Single-fan rooms share a row');
      } else {
        assert.ok(areaBoxes[1].y > areaBoxes[0].y && areaBoxes[1].x === areaBoxes[0].x, 'Rooms stack on a phone');
      }
      assert.deepEqual(errors, []);
      console.log(`Environment page passed at ${width}px`);
      await page.close();
    }
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
