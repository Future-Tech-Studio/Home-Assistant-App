const fs = require('node:fs');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.FHT_PLAYWRIGHT || 'playwright');

// New Lighting layout: counts at the top, rooms grouped by floor, drag a row
// sideways to dim it, tapping a row toggles it (no switch), All off asks first, each room has
// All on and All off, and Classic view brings back the original cards on this
// device.
(async () => {
  const html = fs.readFileSync('future_homes_tech_app/web/index.html', 'utf8');
  const entities = [
    { entity_id: 'light.fht_kitchen_bar_lights', domain: 'light', friendly_name: 'Kitchen Bar Lights', state: 'on', brightness: 200, area: 'Kitchen', floor: 'Main Floor' },
    { entity_id: 'light.fht_kitchen_pendants', domain: 'light', friendly_name: 'Kitchen Pendants', state: 'off', area: 'Kitchen', floor: 'Main Floor' },
    { entity_id: 'light.fht_pantry_light', domain: 'light', friendly_name: 'Pantry Light', state: 'unavailable', area: 'Pantry', floor: 'Main Floor' },
    { entity_id: 'light.fht_master_bedroom_all_lights', domain: 'light', friendly_name: 'Master Bedroom All Lights', state: 'on', brightness: 90, area: 'Master Bedroom', floor: 'Upstairs' },
    { entity_id: 'light.fht_porch_light', domain: 'light', friendly_name: 'Porch Light', state: 'on', brightness: null, supported_color_modes: ['onoff'], area: 'Porch', floor: 'Main Floor' },
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
          const action = route.request().postDataJSON();
          actions.push(action);
          // All on answers with the brightness each light took for the current mode.
          if (action.action === 'turn_on') {
            return route.fulfill({ json: { ok: true, brightness: Object.fromEntries(action.entity_ids.map(id => [id, 40])) } });
          }
          return route.fulfill({ json: { ok: true } });
        }
        return route.fulfill({ json: { ok: true, entities: [], floors: [], rooms: [], buttons: [], scenes: [], settings: {}, entries: [], schedules: {}, single_lights: [] } });
      });
      await page.goto('http://fht.test/');
      await page.waitForTimeout(500);
      await page.evaluate(() => document.querySelector('[data-view="lighting"]').click());
      await page.waitForSelector('.lighting-row');

      assert.deepEqual(await page.locator('.lighting-stat b').allTextContents(), ['3', '3', '1'], 'lights on, rooms lit, offline');
      assert.deepEqual(await page.locator('.lighting-floor-title').allTextContents(), ['Main Floor', 'Upstairs']);
      assert.deepEqual(await page.locator('.lighting-row-name').allTextContents(), ['Bar Lights', 'Pendants', 'Light', 'Light', 'All Lights']);
      assert.equal(await page.locator('.lighting-row-value').first().textContent(), '78%');
      assert.equal(await page.locator('.lighting-row-switch').count(), 0, 'rows have no on/off switch');
      // An on/off-only light has no brightness bar and reads On, and dragging it does nothing.
      const porchRow = page.locator('[data-lighting-row="light.fht_porch_light"]');
      assert.equal(await porchRow.locator('.lighting-row-value').textContent(), 'On', 'an on/off light that is on reads On');
      assert.equal(await porchRow.locator('.lighting-row-fill').count(), 0, 'an on/off light has no brightness bar');
      assert.equal(await porchRow.getAttribute('role'), 'button');
      await porchRow.scrollIntoViewIfNeeded();
      const porchBox = await porchRow.boundingBox();
      await page.mouse.move(porchBox.x + 20, porchBox.y + porchBox.height / 2);
      await page.mouse.down();
      await page.mouse.move(porchBox.x + porchBox.width * 0.5, porchBox.y + porchBox.height / 2, { steps: 6 });
      await page.mouse.up();
      await page.waitForTimeout(150);
      assert.equal(actions.length, 0, 'dragging an on/off light sends nothing');
      assert.equal(await porchRow.locator('.lighting-row-fill').count(), 0, 'no bar appears while dragging an on/off light');
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
      assert.equal(actions.length, 0, 'dragging the brightness does not also toggle');

      // Tapping a row toggles it; tapping the offline light does nothing.
      const bedroom = page.locator('[data-lighting-row="light.fht_master_bedroom_all_lights"]');
      await bedroom.scrollIntoViewIfNeeded();
      await bedroom.click();
      await page.waitForTimeout(150);
      assert.deepEqual(actions.pop(), { action: 'toggle', entity_ids: ['light.fht_master_bedroom_all_lights'], brightness_pct: null });
      assert.equal(await bedroom.getAttribute('class').then(c => c.includes('is-off')), true, 'the tapped light shows off');
      const porch = page.locator('[data-lighting-row="light.fht_porch_light"]');
      await porch.click();
      await page.waitForTimeout(150);
      assert.deepEqual(actions.pop(), { action: 'toggle', entity_ids: ['light.fht_porch_light'], brightness_pct: null });
      await page.locator('[data-lighting-row="light.fht_pantry_light"]').click();
      await page.waitForTimeout(150);
      assert.equal(actions.length, 0, 'tapping an offline light sends nothing');

      // Enter on a focused row toggles it too.
      await page.locator('[data-lighting-row="light.fht_kitchen_bar_lights"]').focus();
      await page.keyboard.press('Enter');
      await page.waitForTimeout(150);
      assert.deepEqual(actions.pop(), { action: 'toggle', entity_ids: ['light.fht_kitchen_bar_lights'], brightness_pct: null });

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
      assert.deepEqual(off.entity_ids.sort(), ['light.fht_kitchen_pendants'], 'only the light still on after the taps');

      // Each room has All on and All off instead of an "N on" count; each
      // sends only the lights that need it, and is left out when none do.
      const kitchen = page.locator('.lighting-room').filter({ hasText: 'Kitchen' });
      assert.deepEqual(await kitchen.locator('.lighting-room-button').allTextContents(), ['All on'], 'nothing on to turn off');
      await kitchen.locator('[data-lighting-room-action="on"]').click();
      await page.waitForTimeout(150);
      assert.deepEqual(actions.pop(), { action: 'turn_on', entity_ids: ['light.fht_kitchen_bar_lights', 'light.fht_kitchen_pendants'], brightness_pct: null });
      assert.deepEqual(await kitchen.locator('.lighting-row-value').allTextContents(), ['40%', '40%'], 'rows show the mode brightness');
      assert.deepEqual(await kitchen.locator('.lighting-room-button').allTextContents(), ['All off'], 'all on already');
      const pantry = page.locator('.lighting-room').filter({ hasText: 'Pantry' });
      assert.equal(await pantry.locator('.lighting-room-actions').count(), 0, 'offline room has nothing to switch');
      const head = await kitchen.locator('.lighting-room-head').boundingBox();
      assert.ok(head.height < 56, `room header stays one line at ${width}px (${head.height}px)`);

      // Classic view brings back the original cards, and stays after a reload.
      await page.locator('#lighting-layout-toggle').click();
      await page.waitForSelector('.lighting-area-card');
      assert.equal(await page.locator('.lighting-row').count(), 0);
      assert.equal(await page.locator('#lighting-layout-toggle').textContent(), 'New view');
      assert.equal(await page.locator('#lighting-all-off').isVisible(), false);
      const classicKitchen = page.locator('.lighting-area-card').filter({ hasText: 'Kitchen' });
      assert.deepEqual(await classicKitchen.locator('.lighting-room-button').allTextContents(), ['All off'], 'classic cards keep the room buttons');
      assert.equal(await page.locator('.lighting-area-card').filter({ hasText: 'Pantry' }).locator('.lighting-room-button').count(), 0);
      const porchCard = page.locator('.lighting-control-card').filter({ has: page.locator('[data-lighting-entity-id="light.fht_porch_light"]') });
      assert.equal(await porchCard.locator('.lighting-brightness-button, .lighting-item-range').count(), 0, 'classic on/off card has no brightness control');
      const bedroomCard = page.locator('.lighting-control-card').filter({ has: page.locator('[data-lighting-entity-id="light.fht_master_bedroom_all_lights"]') });
      assert.equal(await bedroomCard.locator('.lighting-brightness-button').count(), 1, 'classic dimmable card keeps its brightness control');
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
