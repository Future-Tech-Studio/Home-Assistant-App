const fs = require('node:fs');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.FHT_PLAYWRIGHT || 'playwright');
(async () => {
  const html = fs.readFileSync('future_homes_tech_app/web/index.html', 'utf8');
  const targets = { sirens: [{ entity_id: 'siren.hallway_siren', name: 'Hallway Siren' }], chimes: [{ entity_id: 'button.kitchen_chime_play_buzzer', name: 'Kitchen Chime' }] };
  const alerts = { ok: true, door_open_alerts: {
    rooms: [
      { area: 'Entry', display_name: 'Mudroom', sensors: [
        { entity_id: 'binary_sensor.front_door_sensor', display_name: 'Front Door', friendly_name: 'Front Door Sensor', state: 'off', missing: false }] },
      { area: 'Kitchen', display_name: 'Kitchen', sensors: [
        { entity_id: 'binary_sensor.kitchen_window', display_name: 'Kitchen Window', friendly_name: 'Kitchen Window Contact Sensor', state: 'on', missing: false },
        { entity_id: 'binary_sensor.patio_door', display_name: 'Patio Door With A Much Longer Name Than Usual', friendly_name: 'Patio Door Sensor', state: 'unavailable', missing: false }] },
    ],
    settings: { 'binary_sensor.kitchen_window': { enabled: true, delay_minutes: 10, when: 'night', alert_targets: ['siren.hallway_siren'], unifi_webhook: false, notification: true } },
    alarm_targets: targets, webhook_configured: false, house_mode: 'Day', stale: false } };
  const fridge = { ok: true, fridge_alarms: { devices: [], settings: {}, alarm_targets: targets, webhook_configured: false } };
  const browser = await chromium.launch({ headless: true });
  for (const width of [1280, 390]) {
    const saved = [];
    const page = await browser.newPage({ viewport: { width, height: 900 } });
    const errors = []; page.on('pageerror', e => errors.push(e.message));
    await page.route('**/*', route => {
      const url = new URL(route.request().url()); const path = url.pathname.slice(1);
      if (url.pathname === '/') return route.fulfill({ contentType: 'text/html', body: html });
      if (/\.(png|webp|jpg)$/.test(path)) return route.fulfill({ status: 404, body: '' });
      if (path === 'api/alarm-door-settings') return route.fulfill({ json: { ok: true, settings: {}, stale: false, sensors: [] } });
      if (path === 'api/fridge-alarms') return route.fulfill({ json: fridge });
      if (path === 'api/door-open-alerts' && route.request().method() === 'POST') {
        const body = route.request().postDataJSON(); saved.push(body);
        return route.fulfill({ json: { ok: true, saved: true, activated: true, settings: { ...alerts.door_open_alerts.settings, [body.entity_id]: body }, automations: [] } });
      }
      if (path === 'api/door-open-alerts') return route.fulfill({ json: alerts });
      return route.fulfill({ json: { ok: true, entities: [], floors: [] } });
    });
    await page.goto('http://fht.test/');
    await page.waitForTimeout(800);
    if (width < 800) await page.locator('#mobile-nav-toggle').click();
    await page.locator('#settings-toggle').click();
    await page.locator('[data-view="alarm"]').first().click();
    await page.locator('[data-alarm-section="device"]').click();
    await page.locator('[data-door-open-alert]').first().waitFor();
    assert.deepEqual(await page.locator('.door-open-alert-room-title').allTextContents(), ['Mudroom', 'Kitchen']);
    assert.equal(await page.locator('[data-door-open-alert]').count(), 3);
    assert.equal(await page.locator('#alarm-door-open-list .fridge-alarm-sensor-name').first().textContent(), 'Front Door');
    const window = page.locator('[data-door-open-alert][data-entity-id="binary_sensor.kitchen_window"]');
    assert.equal(await window.locator('[data-door-open-field="enabled"]').isChecked(), true);
    assert.equal(await window.locator('[data-door-open-field="when"]').inputValue(), 'night');
    assert.equal(await window.locator('[data-door-open-field="delay_minutes"]').inputValue(), '10');
    assert.equal(await window.locator('[data-door-open-field="alert_targets"][value="siren.hallway_siren"]').isChecked(), true);
    assert.equal(await window.locator('.fridge-alarm-current').textContent(), 'Open');
    assert.equal(await window.locator('[data-door-open-field="unifi_webhook"]').isDisabled(), true);
    const front = page.locator('[data-door-open-alert][data-entity-id="binary_sensor.front_door_sensor"]');
    assert.equal(await front.locator('[data-door-open-field="when"]').inputValue(), 'any');
    assert.equal(await front.locator('[data-door-open-field="notification"]').isChecked(), true);
    const posted = () => page.waitForResponse(r => r.request().method() === 'POST' && r.url().endsWith('api/door-open-alerts'));
    await Promise.all([posted(), front.locator('[data-door-open-field="when"]').selectOption('night_sleep')]);
    assert.deepEqual(saved.at(-1), { entity_id: 'binary_sensor.front_door_sensor', enabled: false, delay_minutes: 5, when: 'night_sleep', alert_targets: [], notification: true, unifi_webhook: false });
    await page.waitForFunction(() => document.querySelector('[data-entity-id="binary_sensor.front_door_sensor"] [data-door-open-feedback]').textContent === 'Saved');
    await Promise.all([posted(), front.locator('[data-door-open-field="alert_targets"][value="button.kitchen_chime_play_buzzer"]').check()]);
    await Promise.all([posted(), front.locator('[data-door-open-field="delay_minutes"]').selectOption('30')]);
    await Promise.all([posted(), front.locator('[data-door-open-field="enabled"]').check()]);
    assert.deepEqual(saved.at(-1), { entity_id: 'binary_sensor.front_door_sensor', enabled: true, delay_minutes: 30, when: 'night_sleep', alert_targets: ['button.kitchen_chime_play_buzzer'], notification: true, unifi_webhook: false });
    await page.waitForFunction(() => !document.querySelector('[data-entity-id="binary_sensor.front_door_sensor"] [data-door-open-field="when"]').disabled);
    assert.equal(await front.locator('[data-door-open-field="unifi_webhook"]').isDisabled(), true);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true);
    assert.equal(await page.locator('#alarm-door-open-list').evaluate(el => el.scrollWidth <= el.clientWidth + 1), true);
    const columns = await page.locator('.door-open-alert-grid').first().evaluate(el => getComputedStyle(el).gridTemplateColumns.trim().split(/\s+/).length);
    assert.equal(columns, width < 761 ? 1 : 2);
    assert.deepEqual(errors, []);
    console.log(`Door Left Open section passed at ${width}px`);
    await page.close();
  }
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
