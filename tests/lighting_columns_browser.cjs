const fs = require('node:fs');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.FHT_PLAYWRIGHT || 'playwright');

// Lighting shows two columns of room cards from iPad portrait up, and follows
// the window when it is resized, but one column on a phone.
(async () => {
  const html = fs.readFileSync('future_homes_tech_app/web/index.html', 'utf8');
  const rooms = ['Dining Room', 'Pantry', 'Kitchen', 'Outside Perimeter', "Maverick's Bedroom", "Chloe's Bedroom"];
  const entities = rooms.flatMap(room => {
    const slug = room.toLowerCase().replace(/[^a-z0-9]+/g, '_');
    return [
      { entity_id: `light.fht_${slug}_all_lights`, domain: 'light', state: 'on', brightness: 200, area: room, friendly_name: `${room} All Lights` },
      { entity_id: `light.fht_${slug}_fan_lights`, domain: 'light', state: 'off', area: room, friendly_name: `${room} Fan Lights` },
    ];
  });
  const columns = page => page.evaluate(() => new Set([...document.getElementById('lighting-area-grid').children]
    .map(card => Math.round(card.getBoundingClientRect().left))).size);
  const browser = await chromium.launch({ headless: true });
  try {
    for (const [width, height, expected] of [[390, 844, 1], [768, 1024, 2], [820, 1180, 2], [1024, 768, 2], [1180, 820, 3]]) {
      const page = await browser.newPage({ viewport: { width, height } });
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.route('**/*', route => {
        const url = new URL(route.request().url());
        if (url.pathname === '/') return route.fulfill({ contentType: 'text/html', body: html });
        if (/\.(png|webp|jpg)$/.test(url.pathname)) return route.fulfill({ status: 404, body: '' });
        if (url.pathname === '/api/lighting/status') return route.fulfill({ json: { ok: true, entities, count: entities.length, stale: false } });
        return route.fulfill({ json: { ok: true, entities: [], floors: [], rooms: [], settings: {}, scenes: [], catalog: {}, current_modes: {}, house_settings: {}, buttons: [], control_settings: {}, aliases: {}, entries: [] } });
      });
      await page.goto('http://fht.test/');
      await page.waitForTimeout(800);
      await page.evaluate(() => document.querySelector('[data-view="lighting"]')?.click());
      await page.waitForSelector('.lighting-area-card');
      await page.waitForTimeout(300);
      assert.equal(await columns(page), expected, `${expected} column(s) at ${width}px`);
      if (width === 768) {
        // Turning the iPad (or widening the window) re-flows the cards live.
        await page.setViewportSize({ width: 1180, height: 820 });
        await page.waitForTimeout(400);
        assert.equal(await columns(page), 3, 'Three columns after widening to 1180px');
        await page.setViewportSize({ width: 768, height: 1024 });
        await page.waitForTimeout(400);
        assert.equal(await columns(page), 2, 'Two columns again at 768px');
      }
      assert.deepEqual(errors, []);
      await page.close();
      console.log(`Lighting columns passed at ${width}px`);
    }
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exit(1); });
