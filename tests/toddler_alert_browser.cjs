const fs = require('node:fs');
const nodePath = require('node:path');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.FHT_PLAYWRIGHT || 'playwright');

// A bedroom in Toddler mode whose door opened shows a big red alert at the top of the Dashboard;
// tapping it clears the alert by leaving Toddler mode (Day or Night, chosen by the App).
// Set FHT_SCREENSHOT_DIR to also save dashboard-<width>.png with the alert showing.
const WEB = 'future_homes_tech_app/web';
const TYPES = { png: 'image/png', webp: 'image/webp', jpg: 'image/jpeg' };
const MAVERICK = { area: 'Bedroom 3', display_name: 'Maverick\'s Bedroom', entity_id: 'input_boolean.fht_bedroom_3_toddler_alert', mode_entity_id: 'input_select.fht_bedroom_3_mode', last_changed: '2026-10-11T02:14:00+00:00' };
const NURSERY = { area: 'Nursery', display_name: 'Nursery', entity_id: 'input_boolean.fht_nursery_toddler_alert', mode_entity_id: 'input_select.fht_nursery_mode', last_changed: '' };

(async () => {
  const html = fs.readFileSync(`${WEB}/index.html`, 'utf8');
  const shots = process.env.FHT_SCREENSHOT_DIR || '';
  const browser = await chromium.launch({ headless: true });
  try {
    for (const [width, height] of [[390, 844], [1180, 820]]) {
      const page = await browser.newPage({ viewport: { width, height } });
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      let alerts = [MAVERICK, NURSERY];
      let failClear = false;
      const cleared = [];
      await page.route('**/*', route => {
        const url = new URL(route.request().url());
        const path = url.pathname.slice(1);
        if (url.pathname === '/') return route.fulfill({ contentType: 'text/html', body: html });
        const asset = nodePath.join(WEB, nodePath.basename(path));
        if (/\.(png|webp|jpg)$/.test(path)) {
          return fs.existsSync(asset)
            ? route.fulfill({ contentType: TYPES[path.split('.').pop()], body: fs.readFileSync(asset) })
            : route.fulfill({ status: 404, body: '' });
        }
        if (path === 'api/toddler/alerts') return route.fulfill({ json: { ok: true, toddler_alerts: alerts, stale: false } });
        if (path === 'api/toddler/clear') {
          const body = route.request().postDataJSON();
          cleared.push(body);
          if (failClear) return route.fulfill({ status: 502, json: { ok: false, error: 'Home Assistant returned HTTP 500.' } });
          alerts = alerts.filter(alert => alert.area !== body.area);
          return route.fulfill({ json: { ok: true, area: body.area, mode: 'Night' } });
        }
        return route.fulfill({ json: { ok: true, entities: [], floors: [] } });
      });
      await page.goto('http://fht.test/');
      const maverick = page.locator('[data-toddler-alert="Bedroom 3"]');
      await maverick.waitFor();
      assert.deepEqual(
        await page.locator('#view-home .toddler-awake-title').allTextContents(),
        ['Maverick’s awake', 'Nursery: toddler awake']
      );
      assert.equal(await maverick.evaluate(el => el.tagName), 'BUTTON');
      assert.match(await maverick.locator('.toddler-awake-detail').textContent(), /^Door opened at \d{1,2}:\d{2}.* · Tap to clear$/);
      assert.equal(await page.locator('[data-toddler-alert="Nursery"] .toddler-awake-detail').textContent(), 'Door opened · Tap to clear');
      // First thing on the Dashboard, unmistakably red, and no sideways scrolling.
      assert.equal(await page.locator('#view-home > *').first().getAttribute('id'), 'toddler-alerts');
      assert.equal(await maverick.evaluate(el => getComputedStyle(el).backgroundImage.includes('rgb(229, 41, 59)')), true);
      const box = await maverick.boundingBox();
      assert.ok(box.y < height / 2 && box.height >= 100, `alert sits high and large (${JSON.stringify(box)})`);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true);
      if (shots) {
        fs.mkdirSync(shots, { recursive: true });
        await page.screenshot({ path: nodePath.join(shots, `dashboard-${width}.png`) });
      }

      // A failed clear brings the alert back with the reason.
      failClear = true;
      await maverick.click();
      await page.locator('.toddler-awake-error').waitFor();
      assert.match(await page.locator('.toddler-awake-error').textContent(), /Couldn’t clear the alert: Home Assistant returned HTTP 500\./);
      assert.equal(await maverick.count(), 1);

      // Tapping clears it: the App leaves Toddler mode for that room, and the alert goes at once.
      failClear = false;
      const clearedResponse = page.waitForResponse(r => r.url().endsWith('api/toddler/clear'));
      await maverick.click();
      assert.equal(await maverick.count(), 0);
      assert.equal(await (await clearedResponse).json().then(body => body.mode), 'Night');
      assert.deepEqual(cleared, [{ area: 'Bedroom 3' }, { area: 'Bedroom 3' }]);
      assert.equal(await page.locator('.toddler-awake-error').count(), 0);
      assert.deepEqual(await page.locator('#view-home .toddler-awake-title').allTextContents(), ['Nursery: toddler awake']);

      // With no alert helper on, the Dashboard stays blank.
      alerts = [];
      await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
      await page.waitForFunction(() => document.querySelector('#toddler-alerts').hidden);
      assert.equal(await page.locator('[data-toddler-alert]').count(), 0);
      assert.deepEqual(errors, []);
      console.log(`Toddler awake alert passed at ${width}px`);
      await page.close();
    }
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exit(1); });
