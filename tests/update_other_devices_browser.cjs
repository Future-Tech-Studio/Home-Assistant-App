const fs = require('node:fs');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.FHT_PLAYWRIGHT || 'playwright');

// When one device updates the App, every other open copy reloads onto the new
// version by itself and reopens on the page it was showing. If the reload still
// serves the old version, it offers the Refresh button instead of looping.
(async () => {
  const html = fs.readFileSync('future_homes_tech_app/web/index.html', 'utf8');
  const clientVersion = html.match(/const CLIENT_VERSION = "([^"]+)"/)[1];
  let runningVersion = clientVersion;
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
    const errors = [];
    const loads = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/*', async route => {
      const url = new URL(route.request().url());
      if (url.pathname === '/') {
        loads.push(url.search);
        return route.fulfill({ contentType: 'text/html', body: html });
      }
      if (/\.(png|webp|jpg)$/.test(url.pathname)) return route.fulfill({ status: 404, body: '' });
      if (url.pathname === '/api/app-info') return route.fulfill({ json: { ok: true, installed_version: runningVersion, running_version: runningVersion, available_version: clientVersion, update_available: false, beta_mode: false, site_profile: {} } });
      if (url.pathname === '/api/live/revision') {
        await new Promise(resolve => setTimeout(resolve, 300));
        return route.fulfill({ json: { ok: true, revision: 1, changed: false, running_version: runningVersion } });
      }
      return route.fulfill({ json: { ok: true, entities: [], floors: [], rooms: [], settings: {}, scenes: [], catalog: {}, current_modes: {}, house_settings: {}, buttons: [], control_settings: {}, aliases: {}, entries: [] } });
    });
    await page.goto('http://fht.test/');
    await page.waitForTimeout(1500);
    await page.locator('[data-view="lighting"]').evaluate(button => button.click());
    await page.waitForTimeout(8000);
    assert.equal(loads.length, 1, 'Nothing reloads while the version matches');

    // A dialog left open waits for it to close before reloading.
    await page.evaluate(() => {
      const dialog = document.createElement('dialog');
      dialog.id = 'test-dialog';
      document.body.append(dialog);
      dialog.show();
    });
    runningVersion = '99.0.0';
    await page.waitForTimeout(3000);
    assert.equal(loads.length, 1, 'An open dialog holds the reload');
    await page.evaluate(() => document.getElementById('test-dialog').close());
    await page.waitForTimeout(3000);
    assert.equal(loads.length, 2, 'Another device updated the App: this copy reloads');
    assert.match(loads[1], /fht_refresh=/);
    assert.ok(await page.locator('#view-lighting').isVisible(), 'It reopens on the page it was showing');

    // The reload still served the old version: no second reload, offer Refresh.
    await page.waitForTimeout(9000);
    assert.equal(loads.length, 2, 'It does not reload in a loop');
    assert.equal(await page.evaluate(() => document.getElementById('refresh-app').hidden), false, 'The Refresh button is offered instead');
    assert.deepEqual(errors, []);
    console.log('Other devices reload after an update passed');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exit(1); });
