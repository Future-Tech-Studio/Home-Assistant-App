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
      // The header no longer shows page-opening times.
      assert.equal(await page.locator('#brand-timing').count(), 0);
      if (width < 800) await page.locator('#mobile-nav-toggle').click();
      await page.locator('#settings-toggle').click();
      const menu = await page.locator('#settings-submenu [data-view]').evaluateAll(items => items.map(item => item.textContent.trim()));
      assert.deepEqual(menu.slice(0, 2), ['Room Devices', 'Home Configurator']);
      await page.locator('[data-view="room-devices"]').click();
      const list = page.locator('#room-devices-list');
      await list.getByRole('heading', { name: /Chloe's Bedroom/ }).waitFor();
      assert.deepEqual(await list.locator('.room-devices-room').first().locator('[role="row"]').nth(1).locator('[role="cell"]').allTextContents(),
        ['Desk Light', 'light.bedroom_6_desk_light']);
      assert.deepEqual(await list.locator('.room-devices-room').first().locator('[role="cell"]:not(.room-devices-id)').allTextContents(),
        ['Desk Light', 'All Lights', 'Bedroom 6', 'Presence'], 'Room prefixes are dropped; a name that is only the room stays whole');
      assert.equal(await list.locator('.room-devices-pill').count(), 0, 'No status tag before each name');
      const [nameCell, idCell] = await list.locator('.room-devices-room').first().locator('[role="row"]').nth(1).locator('[role="cell"]').evaluateAll(cells => cells.map(cell => cell.getBoundingClientRect()));
      if (width < 600) {
        assert.ok(idCell.top >= nameCell.bottom - 1, 'On a phone the entity ID sits under the name');
        assert.equal(await list.locator('.room-devices-head').first().isVisible(), false, 'Column headings are hidden on a phone');
      } else {
        assert.ok(Math.abs(idCell.top - nameCell.top) < 2 && idCell.left > nameCell.right, 'Wide screens keep name and entity ID side by side');
        assert.equal(await list.locator('.room-devices-head').first().isVisible(), true);
      }
      if (process.env.FHT_SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.FHT_SCREENSHOT_DIR}/room-devices-${width}.png`, fullPage: true });
      await page.locator('#room-devices-filter').fill('kitchen pendant');
      assert.deepEqual(await list.locator('.room-devices-room h2').allTextContents(), ['Kitchen 1']);
      await page.locator('#room-devices-filter').fill('chloe');
      assert.equal(await list.locator('.room-devices-room [role="cell"].room-devices-id').count(), 4);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true, 'No horizontal overflow');
      // Same header as Doors, Switches and Environment.
      assert.equal(await page.evaluate(() => document.body.classList.contains('room-devices-view-active')), true);
      assert.equal(await page.evaluate(() => Boolean(document.querySelector('.page-actions-primary > #room-devices-toolbar'))), true, 'Room Devices title lives in the shared header bar');
      assert.equal(await page.locator('.page-actions').evaluate(element => getComputedStyle(element).height), '0px', 'Header bar collapses like Switches');
      const columns = await page.locator('#room-devices-list').evaluate(list => getComputedStyle(list).gridTemplateColumns.split(' ').length);
      assert.equal(columns, width >= 1280 ? 2 : 1, `Room Devices is at most two columns (${columns} at ${width}px)`);
      await page.setViewportSize({ width: 2400, height: 900 });
      assert.equal(await page.locator('#room-devices-list').evaluate(list => getComputedStyle(list).gridTemplateColumns.split(' ').length), 2, 'Still two columns on a very wide screen');
      await page.setViewportSize({ width, height: 900 });
      assert.deepEqual(errors, []);
      console.log(`Room Devices page passed at ${width}px`);
      await page.close();
    }
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
