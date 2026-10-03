const fs = require('node:fs');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.FHT_PLAYWRIGHT || 'playwright');

// Settings → Future Tech Portal: paste a token, see the connection, choose what reports.
(async () => {
  const html = fs.readFileSync('future_homes_tech_app/web/index.html', 'utf8');
  const browser = await chromium.launch({ headless: true });
  const token = 'fts_browserTest12345';
  try {
    for (const width of [1280, 390]) {
      const page = await browser.newPage({ viewport: { width, height: 900 } });
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      const posts = [];
      const choices = ['unifi', 'unifiprotect', 'zha', 'zwave_js', 'matter', 'mqtt', 'esphome', 'hue']
        .map(domain => ({ domain, devices: domain === 'zha' ? 34 : domain === 'hue' ? 1 : 0, default: domain !== 'hue' }));
      let state = {
        ok: true, token_saved: false, enabled: true, package_installed: false,
        integrations: ['unifi', 'unifiprotect', 'zha', 'zwave_js', 'matter', 'mqtt', 'esphome'],
        integration_choices: choices, endpoint: 'https://futuretech.studio/api/beta/ingest',
        include_label: 'future_tech_report', exclude_label: 'future_tech_exclude',
        status: { connection: 'not_set_up', http_status: null, last_result: '', last_attempt: '', last_success: '', last_inventory: '', device_count: null },
      };
      await page.route('**/*', route => {
        const request = route.request();
        const url = new URL(request.url());
        if (url.pathname === '/') return route.fulfill({ contentType: 'text/html', body: html });
        if (/\.(png|webp|jpg)$/.test(url.pathname)) return route.fulfill({ status: 404, body: '' });
        if (url.pathname === '/api/future-tech-portal') {
          if (request.method() === 'POST') {
            const body = request.postDataJSON();
            posts.push(body);
            if (body.action === 'save_token' && body.token === 'nope') {
              return route.fulfill({ status: 400, json: { ok: false, saved: false, error: 'Paste the token exactly as the portal shows it; it starts with fts_.' } });
            }
            if (body.action === 'save_token') {
              const now = new Date().toISOString();
              state = { ...state, token_saved: true, package_installed: true,
                status: { connection: 'connected', http_status: 200, last_result: '200', last_kind: 'inventory', last_attempt: now, last_success: now, last_inventory: now, device_count: 41 } };
            }
            if (body.action === 'settings') state = { ...state, ...('integrations' in body ? { integrations: body.integrations } : {}), ...('enabled' in body ? { enabled: body.enabled } : {}) };
            if (body.action === 'remove_token') {
              state = { ...state, token_saved: false, package_installed: false, status: { ...state.status, connection: 'not_set_up' } };
            }
            return route.fulfill({ json: { ...state, saved: true, activated: true } });
          }
          return route.fulfill({ json: state });
        }
        return route.fulfill({ json: { ok: true, entities: [], floors: [], rooms: [], settings: {}, entries: [] } });
      });
      await page.goto('http://fht.test/');
      await page.waitForTimeout(800);
      if (width < 800) await page.locator('#mobile-nav-toggle').click();
      await page.locator('#settings-toggle').click();
      const menu = await page.locator('#settings-submenu [data-view]').evaluateAll(items => items.map(item => item.textContent.trim()));
      assert.equal(menu[menu.indexOf('Unifi') + 1], 'Future Tech Portal', 'The portal page sits after Unifi');
      await page.locator('[data-view="future-tech-portal"]').click();
      const view = page.locator('#view-future-tech-portal');
      await page.waitForFunction(() => document.querySelector('#portal-connection').textContent === 'Not set up');
      assert.equal(await page.locator('#settings-submenu').isHidden(), false, 'The Settings menu stays open on this page');
      assert.equal(await page.locator('#portal-send-inventory').isDisabled(), true, 'Nothing to send before a token');
      assert.equal(await page.locator('#portal-token-remove').isHidden(), true);
      assert.equal(await page.locator('#portal-token-input').getAttribute('type'), 'password', 'The token is masked while typed');
      assert.deepEqual(
        await page.locator('#portal-integrations .portal-integration').allTextContents(),
        ['UniFi Network', 'UniFi Protect', 'Zigbee (ZHA) 34 devices', 'Z-Wave', 'Matter', 'MQTT', 'ESPHome', 'hue 1 device'],
      );
      assert.equal(await page.locator('#portal-integrations input:checked').count(), 7, 'The seven default integrations are on');

      // A bad token shows the server's message and is kept in the box to fix.
      await page.locator('#portal-token-input').fill('nope');
      await page.locator('#portal-token-save').click();
      await page.waitForFunction(() => document.querySelector('#portal-state').classList.contains('error'));
      assert.match(await page.locator('#portal-state').textContent(), /starts with fts_/);

      await page.locator('#portal-token-input').fill(token);
      await page.locator('#portal-token-save').click();
      await page.waitForFunction(() => document.querySelector('#portal-connection').textContent === 'Connected');
      assert.deepEqual(posts.at(-1), { action: 'save_token', token });
      assert.equal(await page.locator('#portal-token-input').inputValue(), '', 'The token is cleared from the page after saving');
      assert.equal(await page.locator('#portal-connection').evaluate(node => getComputedStyle(node).color), 'rgb(85, 215, 151)', 'Connected is green');
      assert.equal(await page.locator('#portal-send-inventory').isDisabled(), false);
      assert.equal(await page.locator('#portal-token-remove').isHidden(), false);
      assert.equal(await page.locator('#portal-token-save').textContent(), 'Replace token');
      const details = await page.locator('#portal-status-details').innerText();
      assert.match(details, /Devices reported\s+41/i);
      assert.match(details, /inventory · HTTP 200/);
      assert.ok(!(await view.innerHTML()).includes(token), 'The token never appears in the page');

      await page.locator('#portal-integrations input[value="hue"]').check();
      await page.waitForFunction(() => document.querySelectorAll('#portal-integrations input:checked').length === 8 && !document.querySelector('#portal-state').textContent);
      assert.deepEqual(posts.at(-1), { action: 'settings', integrations: ['unifi', 'unifiprotect', 'zha', 'zwave_js', 'matter', 'mqtt', 'esphome', 'hue'] });
      await page.locator('#portal-enabled').uncheck();
      await page.waitForFunction(() => document.querySelector('#portal-enabled').checked === false && !document.querySelector('#portal-state').textContent);
      assert.deepEqual(posts.at(-1), { action: 'settings', enabled: false });

      await page.locator('#portal-send-inventory').click();
      await page.waitForFunction(() => document.querySelector('#portal-state').textContent.startsWith('Inventory requested'));
      assert.deepEqual(posts.at(-1), { action: 'send_inventory' });

      // A rejected token turns the card red and explains the pause.
      state = { ...state, status: { ...state.status, connection: 'rejected', http_status: 401, last_result: '401' } };
      await page.locator('[data-page-refresh="future-tech-portal"]').click();
      await page.waitForFunction(() => document.querySelector('#portal-connection').textContent === 'Token rejected');
      assert.equal(await page.locator('#portal-connection').evaluate(node => getComputedStyle(node).color), 'rgb(255, 123, 136)', 'A rejected token is red');
      assert.match(await page.locator('#portal-connection-detail').textContent(), /paused until you save a new token/);

      page.once('dialog', dialog => dialog.accept());
      await page.locator('#portal-token-remove').click();
      await page.waitForFunction(() => document.querySelector('#portal-connection').textContent === 'Not set up');
      assert.deepEqual(posts.at(-1), { action: 'remove_token' });

      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      assert.ok(overflow <= 1, `No sideways scrolling at ${width}px (overflow ${overflow})`);
      assert.deepEqual(errors, []);
      await page.close();
    }
    console.log('Future Tech Portal browser checks passed');
  } finally {
    await browser.close();
  }
})().catch(error => {
  console.error(error);
  process.exit(1);
});
