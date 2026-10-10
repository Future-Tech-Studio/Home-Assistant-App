const fs = require('node:fs');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.FHT_PLAYWRIGHT || 'playwright');

// Another device installs an App update and Home Assistant drops the App's
// panel, sending this screen (a wall panel, say) to its default dashboard.
// Once the new version answers, this screen opens the App again by itself.
// A plain outage with no new version never moves the screen.
(async () => {
  const html = fs.readFileSync('future_homes_tech_app/web/index.html', 'utf8');
  const clientVersion = html.match(/const CLIENT_VERSION = "([^"]+)"/)[1];
  const host = `<!doctype html><html><head></head><body><home-assistant></home-assistant>
    <iframe id="app" src="/api/hassio_ingress/token/" style="width:1280px;height:800px"></iframe>
    <script>
      document.querySelector('home-assistant').hass = { panels: { fht_app: {}, lovelace: {} }, states: {} };
      window.navigations = [];
      window.addEventListener('location-changed', () => window.navigations.push(location.pathname));
    </script></body></html>`;
  let runningVersion = clientVersion;
  let appDown = false;
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/*', async route => {
      const url = new URL(route.request().url());
      if (url.pathname === '/fht_app') return route.fulfill({ contentType: 'text/html', body: host });
      if (url.pathname === '/api/hassio_ingress/token/') return route.fulfill({ contentType: 'text/html', body: html });
      if (/\.(png|webp|jpg)$/.test(url.pathname)) return route.fulfill({ status: 404, body: '' });
      if (appDown && url.pathname.includes('/api/')) return route.fulfill({ status: 502, contentType: 'text/html', body: 'Bad gateway' });
      if (url.pathname.endsWith('/api/health')) return route.fulfill({ json: { ok: true, running_version: runningVersion } });
      if (url.pathname.endsWith('/api/app-info')) return route.fulfill({ json: { ok: true, installed_version: runningVersion, running_version: runningVersion, available_version: runningVersion, update_available: false, beta_mode: false, site_profile: {} } });
      if (url.pathname.endsWith('/api/live/revision')) {
        await new Promise(resolve => setTimeout(resolve, 300));
        return route.fulfill({ json: { ok: true, revision: 1, changed: false, running_version: runningVersion } });
      }
      return route.fulfill({ json: { ok: true, entities: [], floors: [], rooms: [], settings: {}, scenes: [], catalog: {}, current_modes: {}, house_settings: {}, buttons: [], control_settings: {}, aliases: {}, entries: [] } });
    });
    await page.goto('http://fht.test/fht_app');
    await page.waitForTimeout(9000);

    // A short outage with the same version: nothing moves, the watcher stops.
    appDown = true;
    await page.waitForTimeout(4000);
    assert.ok(await page.evaluate(() => window.fhtUpdateWatcherPassive), 'Losing the App starts a watcher in Home Assistant');
    appDown = false;
    await page.waitForTimeout(4000);
    assert.ok(await page.evaluate(() => !window.fhtUpdateWatcher), 'The App answers on the same version: the watcher stops');

    // Someone else updates: the App goes down and Home Assistant drops its panel.
    appDown = true;
    await page.waitForTimeout(4000);
    await page.evaluate(() => {
      document.getElementById('app').remove();
      delete document.querySelector('home-assistant').hass.panels.fht_app;
      history.pushState(null, '', '/lovelace/wall');
    });
    await page.waitForTimeout(4000);
    assert.equal(new URL(page.url()).pathname, '/lovelace/wall', 'It waits while the update installs');

    runningVersion = '99.0.0';
    appDown = false;
    await page.evaluate(() => { document.querySelector('home-assistant').hass.panels.fht_app = {}; });
    await page.waitForTimeout(4000);
    assert.equal(new URL(page.url()).pathname, '/fht_app', 'Home Assistant opens the App again');
    assert.deepEqual(await page.evaluate(() => window.navigations), ['/fht_app']);
    assert.ok(await page.evaluate(() => !window.fhtUpdateWatcher), 'The watcher stops');
    assert.deepEqual(errors, []);
    console.log('Other screens return to the App after an update passed');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exit(1); });
