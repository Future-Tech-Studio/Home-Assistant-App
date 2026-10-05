const fs = require('node:fs');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.FHT_PLAYWRIGHT || 'playwright');

// A waiting Beta or Stable update shows in the header on every page in the menu,
// including the pages with the shared corner header (Dashboard, Doors, Lighting, ...).
(async () => {
  const html = fs.readFileSync('future_homes_tech_app/web/index.html', 'utf8');
  const browser = await chromium.launch({ headless: true });
  const cases = [
    { label: 'Beta 0.8.2 Available', update_available: false, beta: { beta_mode: true, running_version: '0.8.1', beta_available_version: '0.8.2', beta_update_available: true, beta_error: null } },
    { label: 'Update Available', update_available: true, beta: { beta_mode: false, running_version: '0.8.1', beta_available_version: '', beta_update_available: false, beta_error: null } },
    // Beta mode: an older Stable waiting in Home Assistant never replaces a newer Beta.
    { label: 'Beta 0.8.33 Available', update_available: true, info: { installed_version: '0.8.4', available_version: '0.8.7' }, beta: { beta_mode: true, running_version: '0.8.32', beta_available_version: '0.8.33', beta_update_available: true, beta_error: null } },
    { label: null, update_available: true, info: { installed_version: '0.8.4', available_version: '0.8.7' }, beta: { beta_mode: true, running_version: '0.8.33', beta_available_version: '0.8.33', beta_update_available: false, beta_error: null } },
    // A Stable newer than the running Beta is still offered.
    { label: 'Update Available', update_available: true, info: { installed_version: '0.8.4', available_version: '0.9.0' }, beta: { beta_mode: true, running_version: '0.8.33', beta_available_version: '0.8.33', beta_update_available: false, beta_error: null } },
  ];
  try {
    for (const { label, update_available, info = {}, beta } of cases) for (const width of [1280, 700, 390]) {
      const page = await browser.newPage({ viewport: { width, height: 900 } });
      const errors = [];
      const appUpdates = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.route('**/*', route => {
        const url = new URL(route.request().url());
        if (url.pathname === '/') return route.fulfill({ contentType: 'text/html', body: html });
        if (/\.(png|webp|jpg)$/.test(url.pathname)) return route.fulfill({ status: 404, body: '' });
        if (url.pathname === '/api/app-info') return route.fulfill({ json: { ok: true, installed_version: '0.8.1', available_version: '0.8.2', ...info, update_available, ...beta, site_profile: {} } });
        if (url.pathname === '/api/app/update') { appUpdates.push(route.request().method()); return route.fulfill({ json: { ok: true, version: '0.8.2', restarting: true } }); }
        if (url.pathname === '/api/health') return route.fulfill({ json: { ok: true, running_version: '0.8.1' } });
        if (url.pathname === '/api/beta/status') return route.fulfill({ json: { ok: true, ...beta } });
        return route.fulfill({ json: { ok: true, entities: [], floors: [], rooms: [], settings: {}, scenes: [], catalog: {}, current_modes: {}, house_settings: {}, buttons: [], control_settings: {}, aliases: {}, entries: [] } });
      });
      await page.goto('http://fht.test/');
      await page.waitForTimeout(1500);
      const button = page.locator('#update-app');
      if (label === null) {
        assert.ok(!(await button.isVisible()), `No update is offered over a newer running Beta at ${width}px`);
        assert.deepEqual(errors, []);
        await page.close();
        console.log(`Older Stable hidden in Beta mode at ${width}px`);
        continue;
      }
      assert.equal(await button.textContent(), label);
      const views = await page.evaluate(() => [...new Set([...document.querySelectorAll('[data-view]')].map(item => item.dataset.view))]);
      assert.ok(views.length >= 18, `Every menu page is checked (${views.join(', ')})`);
      for (const view of views) {
        await page.evaluate(name => document.querySelector(`[data-view="${name}"]`)?.click(), view);
        await page.waitForTimeout(250);
        assert.ok(await button.isVisible(), `${label} shows on ${view} at ${width}px`);
        const [update, updates] = await page.evaluate(() => ['#update-app', '#open-updates'].map(selector => document.querySelector(selector).getBoundingClientRect().toJSON()));
        if (updates.width) assert.ok(update.right <= updates.left, `It sits left of the Updates button on ${view} at ${width}px`);
      }
      if (!beta.beta_mode && width === 1280) {
        // A Stable update installs in place and waits to reload, instead of leaving the App.
        await button.click();
        await page.waitForTimeout(500);
        assert.deepEqual(appUpdates, ['POST']);
        assert.equal(await button.textContent(), 'Updating to 0.8.2…');
        assert.equal(new URL(page.url()).pathname, '/');
      }
      assert.deepEqual(errors, []);
      await page.close();
      console.log(`${label} passed on ${views.length} pages at ${width}px`);
    }
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exit(1); });
