const fs = require('node:fs');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.FHT_PLAYWRIGHT || 'playwright');

// One Revert button sits in the header of every page, like Updates and Exit.
// It opens a card listing the recent saves from every settings page, five at a
// time; each row can be reverted, and a revert can be reverted again.
(async () => {
  const html = fs.readFileSync('future_homes_tech_app/web/index.html', 'utf8');
  const browser = await chromium.launch({ headless: true });
  try {
    for (const width of [1280, 700, 390]) {
      const page = await browser.newPage({ viewport: { width, height: 900 } });
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      const reverts = [];
      const historyQueries = [];
      let failNextRevert = false;
      const ago = minutes => new Date(Date.now() - minutes * 60000).toISOString();
      // Twelve saves from three pages, newest first: five per page, so three pages.
      let entries = [];
      const resetHistory = () => {
        entries = [
          { timestamp: '20261003T140200000000Z', saved_at: ago(3), page: 'switches', page_label: 'Switches, Doors and Buttons', store: 'switch_control_settings.json', label: 'Switch, door and button actions', summary: 'Kitchen Switch › Action changed from Off to Toggle; Hall Switch turned on', changes: ['Kitchen Switch › Action changed from Off to Toggle', 'Hall Switch turned on'] },
          ...Array.from({ length: 10 }, (_, n) => ({ timestamp: `20261003T13${String(59 - n).padStart(2, '0')}00000000Z`, saved_at: ago(10 + n), page: 'presence', page_label: 'Presence', store: 'presence_light_group_timings.json', label: 'Presence delays', summary: `Kitchen delay ${n + 1} minutes, Hallway delay ${n + 2} minutes, Office delay ${n + 3} minutes` })),
          { timestamp: '20261002T090000000000Z', saved_at: ago(26 * 60), page: 'rooms', page_label: 'Home Configurator', store: 'room_aliases.json', label: 'Room names', summary: 'Added Bedroom 6' },
        ];
      };
      await page.route('**/*', route => {
        const request = route.request();
        const url = new URL(request.url());
        if (url.pathname === '/') return route.fulfill({ contentType: 'text/html', body: html });
        if (/\.(png|webp|jpg)$/.test(url.pathname)) return route.fulfill({ status: 404, body: '' });
        if (url.pathname === '/api/app-info') return route.fulfill({ json: { ok: true, installed_version: '0.8.1', update_available: true, beta_mode: false, site_profile: {} } });
        if (url.pathname === '/api/settings/history') {
          historyQueries.push(url.search);
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
          entries = [{ ...entries.find(entry => entry.timestamp === body.timestamp), timestamp: '20261003T141500000000Z', saved_at: new Date().toISOString() }, ...entries];
          return route.fulfill({ json: { ok: true, saved: true, restored: true, activated: true, entries: [] } });
        }
        return route.fulfill({ json: { ok: true, entities: [], floors: [], rooms: [], settings: {}, scenes: [], catalog: {}, current_modes: {}, house_settings: {}, buttons: [], control_settings: {}, aliases: {}, entries: [] } });
      });
      await page.goto('http://fht.test/');
      await page.waitForTimeout(800);
      const showView = view => page.evaluate(name => document.querySelector(`[data-view="${name}"]`).click(), view);
      const revertButton = page.locator('#page-revert');
      const boxes = () => page.evaluate(() => ['#page-revert', '#open-updates', '#update-app'].map(selector => document.querySelector(selector).getBoundingClientRect().toJSON()));

      // The button shows in the header of every menu page, between the update button and Updates.
      const views = await page.evaluate(() => [...new Set([...document.querySelectorAll('[data-view]')].map(item => item.dataset.view))]);
      assert.ok(views.length >= 12, `Every menu page is checked (${views.join(', ')})`);
      for (const view of views) {
        await showView(view);
        await page.waitForTimeout(150);
        assert.ok(await revertButton.isVisible(), `Revert shows on ${view} at ${width}px`);
        const [revert, updates, update] = await boxes();
        assert.ok(revert.right <= updates.left + 1 && Math.abs(revert.top - updates.top) <= 1, `Revert sits beside Updates on ${view} at ${width}px`);
        assert.ok(update.right <= revert.left + 1, `The update button sits left of Revert on ${view} at ${width}px`);
        assert.ok(revert.left >= 0, `Revert inside the ${width}px viewport on ${view}`);
        // On a computer the button says Revert; on a phone it is the icon alone.
        assert.equal((await revertButton.innerText()).trim(), width > 820 ? 'Revert' : '', `Revert label on ${view} at ${width}px`);
      }

      // Home Configurator keeps no Revert Changes card of its own.
      await showView('rooms');
      await page.waitForTimeout(300);
      assert.equal(await page.locator('#room-configurator-list .revert-changes-list, #room-configurator-list .revert-changes-title').count(), 0);

      // With nothing saved the card says so.
      await showView('home');
      await revertButton.click();
      await page.waitForSelector('#page-revert-dialog[open]');
      assert.equal(await page.locator('#page-revert-dialog-title').innerText(), 'Revert Changes');
      await page.waitForFunction(() => document.querySelector('#revert-changes-list').innerText.includes('No saved changes yet.'));
      assert.equal(await page.locator('#revert-pager').isVisible(), false);
      await page.locator('#page-revert-dialog-close').click();
      await page.waitForFunction(() => !document.getElementById('page-revert-dialog').open);

      // What the App removed on its own is listed for information, with no Revert button.
      entries = [{ timestamp: '20261002T100000000000Z', saved_at: ago(25 * 60), page: 'cleanup', page_label: 'App', store: '', label: 'Removed automatically', summary: 'Old flag', changes: ['Old flag', 'automation.old'], revertible: false }];
      await revertButton.click();
      await page.waitForSelector('#page-revert-dialog[open]');
      const cleanupRow = page.locator('#revert-changes-list .revert-change-row').first();
      await cleanupRow.waitFor();
      assert.ok((await cleanupRow.innerText()).includes('App · Removed automatically'));
      assert.deepEqual(await cleanupRow.locator('.revert-change-summary li').allInnerTexts(), ['Old flag', 'automation.old']);
      assert.equal(await cleanupRow.locator('.revert-change-button').count(), 0, 'Automatic removals cannot be reverted');
      await page.locator('#page-revert-dialog-close').click();
      await page.waitForFunction(() => !document.getElementById('page-revert-dialog').open);

      // From any page the card lists every page's changes, with the page they were made on.
      resetHistory();
      await showView('lighting');
      await revertButton.click();
      await page.waitForSelector('#page-revert-dialog[open]');
      const list = page.locator('#revert-changes-list');
      await list.locator('.revert-change-row').first().waitFor();
      assert.equal(historyQueries.at(-1), '', 'The card asks for every page at once');
      const rows = list.locator('.revert-change-row');
      const rowTexts = () => rows.allInnerTexts();
      assert.equal(await rows.count(), 5);
      const firstRow = rows.first();
      assert.ok((await firstRow.innerText()).includes('Switches, Doors and Buttons · Switch, door and button actions'));
      assert.ok((await firstRow.innerText()).includes('3 min ago'));
      // Each changed setting is its own line, with its old and new value.
      assert.deepEqual(await firstRow.locator('.revert-change-summary li').allInnerTexts(), ['Kitchen Switch › Action changed from Off to Toggle', 'Hall Switch turned on']);
      assert.ok((await rows.nth(1).innerText()).includes('Presence · Presence delays'));
      const button = firstRow.locator('.revert-change-button');
      const box = await button.boundingBox();
      assert.ok(box && box.x >= 0 && box.x + box.width <= width + 1 && box.height >= 24, `Row Revert button inside the ${width}px viewport`);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true, 'No horizontal overflow');
      if (width > 820) {
        // Wide rows: a change with a long summary takes two lines, not five.
        const rowHeight = await rows.nth(1).evaluate(row => row.getBoundingClientRect().height);
        assert.ok(rowHeight < 64, `Row is ${rowHeight}px tall at ${width}px`);
        const dialogWidth = await page.locator('#page-revert-dialog').evaluate(dialog => dialog.getBoundingClientRect().width);
        assert.ok(dialogWidth >= 700, `The card is ${dialogWidth}px wide at ${width}px`);
      }
      if (process.env.FHT_SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.FHT_SCREENSHOT_DIR}/page-revert-${width}.png` });

      // Five per page with first, previous, page number, next and last.
      const pager = page.locator('#revert-pager');
      const current = page.locator('#revert-pager-current');
      const pagerButton = name => pager.locator(`[data-revert-page="${name}"]`);
      assert.ok(await pager.isVisible());
      assert.deepEqual(await pager.locator('button').allInnerTexts(), ['«', '‹', '›', '»']);
      assert.equal(await current.innerText(), 'Page 1 of 3');
      assert.equal(await pagerButton('first').isDisabled(), true);
      assert.equal(await pagerButton('prev').isDisabled(), true);
      await pagerButton('next').click();
      assert.equal(await current.innerText(), 'Page 2 of 3');
      assert.ok((await rowTexts())[0].includes('Kitchen delay 5 minutes'));
      await pagerButton('last').click();
      assert.equal(await current.innerText(), 'Page 3 of 3');
      assert.equal(await rows.count(), 2);
      assert.ok((await rowTexts())[1].includes('Home Configurator · Room names'));
      assert.equal(await pagerButton('next').isDisabled(), true);
      assert.equal(await pagerButton('last').isDisabled(), true);
      await pagerButton('prev').click();
      assert.equal(await current.innerText(), 'Page 2 of 3');
      await pagerButton('first').click();
      assert.equal(await current.innerText(), 'Page 1 of 3');

      // Closing the confirmation keeps the current settings.
      await button.click();
      await page.waitForSelector('#settings-undo-dialog[open]');
      const text = await page.locator('#settings-undo-dialog-text').innerText();
      assert.ok(text.includes('This puts Switch, door and button actions back to how it was before the change saved 3 min ago'), text);
      assert.equal(await page.locator('#settings-undo-dialog-note').innerText(), 'That change: Kitchen Switch › Action changed from Off to Toggle; Hall Switch turned on.');
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

      // A row on a later page reverts that row's own save, on the page it was made on;
      // the card then returns to page 1, where the revert is the newest change.
      await pagerButton('last').click();
      await rows.last().locator('.revert-change-button').click();
      await page.waitForSelector('#settings-undo-dialog[open]');
      await page.locator('#settings-undo-confirm').click();
      await page.waitForFunction(() => !document.getElementById('settings-undo-dialog').open);
      assert.deepEqual(reverts.at(-1), { page: 'rooms', store: 'room_aliases.json', timestamp: '20261002T090000000000Z' });
      await page.waitForFunction(() => document.querySelector('#revert-pager-current').textContent === 'Page 1 of 3');
      assert.ok((await rowTexts())[0].includes('just now'), 'The revert can be reverted again');
      assert.ok(await page.locator('#page-revert-dialog').evaluate(dialog => dialog.open), 'The card stays open for another revert');
      await page.keyboard.press('Escape');
      await page.waitForFunction(() => !document.getElementById('page-revert-dialog').open);
      assert.deepEqual(errors, []);
      console.log(`Revert button passed at ${width}px`);
      await page.close();
    }
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
