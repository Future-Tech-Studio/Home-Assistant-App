const fs = require('node:fs');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.FHT_PLAYWRIGHT || 'playwright');

// When an App update makes Home Assistant leave the App's panel (it opens the
// default dashboard), Home Assistant opens the App again once the new version
// answers, and the App reopens on the page it was showing.
(async () => {
  const html = fs.readFileSync('future_homes_tech_app/web/index.html', 'utf8');
  const host = `<!doctype html><html><head></head><body><home-assistant></home-assistant>
    <iframe id="app" src="/api/hassio_ingress/token/" style="width:1280px;height:800px"></iframe>
    <script>
      document.querySelector('home-assistant').hass = { panels: { fht_app: {}, lovelace: {} }, states: {} };
      window.navigations = [];
      window.addEventListener('location-changed', () => window.navigations.push(location.pathname));
    </script></body></html>`;
  let runningVersion = '0.8.1';
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/*', route => {
      const url = new URL(route.request().url());
      if (url.pathname === '/fht_app') return route.fulfill({ contentType: 'text/html', body: host });
      if (url.pathname === '/api/hassio_ingress/token/') return route.fulfill({ contentType: 'text/html', body: html });
      if (/\.(png|webp|jpg)$/.test(url.pathname)) return route.fulfill({ status: 404, body: '' });
      if (url.pathname.endsWith('/api/app-info')) return route.fulfill({ json: { ok: true, installed_version: runningVersion, available_version: '0.8.2', update_available: runningVersion === '0.8.1', beta_mode: false, site_profile: {} } });
      if (url.pathname.endsWith('/api/app/update')) return route.fulfill({ json: { ok: true, version: '0.8.2', restarting: true, entity_id: 'update.fht_app_update' } });
      if (url.pathname.endsWith('/api/health')) return route.fulfill({ json: { ok: true, running_version: runningVersion } });
      return route.fulfill({ json: { ok: true, entities: [], floors: [], rooms: [], settings: {}, scenes: [], catalog: {}, current_modes: {}, house_settings: {}, buttons: [], control_settings: {}, aliases: {}, entries: [] } });
    });
    await page.goto('http://fht.test/fht_app');
    const app = page.frameLocator('#app');
    await page.waitForTimeout(1500);
    await app.locator('[data-view="lighting"]').evaluate(button => button.click());
    await app.locator('#update-app').click();
    await page.waitForTimeout(500);
    assert.equal(await app.locator('#update-app').textContent(), 'Updating to 0.8.2…');

    // Home Assistant drops the App's panel and opens the wall dashboard.
    await page.evaluate(() => {
      document.getElementById('app').remove();
      delete document.querySelector('home-assistant').hass.panels.fht_app;
      history.pushState(null, '', '/lovelace/wall');
    });
    await page.waitForTimeout(4000);
    assert.equal(new URL(page.url()).pathname, '/lovelace/wall', 'It waits while the update installs');

    // The update finishes: the panel is back and the new version answers.
    runningVersion = '0.8.2';
    await page.evaluate(() => {
      const hass = document.querySelector('home-assistant').hass;
      hass.panels.fht_app = {};
      hass.states['update.fht_app_update'] = { attributes: { installed_version: '0.8.2', in_progress: false } };
    });
    await page.waitForTimeout(4000);
    assert.equal(new URL(page.url()).pathname, '/fht_app', 'Home Assistant opens the App again');
    assert.deepEqual(await page.evaluate(() => window.navigations), ['/fht_app']);

    // Home Assistant draws the App's panel again: the App opens on Lighting.
    await page.evaluate(() => {
      const frame = document.createElement('iframe');
      frame.id = 'app';
      frame.src = '/api/hassio_ingress/token/';
      frame.style.cssText = 'width:1280px;height:800px';
      document.body.append(frame);
    });
    await page.waitForTimeout(1500);
    assert.ok(await app.locator('#view-lighting').isVisible(), 'The App reopens on the page it was showing');
    assert.ok(await page.evaluate(() => !window.fhtUpdateWatcher), 'The watcher stops');
    assert.deepEqual(errors, []);
    console.log('Update returns to the App page passed');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exit(1); });
