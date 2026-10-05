const fs = require('node:fs');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.FHT_PLAYWRIGHT || 'playwright');

// New Lighting layout: counts at the top, rooms grouped by floor, drag a row
// sideways to dim it, the switch toggles, All off asks first, and Classic view
// brings back the original cards on this device.
(async () => {
  const html = fs.readFileSync('future_homes_tech_app/web/index.html', 'utf8');
  const entities = [
    { entity_id: 'light.fht_kitchen_all_lights', domain: 'light', friendly_name: 'Kitchen All Lights', state: 'on', brightness: 200, area: 'Kitchen', floor: 'Main Floor' },
    { entity_id: 'light.fht_kitchen_pendants', domain: 'light', friendly_name: 'Kitchen Pendants', state: 'off', area: 'Kitchen', floor: 'Main Floor' },
    { entity_id: 'light.fht_pantry_light', domain: 'light', friendly_name: 'Pantry Light', state: 'unavailable', area: 'Pantry', floor: 'Main Floor' },
    { entity_id: 'light.fht_master_bedroom_all_lights', domain: 'light', friendly_name: 'Master Bedroom All Lights', state: 'on', brightness: 90, area: 'Master Bedroom', floor: 'Upstairs' },
  ];
  const browser = await chromium.launch({ headless: true });
  try {
    for (const [width, height] of [[1180, 820], [390, 844]]) {
      const context = await browser.newContext({ viewport: { width, height } });
      const page = await context.newPage();
      const errors = [];
      const actions = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.route('**/*', route => {
        const url = new URL(route.request().url());
        if (url.pathname === '/') return route.fulfill({ contentType: 'text/html', body: html });
        if (/\.(png|webp|jpg)$/.test(url.pathname)) return route.fulfill({ status: 404, body: '' });
        if (url.pathname === '/api/lighting/status') return route.fulfill({ json: { ok: true, entities, stale: false } });
        if (url.pathname === '/api/lighting/action') {
          actions.push(route.request().postDataJSON());
          return route.fulfill({ json: { ok: true } });
        }
        return route.fulfill({ json: { ok: true, entities: [], floors: [], rooms: [], buttons: [], scenes: [], settings: {}, entries: [], schedules: {}, single_lights: [] } });
      });
      await page.goto('http://fht.test/');
      await page.waitForTimeout(500);
      await page.evaluate(() => document.querySelector('[data-view="lighting"]').click());
      await page.waitForSelector('.lighting-row');

      assert.deepEqual(await page.locator('.lighting-stat b').allTextContents(), ['2', '2', '1'], 'lights on, rooms lit, offline');
      assert.deepEqual(await page.locator('.lighting-floor-title').allTextContents(), ['Main Floor', 'Upstairs']);
      assert.deepEqual(await page.locator('.lighting-row-name').allTextContents(), ['All Lights', 'Pendants', 'Light', 'All Lights']);
      assert.equal(await page.locator('.lighting-row-value').first().textContent(), '78%');
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, `no sideways scroll at ${width}px`);

      // Drag the Pendants row to about 50%.
      const row = page.locator('[data-lighting-row="light.fht_kitchen_pendants"]');
      await row.scrollIntoViewIfNeeded();
      const box = await row.boundingBox();
      await page.mouse.move(box.x + 20, box.y + box.height / 2);
      await page.mouse.down();
      await page.mouse.move(box.x + box.width * 0.3, box.y + box.height / 2, { steps: 4 });
      await page.mouse.move(box.x + box.width * 0.5, box.y + box.height / 2, { steps: 4 });
      await page.mouse.up();
      await page.waitForTimeout(150);
      const dim = actions.pop();
      assert.equal(dim.action, 'set_brightness');
      assert.deepEqual(dim.entity_ids, ['light.fht_kitchen_pendants']);
      assert.ok(Math.abs(dim.brightness_pct - 50) <= 2, `dimmed to ${dim.brightness_pct}%`);

      // A tap on a row without dragging changes nothing.
      await row.click({ position: { x: 20, y: box.height / 2 } });
      await page.waitForTimeout(150);
      assert.equal(actions.length, 0, 'a plain tap does not dim');

      // The switch toggles; the offline light's switch is disabled.
      await page.locator('[data-lighting-row="light.fht_master_bedroom_all_lights"] .lighting-row-switch').click();
      await page.waitForTimeout(150);
      assert.deepEqual(actions.pop(), { action: 'toggle', entity_ids: ['light.fht_master_bedroom_all_lights'], brightness_pct: null });
      assert.equal(await page.locator('[data-lighting-row="light.fht_pantry_light"] .lighting-row-switch').isDisabled(), true);

      // All off asks first, and declining sends nothing.
      page.once('dialog', dialog => dialog.dismiss());
      await page.locator('#lighting-all-off').click();
      await page.waitForTimeout(150);
      assert.equal(actions.length, 0, 'declined All off sends nothing');
      page.once('dialog', dialog => dialog.accept());
      await page.locator('#lighting-all-off').click();
      await page.waitForTimeout(150);
      const off = actions.pop();
      assert.equal(off.action, 'turn_off');
      assert.deepEqual(off.entity_ids.sort(), ['light.fht_kitchen_all_lights', 'light.fht_kitchen_pendants']);

      // Classic view brings back the original cards, and stays after a reload.
      await page.locator('#lighting-layout-toggle').click();
      await page.waitForSelector('.lighting-area-card');
      assert.equal(await page.locator('.lighting-row').count(), 0);
      assert.equal(await page.locator('#lighting-layout-toggle').textContent(), 'New view');
      assert.equal(await page.locator('#lighting-all-off').isVisible(), false);
      await page.reload();
      await page.waitForTimeout(500);
      await page.evaluate(() => document.querySelector('[data-view="lighting"]').click());
      await page.waitForSelector('.lighting-area-card');
      await page.locator('#lighting-layout-toggle').click();
      await page.waitForSelector('.lighting-row');
      assert.equal(await page.locator('#lighting-layout-toggle').textContent(), 'Classic view');

      assert.deepEqual(errors, []);
      await context.close();
      console.log(`New Lighting layout passed at ${width}px`);
    }
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exit(1); });
