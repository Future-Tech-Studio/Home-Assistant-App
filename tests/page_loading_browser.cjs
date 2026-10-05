const fs = require('node:fs');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.FHT_PLAYWRIGHT || 'playwright');

// Opening a page shows the thin loading bar at the top while its data loads, never a "Loading …" line.
const LIGHTS = [
  { entity_id: 'light.fht_kitchen', friendly_name: 'Kitchen Lights', state: 'on', area: 'Kitchen', brightness: 200 },
  { entity_id: 'light.fht_dining_room', friendly_name: 'Dining Room Lights', state: 'off', area: 'Dining Room' },
];
const PAGES = [
  { view: 'lighting', bar: '#lighting-load-progress' },
  { view: 'security', bar: '#page-load-progress', settings: false },
  { view: 'room-devices', bar: '#room-devices-load-progress' },
  { view: 'buttons', bar: '#page-load-progress' },
  { view: 'climate-settings', bar: '#page-load-progress' },
  { view: 'room-modes', bar: '#page-load-progress' },
  { view: 'scenes', bar: '#page-load-progress' },
];

(async () => {
  const html = fs.readFileSync('future_homes_tech_app/web/index.html', 'utf8');
  const browser = await chromium.launch({ headless: true });
  try {
    for (const width of [1280, 390]) {
      const page = await browser.newPage({ viewport: { width, height: 800 } });
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      let holding = false;
      let held = [];
      const release = () => { holding = false; held.splice(0).forEach(resolve => resolve()); };
      await page.route('**/*', async route => {
        const url = new URL(route.request().url());
        if (url.pathname === '/') return route.fulfill({ contentType: 'text/html', body: html });
        if (/\.(png|webp|jpg)$/.test(url.pathname)) return route.fulfill({ status: 404, body: '' });
        if (holding && url.pathname.startsWith('/api/')) await new Promise(resolve => held.push(resolve));
        if (url.pathname === '/api/lighting/status') return route.fulfill({ json: { ok: true, entities: LIGHTS } });
        return route.fulfill({ json: { ok: true, entities: [], floors: [], rooms: [], buttons: [], scenes: [], settings: {}, entries: [], schedules: {}, single_lights: [] } });
      });
      await page.goto('http://fht.test/');
      await page.waitForTimeout(800);
      for (const { view, bar } of PAGES) {
        if (width < 800 && !(await page.locator('body.mobile-nav-open').count())) await page.locator('#mobile-nav-toggle').click();
        const item = page.locator(`[data-view="${view}"]`).first();
        if (!(await item.isVisible())) await page.locator('#settings-toggle').click();
        holding = true;
        await item.click();
        const progress = page.locator(bar);
        await progress.waitFor({ state: 'visible' });
        const box = await progress.boundingBox();
        assert.ok(box.y < 60 && box.height <= 8, `${view}: the bar sits in the header (${JSON.stringify(box)})`);
        const loadingLines = await page.locator(`#view-${view} :is(.entity-state, [role="status"])`).evaluateAll(nodes =>
          nodes.filter(node => node.offsetParent && /loading/i.test(node.textContent)).map(node => node.textContent));
        assert.deepEqual(loadingLines, [], `${view}: no loading text while the bar shows`);
        release();
        await progress.waitFor({ state: 'hidden' });
        if (view === 'lighting') {
          assert.equal(await page.locator('.lighting-row').count(), 2);
          assert.equal(await page.locator('#lighting-area-grid').evaluate(grid => getComputedStyle(grid).visibility), 'visible');
        }
      }
      assert.deepEqual(errors, []);
      await page.close();
      console.log(`Page loading bars passed at ${width}px`);
    }
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exit(1); });
