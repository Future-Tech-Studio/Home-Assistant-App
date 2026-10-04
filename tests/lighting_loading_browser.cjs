const fs = require('node:fs');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.FHT_PLAYWRIGHT || 'playwright');

// Lighting: while the light groups load, the page shows the shared top loading bar, not a "Loading lighting…" line.
(async () => {
  const html = fs.readFileSync('future_homes_tech_app/web/index.html', 'utf8');
  const browser = await chromium.launch({ headless: true });
  try {
    for (const width of [1280, 390]) {
      const page = await browser.newPage({ viewport: { width, height: 800 } });
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      let release;
      const gate = new Promise(resolve => { release = resolve; });
      await page.route('**/*', async route => {
        const url = new URL(route.request().url());
        if (url.pathname === '/') return route.fulfill({ contentType: 'text/html', body: html });
        if (/\.(png|webp|jpg)$/.test(url.pathname)) return route.fulfill({ status: 404, body: '' });
        if (url.pathname === '/api/lighting/status') {
          await gate;
          return route.fulfill({ json: { ok: true, entities: [
            { entity_id: 'light.fht_kitchen', friendly_name: 'Kitchen Lights', state: 'on', area: 'Kitchen', brightness: 200 },
            { entity_id: 'light.fht_dining_room', friendly_name: 'Dining Room Lights', state: 'off', area: 'Dining Room' },
          ] } });
        }
        return route.fulfill({ json: { ok: true, entities: [], floors: [], rooms: [], settings: {}, entries: [] } });
      });
      await page.goto('http://fht.test/');
      await page.waitForTimeout(800);
      if (width < 800) await page.locator('#mobile-nav-toggle').click();
      await page.locator('[data-view="lighting"]').first().click();
      const progress = page.locator('#lighting-load-progress');
      await progress.waitFor({ state: 'visible' });
      assert.equal(await page.locator('#lighting-state').isVisible(), false, 'No "Loading lighting…" line while the bar shows');
      const box = await progress.boundingBox();
      assert.ok(box.y < 40 && box.height <= 8, `The bar sits in the header like the other pages (${JSON.stringify(box)})`);
      release();
      await page.locator('.lighting-control-card').first().waitFor();
      await progress.waitFor({ state: 'hidden' });
      assert.equal(await page.locator('.lighting-control-card').count(), 2);
      assert.equal(await page.locator('#lighting-area-grid').evaluate(grid => getComputedStyle(grid).visibility), 'visible');
      assert.deepEqual(errors, []);
      await page.close();
    }
  } finally {
    await browser.close();
  }
  console.log('Lighting loading bar browser check passed.');
})().catch(error => { console.error(error); process.exit(1); });
