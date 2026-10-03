const fs = require('node:fs');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.FHT_PLAYWRIGHT || 'playwright');

(async () => {
  const html = fs.readFileSync('future_homes_tech_app/web/index.html', 'utf8');
  const browser = await chromium.launch({ headless: true });
  try {
    for (const width of [1440, 390]) {
      const page = await browser.newPage({ viewport: { width, height: 1000 } });
      const saves = [];
      await page.route('**/*', route => {
        const pathname = new URL(route.request().url()).pathname;
        if (pathname === '/') return route.fulfill({ contentType: 'text/html', body: html });
        const payload = { ok: true, entities: [], settings: {}, rooms: [], floors: [], changed: false, room_count: 2 };
        if (pathname === '/api/buttons') Object.assign(payload, { buttons: [{ device_id: 'test_button', area: 'Kitchen', friendly_name: 'Kitchen Button', triggers: [{ domain: 'mqtt', type: 'single_press', subtype: '1' }] }], control_settings: {} });
        if (pathname === '/api/home-configurator/room') Object.assign(payload, { room: 'Kitchen', entities: [], control_settings: {} });
        if (pathname === '/api/home-configurator/catalog') payload.action_catalog = { light_groups: [{ entity_id: 'light.kitchen', friendly_name: 'Kitchen All Lights', area: 'Kitchen' }] };
        if (pathname === '/api/switch-light-groups' && route.request().method() === 'POST') saves.push(route.request().postDataJSON());
        if (pathname === '/api/home-configurator/index') payload.floors = [
          { name: 'First Floor', rooms: [{ name: 'Kitchen' }] },
          { name: 'Whole Home', rooms: [] },
          { name: 'Second Floor', rooms: [{ name: 'Bedroom' }] },
          { name: 'Unassigned', rooms: [] },
        ];
        return route.fulfill({ contentType: 'application/json', body: JSON.stringify(payload) });
      });
      await page.goto('http://fht.test/');
      await page.waitForSelector('.page-actions-primary #home-configurator-header', { state: 'attached' });
      await page.locator('[data-view="rooms"]').evaluate(button => button.click());
      await page.waitForFunction(() => !document.querySelector('#home-floor-picker').disabled);
      assert.equal(await page.locator('#home-floor-picker').inputValue(), 'Whole Home');
      assert.deepEqual(await page.locator('#home-floor-picker option').allTextContents(), ['Whole Home', 'First Floor', 'Second Floor']);
      assert.equal(await page.locator('.page-actions-primary #home-configurator-header').count(), 1);
      await page.selectOption('#home-floor-picker', 'First Floor');
      await page.waitForFunction(() => document.querySelectorAll('.home-configurator-floor-card[open]').length === 1);
      assert.equal(await page.locator('.home-configurator-floor-card[open]').getAttribute('data-floor'), 'First Floor');
      assert.equal(await page.locator('.home-configurator-floor-card[open] h2').textContent(), 'Kitchen');
      await page.locator('[data-view="alarm"]').evaluate(button => button.click());
      assert.equal(await page.locator('#home-configurator-header').isVisible(), false);
      assert.equal(await page.locator('[data-alarm-section]').count(), 0);
      assert.equal(await page.locator('#alarm-device-card').evaluate(node => node.tagName), 'SECTION');
      assert.equal(await page.locator('#alarm-device-card').isVisible(), true);
      await page.locator('[data-view="buttons"]').evaluate(button => button.click());
      await page.locator('[data-button-area="Kitchen"] > summary').click();
      await page.waitForSelector('#buttons-list .button-control-title');
      assert.equal(await page.locator('#buttons-list .button-control-title').textContent(), 'Button 1');
      await page.locator('#buttons-list .button-group-select').evaluate(select => {
        for (const option of select.options) option.selected = option.value === 'light_group:light.kitchen';
        select.dispatchEvent(new Event('change', { bubbles: true }));
      });
      await page.waitForFunction(() => document.querySelector('#buttons-state').textContent.includes('saved'));
      assert.equal(saves[0].assignment_id, 'button:test_button|mqtt|single_press|1');
      assert.deepEqual(saves[0].actions, ['light_group:light.kitchen']);
      assert.equal(await page.locator('.page-actions-primary #buttons-toolbar').isVisible(), true);
      assert.equal(await page.locator('#view-buttons > .section-heading').count(), 0);
      const settingsLabels = await page.locator('#settings-submenu > button').allTextContents();
      assert.deepEqual(settingsLabels, [...settingsLabels].sort((left, right) => left.localeCompare(right)));
      await page.locator('[data-view="voice-control"]').click();
      assert.equal(await page.locator('#view-voice-control').isVisible(), true);
      assert.equal(await page.locator('#view-homekit').isVisible(), true);
      assert.equal(await page.locator('#buttons-toolbar').isVisible(), false);
      assert.equal(await page.locator('[data-view="voice-control"]').getAttribute('aria-current'), 'page');
      await page.click('[data-voice-provider="alexa"]');
      assert.equal(await page.locator('#view-homekit').isVisible(), false);
      assert.equal(await page.locator('#voice-service-placeholder h2').textContent(), 'Amazon Alexa');
      await page.click('[data-voice-provider="nest"]');
      assert.equal(await page.locator('#voice-service-placeholder h2').textContent(), 'Google Nest');
      await page.locator('[data-view="buttons"]').click();
      assert.equal(await page.locator('#view-voice-control').isVisible(), false);
      assert.equal(await page.locator('#buttons-toolbar').isVisible(), true);
      console.log(`Configurator header and Alarm navigation passed at ${width}px`);
      await page.close();
    }
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
