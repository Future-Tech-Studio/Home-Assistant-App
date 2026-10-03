const fs = require('node:fs');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.FHT_PLAYWRIGHT || 'playwright');

(async () => {
  const html = fs.readFileSync('future_homes_tech_app/web/index.html', 'utf8');
  const rooms = [
    { area: 'Bedroom 6', name: "Chloe's Bedroom", entities: [
      { entity_id: 'light.bedroom_6_desk_light', friendly_name: 'Bedroom 6 Desk Light', state: 'on' },
      { entity_id: 'light.fht_bedroom_6_all_lights', friendly_name: "FHT - Chloe's Bedroom All Lights" },
      { entity_id: 'sensor.bedroom_6', friendly_name: 'Bedroom 6', state: '71.5', unit: '°F' },
      { entity_id: 'binary_sensor.bedroom_6_presence_with_a_very_long_entity_identifier_occupancy', friendly_name: 'Bedroom 6 Presence', state: 'unavailable' }] },
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
      // The header shows how long the page took to open.
      await page.waitForFunction(() => /^Server \d+(\.\d)? (ms|s) · Page \d+(\.\d)? (ms|s) · Data \d+(\.\d)? (ms|s)$/.test(document.getElementById('brand-timing')?.textContent || ''));
      if (width < 800) await page.locator('#mobile-nav-toggle').click();
      await page.locator('#settings-toggle').click();
      const menu = await page.locator('#settings-submenu [data-view]').evaluateAll(items => items.map(item => item.textContent.trim()));
      assert.deepEqual(menu.slice(0, 2), ['Room Devices', 'Home Configurator']);
      await page.locator('[data-view="room-devices"]').click();
      const list = page.locator('#room-devices-list');
      await list.getByRole('heading', { name: /Chloe's Bedroom/ }).waitFor();
      assert.deepEqual(await list.locator('.room-devices-room').first().locator('[role="row"]').nth(1).locator('[role="cell"]').allTextContents(),
        ['onDesk Light', 'light.bedroom_6_desk_light']);
      assert.deepEqual(await list.locator('.room-devices-room').first().locator('[role="cell"]:not(.room-devices-id)').allTextContents(),
        ['onDesk Light', '—All Lights', '71.5 °FBedroom 6', 'unavailablePresence'], 'Room prefixes are dropped; a name that is only the room stays whole');
      assert.deepEqual(await list.locator('.room-devices-room').first().locator('.room-devices-pill').evaluateAll(pills => pills.map(pill => pill.className)),
        ['room-devices-pill is-on', 'room-devices-pill is-off', 'room-devices-pill ', 'room-devices-pill is-unavailable'], 'Each entity shows its current state first; a blank tag keeps rows aligned');
      assert.equal(await list.locator('.room-devices-pill').evaluateAll(pills => new Set(pills.map(pill => Math.round(pill.getBoundingClientRect().width))).size), 1, 'Every state tag has the same width');
      assert.ok(await list.locator('.room-devices-pill.is-unavailable').evaluate(pill => pill.scrollWidth <= pill.clientWidth), '"unavailable" fits without truncation');
      if (process.env.FHT_SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.FHT_SCREENSHOT_DIR}/room-devices-${width}.png`, fullPage: true });
      await page.locator('#room-devices-filter').fill('kitchen pendant');
      assert.deepEqual(await list.locator('.room-devices-room h2').allTextContents(), ['Kitchen 1']);
      await page.locator('#room-devices-filter').fill('chloe');
      assert.equal(await list.locator('.room-devices-room [role="cell"].room-devices-id').count(), 4);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true, 'No horizontal overflow');
      assert.deepEqual(errors, []);
      console.log(`Room Devices page passed at ${width}px`);
      await page.close();
    }
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
