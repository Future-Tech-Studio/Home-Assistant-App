const fs = require('node:fs');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.FHT_PLAYWRIGHT || 'playwright');

// Each settings page has a Revert button in its header. It opens a card listing
// that page's recent saves only; each row can be reverted, and a revert can be
// reverted again. Home Configurator no longer has its own Revert Changes card.
(async () => {
  const html = fs.readFileSync('future_homes_tech_app/web/index.html', 'utf8');
  const browser = await chromium.launch({ headless: true });
  const settingsPages = ['doors', 'switches', 'buttons', 'presence', 'room-modes', 'scenes', 'alarm', 'rooms'];
  try {
    for (const width of [1280, 700, 390]) {
      const page = await browser.newPage({ viewport: { width, height: 900 } });
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      const reverts = [];
      const historyPages = [];
      let failNextRevert = false;
      const ago = minutes => new Date(Date.now() - minutes * 60000).toISOString();
      const history = {
        switches: [
          { timestamp: '20261003T140200000000Z', saved_at: ago(3), store: 'switch_control_settings.json', label: 'Switch, door and button actions', summary: 'Changed Kitchen' },
          { timestamp: '20261003T130000000000Z', saved_at: ago(65), store: 'switch_control_settings.json', label: 'Switch, door and button actions', summary: '' },
        ],
        // Twelve saves: five per page, so three pages.
        presence: Array.from({ length: 12 }, (_, n) => ({ timestamp: `20261003T1${String(59 - n).padStart(2, '0')}00000000Z`, saved_at: ago(10 + n), store: 'presence_light_group_timings.json', label: 'Presence delays', summary: `Kitchen delay ${n + 1} minutes, Hallway delay ${n + 2} minutes, Office delay ${n + 3} minutes` })),
        rooms: [
          { timestamp: '20261002T090000000000Z', saved_at: ago(26 * 60), store: 'room_aliases.json', label: 'Room names', summary: 'Added Bedroom 6' },
        ],
      };
      await page.route('**/*', route => {
        const request = route.request();
        const url = new URL(request.url());
        if (url.pathname === '/') return route.fulfill({ contentType: 'text/html', body: html });
        if (/\.(png|webp|jpg)$/.test(url.pathname)) return route.fulfill({ status: 404, body: '' });
        if (url.pathname === '/api/app-info') return route.fulfill({ json: { ok: true, installed_version: '0.8.1', update_available: true, beta_mode: false, site_profile: {} } });
        if (url.pathname === '/api/settings/history') {
          const name = url.searchParams.get('page');
          historyPages.push(name);
          return route.fulfill({ json: { ok: true, entries: history[name] || [] } });
        }
        if (url.pathname === '/api/settings/revert') {
          const body = request.postDataJSON();
          reverts.push(body);
          if (failNextRevert) {
            failNextRevert = false;
            return route.fulfill({ status: 502, json: { ok: false, saved: true, activated: false, error: 'Home Assistant is restarting.' } });
          }
          // The revert is itself a saved change, listed first.
          const entries = history[body.page];
          entries.unshift({ ...entries.find(entry => entry.timestamp === body.timestamp), timestamp: '20261003T141500000000Z', saved_at: new Date().toISOString() });
          return route.fulfill({ json: { ok: true, saved: true, restored: true, activated: true, entries: [] } });
        }
        return route.fulfill({ json: { ok: true, entities: [], floors: [], rooms: [], settings: {}, scenes: [], catalog: {}, current_modes: {}, house_settings: {}, buttons: [], control_settings: {}, aliases: {}, entries: [] } });
      });
      await page.goto('http://fht.test/');
      await page.waitForTimeout(800);
      const showView = view => page.evaluate(name => document.querySelector(`[data-view="${name}"]`).click(), view);
      const revertButton = page.locator('#page-revert');
      const boxes = () => page.evaluate(() => ['#page-revert', '#open-updates', '#update-app'].map(selector => document.querySelector(selector).getBoundingClientRect().toJSON()));

      // The button shows in the header of every settings page, between the update button and Updates.
      for (const view of settingsPages) {
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
      for (const view of ['home', 'lighting', 'security', 'environment', 'unifi']) {
        await showView(view);
        await page.waitForTimeout(150);
        assert.equal(await revertButton.isVisible(), false, `No Revert on ${view}, which saves no settings`);
      }

      // Home Configurator keeps no Revert Changes card of its own.
      await showView('rooms');
      await page.waitForTimeout(300);
      assert.equal(await page.locator('#room-configurator-list .revert-changes-list, #room-configurator-list .revert-changes-title').count(), 0);

      // An empty page says so.
      await showView('alarm');
      await revertButton.click();
      await page.waitForSelector('#page-revert-dialog[open]');
      assert.equal(await page.locator('#page-revert-dialog-title').innerText(), 'Revert Changes · Alarm');
      await page.waitForFunction(() => document.querySelector('#revert-changes-list').innerText.includes('No saved changes on this page yet.'));
      assert.equal(historyPages.at(-1), 'alarm', 'The card asks for this page only');
      await page.locator('#page-revert-dialog-close').click();
      await page.waitForFunction(() => !document.getElementById('page-revert-dialog').open);

      // Switches lists only its own changes.
      await showView('switches');
      await revertButton.click();
      await page.waitForSelector('#page-revert-dialog[open]');
      const list = page.locator('#revert-changes-list');
      await list.locator('.revert-change-row').first().waitFor();
      assert.equal(historyPages.at(-1), 'switches');
      assert.equal(await page.locator('#page-revert-dialog-title').innerText(), 'Revert Changes · Switches');
      assert.equal(await list.locator('.revert-change-row').count(), 2);
      const firstRow = list.locator('.revert-change-row').first();
      assert.ok((await firstRow.innerText()).includes('Switch, door and button actions'));
      assert.ok((await firstRow.innerText()).includes('3 min ago'));
      assert.ok((await firstRow.innerText()).includes('Changed Kitchen'));
      assert.equal(await page.locator('#revert-pager').isVisible(), false, 'No pages for two changes');
      assert.ok(!(await list.innerText()).includes('Room names'), 'Other pages\' changes are not listed');
      assert.ok((await list.locator('.revert-change-row').nth(1).innerText()).includes('1 hour ago'));
      const button = firstRow.locator('.revert-change-button');
      const box = await button.boundingBox();
      assert.ok(box && box.x >= 0 && box.x + box.width <= width + 1 && box.height >= 24, `Row Revert button inside the ${width}px viewport`);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true, 'No horizontal overflow');
      if (process.env.FHT_SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.FHT_SCREENSHOT_DIR}/page-revert-${width}.png` });

      // Closing the confirmation keeps the current settings.
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
      // Confirming reverts the row's version; the card then shows the revert itself, newest first.
      await button.click();
      await page.waitForSelector('#settings-undo-dialog[open]');
      await page.locator('#settings-undo-confirm').click();
      await page.waitForFunction(() => !document.getElementById('settings-undo-dialog').open);
      assert.deepEqual(reverts.at(-1), { page: 'switches', store: 'switch_control_settings.json', timestamp: '20261003T140200000000Z' });
      await page.waitForFunction(() => document.querySelectorAll('#revert-changes-list .revert-change-row').length === 3);
      assert.ok((await list.locator('.revert-change-row').first().innerText()).includes('just now'), 'The revert can be reverted again');
      assert.ok(await page.locator('#page-revert-dialog').evaluate(dialog => dialog.open), 'The card stays open for another revert');
      await page.keyboard.press('Escape');
      await page.waitForFunction(() => !document.getElementById('page-revert-dialog').open);

      // Presence has twelve saves: five per page with first, previous, next and last.
      await showView('presence');
      await revertButton.click();
      await page.waitForSelector('#page-revert-dialog[open]');
      await list.locator('.revert-change-row').first().waitFor();
      const pager = page.locator('#revert-pager');
      const current = page.locator('#revert-pager-current');
      const pagerButton = name => pager.locator(`[data-revert-page="${name}"]`);
      const rowTexts = () => list.locator('.revert-change-row').allInnerTexts();
      assert.equal(await list.locator('.revert-change-row').count(), 5);
      assert.ok(await pager.isVisible());
      assert.deepEqual(await pager.locator('button').allInnerTexts(), ['«', '‹', '›', '»']);
      assert.equal(await current.innerText(), 'Page 1 of 3');
      assert.equal(await pagerButton('first').isDisabled(), true);
      assert.equal(await pagerButton('prev').isDisabled(), true);
      assert.ok((await rowTexts())[0].includes('Kitchen delay 1 minutes'));
      if (width > 820) {
        // Wide rows: a change with a long summary takes two lines, not five.
        const rowHeight = await list.locator('.revert-change-row').first().evaluate(row => row.getBoundingClientRect().height);
        assert.ok(rowHeight < 64, `Row is ${rowHeight}px tall at ${width}px`);
        const dialogWidth = await page.locator('#page-revert-dialog').evaluate(dialog => dialog.getBoundingClientRect().width);
        assert.ok(dialogWidth >= 700, `The card is ${dialogWidth}px wide at ${width}px`);
      }
      if (process.env.FHT_SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.FHT_SCREENSHOT_DIR}/page-revert-pages-${width}.png` });
      await pagerButton('next').click();
      assert.equal(await current.innerText(), 'Page 2 of 3');
      assert.ok((await rowTexts())[0].includes('Kitchen delay 6 minutes'));
      await pagerButton('last').click();
      assert.equal(await current.innerText(), 'Page 3 of 3');
      assert.equal(await list.locator('.revert-change-row').count(), 2);
      assert.equal(await pagerButton('next').isDisabled(), true);
      assert.equal(await pagerButton('last').isDisabled(), true);
      await pagerButton('prev').click();
      assert.equal(await current.innerText(), 'Page 2 of 3');
      await pagerButton('first').click();
      assert.equal(await current.innerText(), 'Page 1 of 3');
      // A row on a later page reverts that row's own save.
      await pagerButton('last').click();
      await list.locator('.revert-change-row').last().locator('.revert-change-button').click();
      await page.waitForSelector('#settings-undo-dialog[open]');
      await page.locator('#settings-undo-confirm').click();
      await page.waitForFunction(() => !document.getElementById('settings-undo-dialog').open);
      assert.equal(reverts.at(-1).timestamp, history.presence.at(-1).timestamp);
      await page.waitForFunction(() => document.querySelector('#revert-pager-current').textContent === 'Page 1 of 3');
      assert.ok((await rowTexts())[0].includes('just now'), 'After a revert the card shows the newest change first');
      await page.keyboard.press('Escape');
      assert.deepEqual(errors, []);
      console.log(`Page Revert button passed at ${width}px`);
      await page.close();
    }
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
