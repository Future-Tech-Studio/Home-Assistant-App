const fs = require('node:fs');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.FHT_PLAYWRIGHT || 'playwright');

// Home Configurator → Light Automations: light groups plus lights that have no group of
// their own, such as a single porch or side-yard light.
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
      ];
      const posts = [];
      await page.route('**/*', route => {
        const request = route.request();
        const url = new URL(request.url());
        if (url.pathname === '/') return route.fulfill({ contentType: 'text/html', body: html });
        if (/\.(png|webp|jpg)$/.test(url.pathname)) return route.fulfill({ status: 404, body: '' });
        if (url.pathname === '/api/entities') return route.fulfill({ json: { ok: true, entities } });
        if (url.pathname === '/api/light-schedules') {
          if (request.method() === 'POST') {
            posts.push(request.postDataJSON());
            return route.fulfill({ json: { ok: true, saved: true, activated: true, schedules: { [request.postDataJSON().entity_id]: request.postDataJSON().schedule } } });
          }
          return route.fulfill({ json: { ok: true, schedules: {}, single_lights: ['light.porch', 'light.side_yard'] } });
        }
        return route.fulfill({ json: { ok: true, entities: [], floors: [], rooms: [], settings: {}, scenes: [], catalog: {}, current_modes: {}, house_settings: {}, buttons: [], control_settings: {}, aliases: {}, entries: [] } });
      });
      await page.goto('http://fht.test/');
      await page.waitForTimeout(800);
      if (width < 800) await page.locator('#mobile-nav-toggle').click();
      await page.locator('#settings-toggle').click();
      const menu = await page.locator('#settings-submenu [data-view]').evaluateAll(items => items.map(item => item.textContent.trim()));
      assert.ok(menu.includes('Scenes'), 'Scenes keeps Room Scenes');
      await page.locator('[data-view="rooms"]').click();
      const list = page.locator('#room-configurator-list #scene-light-automations');
      await page.waitForFunction(() => document.querySelectorAll('#scene-light-automations .automation-area-heading').length === 3);
      assert.equal(await page.evaluate(() => {
        const section = document.querySelector('#scene-light-automations');
        return section.parentElement.id === 'room-configurator-list' && !section.nextElementSibling
          && document.querySelector('.future-tech-portal-card').compareDocumentPosition(section) === Node.DOCUMENT_POSITION_FOLLOWING;
      }), true, 'Light Automations is the last section of Home Configurator');
      assert.ok((await list.locator('.light-automations-title').textContent()).startsWith('Light Automations'));
      assert.equal(await list.locator('.scene-area-card').first().evaluate(card => card.matches('.house-mode-card') && getComputedStyle(card).borderLeftWidth), '4px', 'Room cards use the Whole Home card style');
      assert.equal(await page.locator('#view-scenes [data-scene-subpage="light-automations"]').count(), 0, 'Scenes no longer has a Light Automations tab');
      const areaNames = async (area) => list.locator('.scene-area-card').filter({ has: page.locator('.automation-area-heading', { hasText: area }) })
        .locator('[data-light-schedule-card]').evaluateAll(cards => cards.map(card => card.dataset.entityId));
      const outside = await areaNames('Outside');
      assert.deepEqual(outside, ['light.fht_outside_all_lights', 'light.fht_outside_coach_lights', 'light.porch', 'light.side_yard'],
        'Outside: its groups plus the porch and side-yard lights; coach bulbs are covered by Coach Lights, the indicator is not a room light');
      assert.deepEqual(await areaNames('Kitchen'), ['light.fht_kitchen_all_lights'], 'Lights already in a smaller group are not repeated');
      assert.deepEqual(await areaNames('Pantry'), ['light.pantry'], 'A room with one light offers it');
      const porch = list.locator('[data-light-schedule-card][data-entity-id="light.porch"]');
      assert.equal(await page.locator('#scene-light-automations input[type="time"]').count(), 0, 'No system time wheel: it crashes the Mac Home Assistant app');
      await porch.locator('[data-schedule-field="on_type"]').selectOption('time');
      await porch.locator('[data-schedule-phase="on"] .automation-schedule-time').click();
      await page.locator('#climate-time-dialog').waitFor();
      await page.locator('#climate-time-hour').selectOption('7');
      await page.locator('#climate-time-minute').selectOption('45');
      await page.locator('#climate-time-period').selectOption('PM');
      await page.locator('#climate-time-save').click();
      assert.equal(await porch.locator('[data-schedule-phase="on"] .automation-schedule-time').textContent(), '7:45 PM');
      await porch.locator('[data-schedule-field="enabled"]').check();
      await porch.locator('.automation-light-save').click();
      await page.waitForFunction(() => document.querySelector('[data-light-schedule-card][data-entity-id="light.porch"] .automation-light-save').textContent !== 'Saving…');
      assert.equal(posts.at(-1)?.entity_id, 'light.porch', 'A porch light schedule saves for that light');
      assert.equal(posts.at(-1)?.schedule.enabled, true);
      assert.equal(posts.at(-1)?.schedule.on_time, '19:45', 'The picked time is saved');
      // Coming back to the page keeps the single lights listed.
      await page.evaluate(() => document.querySelector('[data-view="switches"]').click());
      await page.evaluate(() => document.querySelector('[data-view="rooms"]').click());
      await page.waitForFunction(() => document.querySelector('#scene-light-automations [data-entity-id="light.side_yard"]'));
      assert.deepEqual(errors, []);
      await page.close();
    }
    console.log('Scene light automations passed');
  } finally {
    await browser.close();
  }
})().catch(error => {
  console.error(error);
  process.exit(1);
});
