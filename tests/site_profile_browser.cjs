const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const { chromium } = require(process.env.FHT_PLAYWRIGHT || 'playwright');

(async () => {
  const html = fs.readFileSync('future_homes_tech_app/web/index.html', 'utf8');
  // The real loader renders the payload: one changed value and one mistake.
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'fht-site-profile-'));
  const override = path.join(directory, 'site_profile.json');
  fs.writeFileSync(override, JSON.stringify({ timezone: 'America/Denver', weather_entity: 'sensor.outside' }));
  const profile = JSON.parse(execFileSync(process.env.FHT_PYTHON || 'python3', ['-B', 'future_homes_tech_app/fht_site.py', 'show'], {
    encoding: 'utf8', env: { ...process.env, FHT_SITE_PROFILE_PATH: override },
  }));
  fs.rmSync(directory, { recursive: true, force: true });
  assert.equal(profile.values.timezone, 'America/Denver');
  assert.equal(profile.problems.length, 1);
  const browser = await chromium.launch({ headless: true });
  try {
    for (const width of [1280, 390]) {
      const page = await browser.newPage({ viewport: { width, height: 900 } });
      const errors = [];
      const requests = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.route('**/*', route => {
        const url = new URL(route.request().url());
        const name = url.pathname.slice(1);
        requests.push({ method: route.request().method(), name });
        if (url.pathname === '/') return route.fulfill({ contentType: 'text/html', body: html });
        if (/\.(png|webp|jpg)$/.test(name)) return route.fulfill({ status: 404, body: '' });
        if (name === 'api/site-profile') return route.fulfill({ json: { ok: true, ...profile } });
        if (name === 'api/protect/arm-mode') return route.fulfill({ json: { ok: true, status: 'disarmed', arm_profile_name: '' } });
        if (name === 'api/protect/nvr-object') return route.fulfill({ json: { ok: true, arm_mode: {} } });
        if (name === 'api/protect/resources') return route.fulfill({ json: { ok: true, resources: {}, home_assistant_devices: {} } });
        return route.fulfill({ json: { ok: true, entities: [], floors: [] } });
      });
      await page.goto('http://fht.test/');
      await page.waitForTimeout(800);
      if (width < 800) await page.locator('#mobile-nav-toggle').click();
      await page.locator('#settings-toggle').click();
      await page.locator('[data-view="unifi"]').click();
      await page.waitForFunction(() => document.querySelector('#site-profile-values')?.textContent.includes('America/Denver'));
      const values = await page.locator('#site-profile-values').textContent();
      assert.match(values, /Protect console.*unifi\.fht\.internal\/proxy\/protect\/integration\/v1/);
      assert.match(values, /Time zone.*America\/Denver/);
      assert.match(values, /Weather entity.*weather\.forecast_home/);
      assert.match(values, /Device alarm rooms.*bridges, device alarms, fridges/);
      const detail = await page.locator('#site-profile-detail').textContent();
      assert.match(detail, /changes 1 value: timezone/);
      assert.match(detail, /restart the App/);
      assert.equal(await page.locator('#site-profile-detail .site-profile-problem').count(), 1);
      assert.match(await page.locator('#site-profile-detail .site-profile-problem').textContent(), /weather_entity/);
      assert.equal(await page.locator('#site-profile-panel button, #site-profile-panel input').count(), 0, 'the card is read-only');
      assert.equal(requests.filter(request => request.name === 'api/site-profile').length, 1);
      assert.equal(requests.some(request => request.method !== 'GET' && request.name === 'api/site-profile'), false);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true);
      assert.deepEqual(errors, []);
      console.log(`Site profile card passed at ${width}px`);
      await page.close();
    }
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
