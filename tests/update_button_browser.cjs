const fs = require('node:fs');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.FHT_PLAYWRIGHT || 'playwright');

// A waiting Beta (or App) update shows in the header on every page, including the
// pages with the shared corner header (Dashboard, Doors, Lighting, Home Configurator, ...).
(async () => {
  const html = fs.readFileSync('future_homes_tech_app/web/index.html', 'utf8');
  const browser = await chromium.launch({ headless: true });
  const beta = { beta_mode: true, running_version: '0.8.1', beta_available_version: '0.8.2', beta_update_available: true, beta_error: null };
  try {
    for (const width of [1280, 700, 390]) {
      const page = await browser.newPage({ viewport: { width, height: 900 } });
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.route('**/*', route => {
        const url = new URL(route.request().url());
        if (url.pathname === '/') return route.fulfill({ contentType: 'text/html', body: html });
        if (/\.(png|webp|jpg)$/.test(url.pathname)) return route.fulfill({ status: 404, body: '' });
        if (url.pathname === '/api/app-info') return route.fulfill({ json: { ok: true, installed_version: '0.8.1', update_available: false, ...beta, site_profile: {} } });
        if (url.pathname === '/api/beta/status') return route.fulfill({ json: { ok: true, ...beta } });
        return route.fulfill({ json: { ok: true, entities: [], floors: [], rooms: [], settings: {}, scenes: [], catalog: {}, current_modes: {}, house_settings: {}, buttons: [], control_settings: {}, aliases: {}, entries: [] } });
      });
      await page.goto('http://fht.test/');
      await page.waitForTimeout(1500);
      const button = page.locator('#update-app');
      assert.equal(await button.textContent(), 'Beta 0.8.2 Available');
      for (const view of ['home', 'doors', 'switches', 'rooms', 'lighting', 'security', 'environment', 'room-devices', 'presence', 'scenes']) {
        await page.evaluate(name => document.querySelector(`[data-view="${name}"]`)?.click(), view);
        await page.waitForTimeout(250);
        assert.ok(await button.isVisible(), `The Beta update button shows on ${view} at ${width}px`);
        const [update, updates] = await page.evaluate(() => ['#update-app', '#open-updates'].map(selector => document.querySelector(selector).getBoundingClientRect().toJSON()));
        if (updates.width) assert.ok(update.right <= updates.left, `It sits left of the Updates button on ${view} at ${width}px`);
      }
      assert.deepEqual(errors, []);
      await page.close();
      console.log(`Update button passed at ${width}px`);
    }
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exit(1); });
