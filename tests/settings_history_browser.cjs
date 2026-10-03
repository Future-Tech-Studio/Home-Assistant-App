const fs = require('node:fs');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.FHT_PLAYWRIGHT || 'playwright');

// Settings pages that show "Undo last change", with the menu item that opens each
// and the store the mocked history reports for it.
const PAGES = [
  { view: 'doors', menu: 'doors', store: 'switch_control_settings.json', label: 'Switch, door and button actions' },
  { view: 'switches', menu: 'switches', store: 'switch_control_settings.json', label: 'Switch, door and button actions' },
  { view: 'buttons', menu: 'buttons', store: 'switch_control_settings.json', label: 'Switch, door and button actions' },
  { view: 'presence', menu: 'presence', store: 'presence_light_group_timings.json', label: 'Presence delays' },
  { view: 'room-modes', menu: 'room-modes', store: 'room_modes.json', label: 'Room modes' },
  { view: 'scenes', menu: 'scenes', store: 'light_schedules.json', label: 'Light automations' },
  { view: 'alarm', menu: 'alarm', store: 'fridge_alarm_settings.json', label: 'Device alarms' },
  { view: 'rooms', menu: 'rooms', store: 'room_aliases.json', label: 'Room names' },
  { view: 'homekit', menu: 'voice-control', store: 'homekit_light_groups.json', label: 'HomeKit lights' },
];

(async () => {
  const html = fs.readFileSync('future_homes_tech_app/web/index.html', 'utf8');
  const browser = await chromium.launch({ headless: true });
  try {
    for (const width of [1280, 390]) {
      const page = await browser.newPage({ viewport: { width, height: 900 } });
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      const reverts = [];
      const historyReads = [];
      const dataReads = [];
      let failNextRevert = false;
      const histories = new Map(PAGES.map(({ view, store, label }) => [view, [{
        timestamp: '20261003T140200000000Z', saved_at: new Date(Date.now() - 3 * 60000).toISOString(),
        store, label, summary: 'Changed Kitchen',
      }]]));
      histories.set('alarm', []);
      await page.route('**/*', route => {
        const request = route.request();
        const url = new URL(request.url());
        if (url.pathname === '/') return route.fulfill({ contentType: 'text/html', body: html });
        if (/\.(png|webp|jpg)$/.test(url.pathname)) return route.fulfill({ status: 404, body: '' });
        if (url.pathname === '/api/settings/history') {
          const view = url.searchParams.get('page');
          historyReads.push(view);
          return route.fulfill({ json: { ok: true, page: view, entries: histories.get(view) || [] } });
        }
        if (url.pathname === '/api/settings/revert') {
          const body = request.postDataJSON();
          reverts.push(body);
          if (failNextRevert) {
            failNextRevert = false;
            return route.fulfill({ status: 502, json: { ok: false, saved: true, activated: false, error: 'Home Assistant is restarting.' } });
          }
          const entry = { ...histories.get(body.page)[0], timestamp: '20261003T141500000000Z', saved_at: new Date().toISOString(), summary: 'Changed Kitchen' };
          histories.set(body.page, [entry]);
          return route.fulfill({ json: { ok: true, saved: true, restored: true, activated: true, entries: [entry] } });
        }
        if (url.pathname.startsWith('/api/')) dataReads.push(url.pathname);
        return route.fulfill({ json: { ok: true, entities: [], floors: [], rooms: [], settings: {}, scenes: [], catalog: {}, current_modes: {}, house_settings: {}, buttons: [], control_settings: {}, aliases: {}, entries: [] } });
      });
      await page.goto('http://fht.test/');
      await page.waitForTimeout(800);

      for (const { view, menu, store, label } of PAGES) {
        if (width < 800) await page.locator('#mobile-nav-toggle').click();
        if ((await page.locator('#settings-toggle').getAttribute('aria-expanded')) !== 'true') await page.locator('#settings-toggle').click();
        await page.locator(`[data-view="${menu}"]`).click();
        const control = page.locator(`[data-settings-undo="${view}"]`);
        if (view === 'alarm') {
          // No history for this page: the control never appears.
          await page.waitForFunction(() => document.body.classList.contains('alarm-view-active'));
          await page.waitForTimeout(300);
          assert.equal(await control.evaluate(node => node.hidden), true, 'Undo stays hidden without history');
          assert.equal(await control.isVisible(), false);
          continue;
        }
        await page.locator(`[data-settings-undo="${view}"]:not([hidden])`).waitFor();
        const button = control.locator('button');
        assert.equal(await button.innerText(), 'Undo last change · 3 min ago', `${view}: time of the last change`);
        const box = await button.boundingBox();
        assert.ok(box && box.x >= 0 && box.x + box.width <= width + 1 && box.y >= 0, `${view}: undo button inside the ${width}px viewport (${JSON.stringify(box)})`);
        assert.ok(box.height >= 24, `${view}: undo button is tappable`);
        const overlapped = await button.evaluate(node => {
          const rect = node.getBoundingClientRect();
          const top = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
          return top !== node && !node.contains(top) ? (top?.id || top?.className || top?.tagName) : '';
        });
        assert.equal(overlapped, '', `${view}: nothing covers the undo button`);
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true, `${view}: no horizontal overflow`);
        if (process.env.FHT_SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.FHT_SCREENSHOT_DIR}/undo-${view}-${width}.png` });

        if (view !== 'switches' && view !== 'homekit') continue;

        // Confirming the pop-up restores the version the history reported, then reloads the page.
        const dialog = page.locator('#settings-undo-dialog');
        const readsBefore = dataReads.length;
        await button.click();
        await page.waitForSelector('#settings-undo-dialog[open]');
        const text = await page.locator('#settings-undo-dialog-text').innerText();
        assert.ok(text.includes(`This puts ${label} back to how it was before the change saved 3 min ago`), `${view}: dialog text (${text})`);
        assert.equal(await page.locator('#settings-undo-dialog-note').innerText(), 'That change: Changed Kitchen.');
        if (process.env.FHT_SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.FHT_SCREENSHOT_DIR}/undo-dialog-${view}-${width}.png` });
        if (view === 'switches') {
          // Closing keeps the current settings.
          await page.locator('#settings-undo-dialog-close').click();
          await page.waitForFunction(() => !document.getElementById('settings-undo-dialog').open);
          assert.equal(reverts.length, 0, 'Closing the pop-up does not undo anything');
          // A failed activation keeps the pop-up open with the error, but still reloads the page.
          failNextRevert = true;
          await button.click();
          await page.waitForSelector('#settings-undo-dialog[open]');
          await page.locator('#settings-undo-confirm').click();
          await page.waitForFunction(() => !document.getElementById('settings-undo-dialog-error').hidden);
          assert.equal(await page.locator('#settings-undo-dialog-error').innerText(), 'Saved, but Home Assistant activation failed: Home Assistant is restarting.');
          assert.equal(await dialog.evaluate(node => node.open), true);
          await page.locator('#settings-undo-dialog-close').click();
          await page.waitForFunction(() => !document.getElementById('settings-undo-dialog').open);
          await button.click();
          await page.waitForSelector('#settings-undo-dialog[open]');
        }
        await page.locator('#settings-undo-confirm').click();
        await page.waitForFunction(() => !document.getElementById('settings-undo-dialog').open);
        assert.deepEqual(reverts.at(-1), { page: view, store, timestamp: '20261003T140200000000Z' });
        await page.waitForFunction(view => document.querySelector(`[data-settings-undo="${view}"] button`)?.innerText === 'Undo last change · just now', view);
        assert.ok(dataReads.length > readsBefore, `${view}: the page loaded its data again after the undo`);
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true);
      }
      assert.ok(historyReads.filter(view => view === 'switches').length >= 3, 'History is read when the page opens and again before each undo');
      assert.deepEqual(errors, []);
      console.log(`Settings undo passed at ${width}px`);
      await page.close();
    }
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
