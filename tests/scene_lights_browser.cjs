const fs = require('node:fs');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.FHT_PLAYWRIGHT || 'playwright');

// Room Configurator → Schedule: the room's light groups plus lights that have no
// group of their own, such as a single porch or side-yard light.
(async () => {
  const html = fs.readFileSync('future_homes_tech_app/web/index.html', 'utf8');
  const browser = await chromium.launch({ headless: true });
  try {
    for (const width of [1280, 390]) {
      const page = await browser.newPage({ viewport: { width, height: 900 } });
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      const light = (entity_id, friendly_name, area, members = []) => ({ entity_id, friendly_name, area, members, domain: 'light', state: 'off' });
      const entities = [
        light('light.fht_outside_all_lights', 'Outside All Lights', 'Outside', ['light.coach_left', 'light.coach_right', 'light.porch', 'light.side_yard']),
        light('light.fht_outside_coach_lights', 'Outside Coach Lights', 'Outside', ['light.coach_left', 'light.coach_right']),
        light('light.coach_left', 'Coach Light Left', 'Outside'),
        light('light.coach_right', 'Coach Light Right', 'Outside'),
        light('light.porch', 'Porch Light', 'Outside'),
        light('light.side_yard', 'Side Yard Light', 'Outside'),
        light('light.outside_switch_indicator', 'Outside Switch Indicator', 'Outside'),
        light('light.pantry', 'Pantry Light', 'Pantry'),
        light('light.fht_kitchen_all_lights', 'Kitchen All Lights', 'Kitchen', ['light.kitchen_1', 'light.kitchen_2']),
        light('light.kitchen_1', 'Kitchen Light 1', 'Kitchen'),
        light('light.kitchen_2', 'Kitchen Light 2', 'Kitchen'),
        light('light.fht_primary_closet_all_lights', 'Primary Closet All Lights', 'Primary Closet'),
        light('light.fht_bedroom_2_all_lights', 'Bedroom 2 All Lights', 'Bedroom 2', ['light.bedroom_2_ceiling']),
        light('light.bedroom_2_ceiling', 'Bedroom 2 Ceiling', 'Bedroom 2'),
        light('light.bedroom_2_closet', 'Bedroom 2 Closet Light', 'Bedroom 2'),
      ];
      const posts = [];
      const room = (name, display_name = name) => ({ name, display_name, mode_type: '', current_mode: '' });
      await page.route('**/*', route => {
        const request = route.request();
        const url = new URL(request.url());
        if (url.pathname === '/') return route.fulfill({ contentType: 'text/html', body: html });
        if (/\.(png|webp|jpg)$/.test(url.pathname)) return route.fulfill({ status: 404, body: '' });
        if (url.pathname === '/api/entities') return route.fulfill({ json: { ok: true, entities } });
        if (url.pathname === '/api/home-configurator/index') {
          return route.fulfill({ json: { ok: true, room_count: 6, house_settings: {}, floors: [
            { name: 'Main Floor', floor_id: 'main', rooms: [room('Outside'), room('Kitchen'), room('Pantry'), room('Laundry')] },
            { name: 'Upstairs', floor_id: 'upstairs', rooms: [room('Bedroom 2', "Ava's Bedroom"), room('Primary Closet')] },
          ] } });
        }
        if (url.pathname === '/api/light-schedules') {
          if (request.method() === 'POST') {
            posts.push(request.postDataJSON());
            return route.fulfill({ json: { ok: true, saved: true, activated: true, schedules: { [request.postDataJSON().entity_id]: request.postDataJSON().schedule } } });
          }
          return route.fulfill({ json: { ok: true, schedules: {}, single_lights: ['light.porch', 'light.side_yard', 'light.bedroom_2_closet'] } });
        }
        return route.fulfill({ json: { ok: true, entities: [], floors: [], rooms: [], settings: {}, scenes: [], catalog: {}, current_modes: {}, house_settings: {}, buttons: [], control_settings: {}, aliases: {}, entries: [], door_sensors: [] } });
      });
      await page.goto('http://fht.test/');
      await page.waitForTimeout(800);
      if (width < 800) await page.locator('#mobile-nav-toggle').click();
      await page.locator('#settings-toggle').click();
      const menu = await page.locator('#settings-submenu [data-view]').evaluateAll(items => items.map(item => item.dataset.view));
      assert.ok(!menu.includes('scenes'), 'Room Scenes moved to Room Configurator');
      assert.ok(!menu.includes('schedule'), 'Schedule moved to Room Configurator');
      await page.locator('[data-view="room-config"]').click();
      await page.waitForFunction(() => !document.getElementById('room-config-picker').disabled);
      const card = page.locator('#room-config-list [data-room-config-schedule]');
      const roomLights = async (name) => {
        await page.locator('#room-config-picker').selectOption(name);
        await page.locator(`[data-room-config-card][data-room="${name}"]`).waitFor();
        await page.waitForFunction(() => document.querySelector('#room-config-schedule')?.children.length);
        return card.locator('[data-light-schedule-card]').evaluateAll(cards => cards.map(item => item.dataset.entityId));
      };
      assert.deepEqual(await roomLights('Outside'), ['light.fht_outside_all_lights', 'light.fht_outside_coach_lights', 'light.porch', 'light.side_yard'],
        'Outside: its groups plus the porch and side-yard lights; coach bulbs are covered by Coach Lights, the indicator is not a room light');
      assert.equal(await card.locator('h2').innerText(), 'Schedule');
      assert.equal(await card.locator('[data-light-schedule-card]').first().evaluate(item => getComputedStyle(item).borderLeftWidth), '4px', 'Each light card has the Whole Home blue edge');
      const columns = await card.locator('.scene-automation-list').evaluate(element => getComputedStyle(element).gridTemplateColumns.split(' ').length);
      assert.equal(columns, width >= 800 ? 2 : 1, 'Two columns wide, one when narrow');
      assert.equal(await page.locator('#room-config-schedule input[type="time"]').count(), 0, 'No system time wheel: it crashes the Mac Home Assistant app');
      const porch = card.locator('[data-light-schedule-card][data-entity-id="light.porch"]');
      await porch.locator('[data-schedule-field="on_type"]').selectOption('time');
      await porch.locator('[data-schedule-phase="on"] .automation-schedule-time').click();
      await page.locator('#climate-time-dialog').waitFor();
      await page.locator('#climate-time-hour').selectOption('7');
      await page.locator('#climate-time-minute').selectOption('45');
      await page.locator('#climate-time-period').selectOption('PM');
      await page.locator('#climate-time-save').click();
      assert.equal(await porch.locator('[data-schedule-phase="on"] .automation-schedule-time').textContent(), '7:45 PM');
      assert.equal(await card.locator('.automation-light-save').count(), 0, 'No Save button: changes save on their own');
      await porch.locator('[data-schedule-field="enabled"]').check();
      await page.waitForFunction(() => document.querySelector('[data-light-schedule-card][data-entity-id="light.porch"] .automation-light-status').textContent === 'Saved');
      assert.equal(await porch.evaluate(item => item.classList.contains('enabled')), true);
      assert.equal(posts.at(-1)?.entity_id, 'light.porch', 'A porch light schedule saves for that light');
      assert.equal(posts.at(-1)?.schedule.enabled, true);
      assert.equal(posts.at(-1)?.schedule.on_time, '19:45', 'The picked time is saved');
      // The color pop-up works from Room Configurator and saves on its own.
      await porch.locator('.automation-light-color').click();
      await page.locator('#light-color-dialog[open]').waitFor();
      await page.locator('#light-color-adaptive').check();
      await page.locator('#light-color-apply').click();
      await page.waitForFunction(() => document.querySelector('#room-config-schedule [data-entity-id="light.porch"] .automation-light-color').textContent.includes('Adaptive'));
      for (let tries = 0; tries < 50 && posts.at(-1)?.schedule.color_mode !== 'adaptive'; tries += 1) await page.waitForTimeout(50);
      assert.equal(posts.at(-1)?.schedule.color_mode, 'adaptive');
      assert.deepEqual(await roomLights('Kitchen'), ['light.fht_kitchen_all_lights'], 'Lights already in a smaller group are not repeated');
      assert.deepEqual(await roomLights('Pantry'), ['light.pantry'], 'A room with one light offers it');
      assert.deepEqual(await roomLights('Bedroom 2'), ['light.fht_bedroom_2_all_lights'], 'A closet light in a bedroom is left out');
      assert.deepEqual(await roomLights('Primary Closet'), [], 'Closet lights are never scheduled');
      assert.equal(await card.locator('.room-config-note').innerText(), 'No lights to schedule in this room.');
      assert.deepEqual(await roomLights('Laundry'), []);
      // Coming back keeps the saved schedule.
      await roomLights('Outside');
      assert.equal(await card.locator('[data-entity-id="light.porch"] [data-schedule-field="enabled"]').isChecked(), true);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true, 'No horizontal overflow');
      assert.deepEqual(errors, []);
      await page.close();
    }
    console.log('Room Configurator schedule passed');
  } finally {
    await browser.close();
  }
})().catch(error => {
  console.error(error);
  process.exit(1);
});
