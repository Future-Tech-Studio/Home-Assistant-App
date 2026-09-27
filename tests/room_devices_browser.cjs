const fs = require('node:fs');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.FHT_PLAYWRIGHT || 'playwright');

(async () => {
  const html = fs.readFileSync('future_homes_tech_app/web/index.html', 'utf8');
  const rooms = [
    { area: 'Bedroom 6', name: "Chloe's Bedroom", entities: [
      { entity_id: 'light.bedroom_6_desk_light', friendly_name: 'Bedroom 6 Desk Light' },
      { entity_id: 'binary_sensor.bedroom_6_presence_with_a_very_long_entity_identifier_occupancy', friendly_name: 'Bedroom 6 Presence' }] },
    { area: 'Kitchen', name: 'Kitchen', entities: [{ entity_id: 'light.kitchen_pendant', friendly_name: 'Kitchen Pendant' }] },
  ];
  const browser = await chromium.launch({ headless: true });
  try {
    for (const width of [1280, 390]) {
      const page = await browser.newPage({ viewport: { width, height: 900 } });
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.route('**/*', route => {
        const url = new URL(route.request().url());
        if (url.pathname === '/') return route.fulfill({ contentType: 'text/html', body: html });
        if (/\.(png|webp|jpg)$/.test(url.pathname)) return route.fulfill({ status: 404, body: '' });
        if (url.pathname === '/api/room-devices') return route.fulfill({ json: { ok: true, rooms } });
        return route.fulfill({ json: { ok: true, entities: [], floors: [] } });
      });
      await page.goto('http://fht.test/');
      await page.waitForTimeout(800);
      if (width < 800) await page.locator('#mobile-nav-toggle').click();
      await page.locator('#settings-toggle').click();
      const menu = await page.locator('#settings-submenu [data-view]').evaluateAll(items => items.map(item => item.textContent.trim()));
      assert.deepEqual(menu.slice(0, 2), ['Room Devices', 'Home Configurator']);
      await page.locator('[data-view="room-devices"]').click();
      const list = page.locator('#room-devices-list');
      await list.getByRole('heading', { name: /Chloe's Bedroom/ }).waitFor();
      assert.deepEqual(await list.locator('.room-devices-room').first().locator('[role="row"]').nth(1).locator('[role="cell"]').allTextContents(),
        ['Bedroom 6 Desk Light', 'light.bedroom_6_desk_light']);
      if (process.env.FHT_SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.FHT_SCREENSHOT_DIR}/room-devices-${width}.png`, fullPage: true });
      await page.locator('#room-devices-filter').fill('pendant');
      assert.deepEqual(await list.locator('.room-devices-room h2').allTextContents(), ['Kitchen 1']);
      await page.locator('#room-devices-filter').fill('chloe');
      assert.equal(await list.locator('.room-devices-room [role="cell"].room-devices-id').count(), 2);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true, 'No horizontal overflow');
      assert.deepEqual(errors, []);
      console.log(`Room Devices page passed at ${width}px`);
      await page.close();
    }
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
