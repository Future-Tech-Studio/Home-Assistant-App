const fs = require('node:fs');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.FHT_PLAYWRIGHT || 'playwright');

// Opening Lighting again shows the lights this device last saw while the live
// states load, without accepting taps, then the live states replace them.
(async () => {
  const html = fs.readFileSync('future_homes_tech_app/web/index.html', 'utf8');
  const light = state => [
    { entity_id: 'light.fht_kitchen', domain: 'light', friendly_name: 'Kitchen Lights', state, brightness: 200, area: 'Kitchen' },
    { entity_id: 'light.fht_dining_room', domain: 'light', friendly_name: 'Dining Room Lights', state: 'off', area: 'Dining Room' },
  ];
  let kitchen = 'on';
  let hold = null;
  const browser = await chromium.launch({ headless: true });
  try {
    const context = await browser.newContext({ viewport: { width: 1180, height: 820 } });
    await context.route('**/*', async route => {
      const url = new URL(route.request().url());
      if (url.pathname === '/') return route.fulfill({ contentType: 'text/html', body: html });
      if (/\.(png|webp|jpg)$/.test(url.pathname)) return route.fulfill({ status: 404, body: '' });
      if (url.pathname === '/api/lighting/status') {
        if (hold) await hold;
        return route.fulfill({ json: { ok: true, entities: light(kitchen), stale: false } });
      }
      return route.fulfill({ json: { ok: true, entities: [], floors: [], rooms: [], buttons: [], scenes: [], settings: {}, entries: [], schedules: {}, single_lights: [] } });
    });
    const open = async page => {
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.goto('http://fht.test/');
      await page.waitForTimeout(500);
      await page.evaluate(() => document.querySelector('[data-view="lighting"]').click());
      return errors;
    };

    // First visit: nothing saved yet, so the cards wait for the live states.
    const first = await context.newPage();
    const firstErrors = await open(first);
    await first.waitForSelector('.lighting-row');
    await first.waitForFunction(() => document.getElementById('lighting-load-progress').hidden);
    assert.deepEqual(firstErrors, []);
    await first.close();

    // Next open: the saved cards show at once while Home Assistant is slow.
    kitchen = 'off';
    let release;
    hold = new Promise(resolve => { release = resolve; });
    const second = await context.newPage();
    const errors = await open(second);
    await second.waitForSelector('.lighting-row');
    const grid = second.locator('#lighting-area-grid');
    assert.equal(await grid.evaluate(node => getComputedStyle(node).visibility), 'visible', 'saved cards are visible');
    assert.equal(await grid.evaluate(node => getComputedStyle(node).pointerEvents), 'none', 'saved cards ignore taps');
    assert.equal(await second.locator('#lighting-load-progress').isVisible(), true, 'loading bar still shows');
    assert.equal(await second.locator('.lighting-row.is-on').count(), 1, 'kitchen shows its saved state');

    release();
    hold = null;
    await second.waitForFunction(() => document.getElementById('lighting-load-progress').hidden);
    assert.equal(await second.locator('.lighting-row.is-on').count(), 0, 'live state replaces the saved one');
    assert.equal(await grid.evaluate(node => getComputedStyle(node).pointerEvents), 'auto', 'cards accept taps again');
    assert.deepEqual(errors, []);
    console.log('Lighting saved-view open passed');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exit(1); });
