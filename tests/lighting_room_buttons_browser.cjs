const fs = require('node:fs');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.FHT_PLAYWRIGHT || 'playwright');

// Each Lighting card has Off and On buttons in its title instead of an All Lights
// row, and lists every other group and standalone light below.
(async () => {
  const html = fs.readFileSync('future_homes_tech_app/web/index.html', 'utf8');
  const entities = [
    { entity_id: 'light.fht_bedroom_2_all_lights', domain: 'light', state: 'off', area: "Chloe's Bedroom", friendly_name: "Chloe's Bedroom All Lights", original_friendly_name: 'Bedroom 2 All Lights' },
    { entity_id: 'light.fht_bedroom_2_fan_lights', domain: 'light', state: 'on', brightness: 255, area: "Chloe's Bedroom", friendly_name: "Chloe's Bedroom Fan Lights" },
    { entity_id: 'light.fht_bedroom_2_closet_lights', domain: 'light', state: 'off', area: "Chloe's Bedroom", friendly_name: "Chloe's Bedroom Closet Lights" },
    { entity_id: 'light.fht_dining_room_all_lights', domain: 'light', state: 'off', area: 'Dining Room', friendly_name: 'Dining Room Light' },
  ];
  const browser = await chromium.launch({ headless: true });
  try {
    for (const width of [1280, 390]) {
      const page = await browser.newPage({ viewport: { width, height: 900 } });
      const errors = [];
      const actions = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.route('**/*', route => {
        const url = new URL(route.request().url());
        if (url.pathname === '/') return route.fulfill({ contentType: 'text/html', body: html });
        if (/\.(png|webp|jpg)$/.test(url.pathname)) return route.fulfill({ status: 404, body: '' });
        if (url.pathname === '/api/lighting/status') return route.fulfill({ json: { ok: true, entities, count: entities.length, stale: false } });
        if (url.pathname === '/api/lighting/action') { actions.push(route.request().postDataJSON()); return route.fulfill({ json: { ok: true } }); }
        return route.fulfill({ json: { ok: true, entities: [], floors: [], rooms: [], settings: {}, scenes: [], catalog: {}, current_modes: {}, house_settings: {}, buttons: [], control_settings: {}, aliases: {}, entries: [] } });
      });
      await page.goto('http://fht.test/');
      await page.waitForTimeout(1000);
      await page.evaluate(() => document.querySelector('[data-view="lighting"]')?.click());
      await page.waitForSelector('.lighting-area-card');
      const chloe = page.locator('.lighting-area-card', { hasText: "Chloe's Bedroom" });
      assert.deepEqual(await chloe.locator('.lighting-name-toggle').allTextContents(), ['Closet Lights', 'Fan Lights']);
      const [off, title, on] = await chloe.locator('.lighting-area-header > *').evaluateAll(nodes => nodes.map(node => ({ text: node.textContent.trim(), box: node.getBoundingClientRect().toJSON() })));
      assert.deepEqual([off.text, title.text, on.text], ['Off', "Chloe's Bedroom", 'On']);
      assert.ok(off.box.right <= title.box.left && title.box.right <= on.box.left, `Off, title, On sit in a row at ${width}px`);
      assert.deepEqual(await page.locator('.lighting-area-card', { hasText: 'Dining Room' }).locator('.lighting-name-toggle').allTextContents(), ['Light']);
      await chloe.getByRole('button', { name: "Turn every Chloe's Bedroom light on" }).click();
      await chloe.getByRole('button', { name: "Turn every Chloe's Bedroom light off" }).click();
      await page.waitForTimeout(200);
      const ids = ['light.fht_bedroom_2_all_lights', 'light.fht_bedroom_2_closet_lights', 'light.fht_bedroom_2_fan_lights'];
      assert.deepEqual(actions.map(({ action, entity_ids }) => [action, [...entity_ids].sort()]), [['turn_on', ids], ['turn_off', ids]]);
      assert.deepEqual(errors, []);
      await page.close();
      console.log(`Lighting room buttons passed at ${width}px`);
    }
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exit(1); });
