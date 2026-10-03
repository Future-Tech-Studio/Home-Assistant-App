const fs = require('node:fs');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.FHT_PLAYWRIGHT || 'playwright');

// The Revert Changes card in Home Configurator lists the recent saves on every
// settings page; each row can be reverted, and a revert can be reverted again.
(async () => {
  const html = fs.readFileSync('future_homes_tech_app/web/index.html', 'utf8');
  const browser = await chromium.launch({ headless: true });
  try {
    for (const width of [1280, 390]) {
      const page = await browser.newPage({ viewport: { width, height: 900 } });
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      const reverts = [];
      let failNextRevert = false;
      let entries = [
        { timestamp: '20261003T140200000000Z', saved_at: new Date(Date.now() - 3 * 60000).toISOString(), page: 'switches', page_label: 'Switches, Doors and Buttons', store: 'switch_control_settings.json', label: 'Switch, door and button actions', summary: 'Changed Kitchen' },
        { timestamp: '20261003T130000000000Z', saved_at: new Date(Date.now() - 65 * 60000).toISOString(), page: 'presence', page_label: 'Presence', store: 'presence_light_group_timings.json', label: 'Presence delays', summary: '' },
        { timestamp: '20261002T090000000000Z', saved_at: new Date(Date.now() - 26 * 3600000).toISOString(), page: 'rooms', page_label: 'Home Configurator', store: 'room_aliases.json', label: 'Room names', summary: 'Added Bedroom 6' },
      ];
      await page.route('**/*', route => {
        const request = route.request();
        const url = new URL(request.url());
        if (url.pathname === '/') return route.fulfill({ contentType: 'text/html', body: html });
        if (/\.(png|webp|jpg)$/.test(url.pathname)) return route.fulfill({ status: 404, body: '' });
        if (url.pathname === '/api/settings/history') {
          assert.equal(url.searchParams.get('page'), null, 'The card asks for every page at once');
          return route.fulfill({ json: { ok: true, entries } });
        }
        if (url.pathname === '/api/settings/revert') {
          const body = request.postDataJSON();
          reverts.push(body);
          if (failNextRevert) {
            failNextRevert = false;
            return route.fulfill({ status: 502, json: { ok: false, saved: true, activated: false, error: 'Home Assistant is restarting.' } });
          }
          // The revert is itself a saved change, listed first.
          entries = [{ ...entries.find(entry => entry.timestamp === body.timestamp), timestamp: '20261003T141500000000Z', saved_at: new Date().toISOString(), summary: 'Changed Kitchen' }, ...entries];
          return route.fulfill({ json: { ok: true, saved: true, restored: true, activated: true, entries: [] } });
        }
        return route.fulfill({ json: { ok: true, entities: [], floors: [], rooms: [], settings: {}, scenes: [], catalog: {}, current_modes: {}, house_settings: {}, buttons: [], control_settings: {}, aliases: {}, entries: [] } });
      });
      await page.goto('http://fht.test/');
      await page.waitForTimeout(800);
      if (width < 800) await page.locator('#mobile-nav-toggle').click();
      await page.locator('#settings-toggle').click();
      await page.locator('[data-view="rooms"]').click();
      const list = page.locator('#revert-changes-list');
      await list.locator('.revert-change-row').first().waitFor();
      assert.equal(await page.locator('.revert-changes-title').innerText(), 'Revert Changes');
      assert.equal(await list.locator('.revert-change-row').count(), 3);
      const firstRow = list.locator('.revert-change-row').first();
      assert.ok((await firstRow.innerText()).includes('Switches, Doors and Buttons · Switch, door and button actions'));
      assert.ok((await firstRow.innerText()).includes('3 min ago'));
      assert.ok((await firstRow.innerText()).includes('— Changed Kitchen'));
      assert.ok((await list.locator('.revert-change-row').nth(1).innerText()).includes('1 hour ago'));
      assert.equal(await page.locator('[data-settings-undo]').count(), 0, 'No per-page undo pills remain');
      const button = firstRow.locator('.revert-change-button');
      const box = await button.boundingBox();
      assert.ok(box && box.x >= 0 && box.x + box.width <= width + 1 && box.height >= 24, `Revert button inside the ${width}px viewport`);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true, 'No horizontal overflow');
      if (process.env.FHT_SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.FHT_SCREENSHOT_DIR}/revert-changes-${width}.png`, fullPage: true });

      // Closing keeps the current settings.
      await button.click();
      await page.waitForSelector('#settings-undo-dialog[open]');
      const text = await page.locator('#settings-undo-dialog-text').innerText();
      assert.ok(text.includes('This puts Switch, door and button actions back to how it was before the change saved 3 min ago'), text);
      assert.equal(await page.locator('#settings-undo-dialog-note').innerText(), 'That change: Changed Kitchen.');
      await page.locator('#settings-undo-dialog-close').click();
      await page.waitForFunction(() => !document.getElementById('settings-undo-dialog').open);
      assert.equal(reverts.length, 0);
      // A failed activation keeps the pop-up open with the error.
      failNextRevert = true;
      await button.click();
      await page.waitForSelector('#settings-undo-dialog[open]');
      await page.locator('#settings-undo-confirm').click();
      await page.waitForFunction(() => !document.getElementById('settings-undo-dialog-error').hidden);
      assert.equal(await page.locator('#settings-undo-dialog-error').innerText(), 'Saved, but Home Assistant activation failed: Home Assistant is restarting.');
      await page.locator('#settings-undo-dialog-close').click();
      await page.waitForFunction(() => !document.getElementById('settings-undo-dialog').open);
      // Confirming reverts the row's version; the list then shows the revert itself, newest first.
      await button.click();
      await page.waitForSelector('#settings-undo-dialog[open]');
      await page.locator('#settings-undo-confirm').click();
      await page.waitForFunction(() => !document.getElementById('settings-undo-dialog').open);
      assert.deepEqual(reverts.at(-1), { page: 'switches', store: 'switch_control_settings.json', timestamp: '20261003T140200000000Z' });
      await page.waitForFunction(() => document.querySelectorAll('#revert-changes-list .revert-change-row').length === 4);
      assert.ok((await list.locator('.revert-change-row').first().innerText()).includes('just now'), 'The revert can be reverted again');
      assert.deepEqual(errors, []);
      console.log(`Revert Changes card passed at ${width}px`);
      await page.close();
    }
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
