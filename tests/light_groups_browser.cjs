const fs = require('node:fs');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.FHT_PLAYWRIGHT || 'playwright');
(async () => {
  const html = fs.readFileSync('future_homes_tech_app/web/index.html', 'utf8');
  const plan = { ok: true, overrides: { excluded_lights: [], names: {} }, rooms: [{ area: "Bedroom 6", lights: [
    { entity_id: "light.bedroom_6_fan_light_1", name: "Bedroom 6 Fan Light 1" }, { entity_id: "light.bedroom_6_fan_light_2", name: "Bedroom 6 Fan Light 2" }, { entity_id: "light.bedroom_6_desk_light", name: "Bedroom 6 Desk Light" }],
    groups: [{ entity_id: "light.fht_bedroom_6_all_lights", unique_id: "fht_bedroom_6_all_lights", name: "Bedroom 6 All Lights", default_name: "Bedroom 6 All Lights", members: ["light.bedroom_6_desk_light", "light.bedroom_6_fan_light_1", "light.bedroom_6_fan_light_2"], reason: "Every light in the room." },
      { entity_id: "light.fht_bedroom_6_fan_lights", unique_id: "fht_bedroom_6_fan_lights", name: "Bedroom 6 Fan Lights", default_name: "Bedroom 6 Fan Lights", members: ["light.bedroom_6_fan_light_1", "light.bedroom_6_fan_light_2"], reason: "Lights whose names include “Fan”." }],
    notes: ["Only one light matches “Desk”, so it is offered as the light itself."] }] };
  let saved;
  const browser = await chromium.launch({ headless: true });
  for (const width of [1280, 390]) {
    const page = await browser.newPage({ viewport: { width, height: 900 } });
    const errors = []; page.on('pageerror', e => errors.push(e.message));
    await page.route('**/*', route => {
      const url = new URL(route.request().url()); const path = url.pathname.slice(1);
      if (url.pathname === '/') return route.fulfill({ contentType: 'text/html', body: html });
      if (/\.(png|webp|jpg)$/.test(path)) return route.fulfill({ status: 404, body: '' });
      if (path === 'api/light-groups/plan') return route.fulfill({ json: plan });
      if (path === 'api/light-groups/overrides') { saved = route.request().postDataJSON(); return route.fulfill({ json: { ...plan, overrides: saved, saved: true } }); }
      return route.fulfill({ json: { ok: true, entities: [], floors: [] } });
    });
    await page.goto('http://fht.test/');
    await page.waitForTimeout(800);
    if (width < 800) await page.locator('#mobile-nav-toggle').click();
    await page.locator('#settings-toggle').click();
    await page.locator('[data-view="light-groups"]').click();
    await page.locator('[data-group-unique-id="fht_bedroom_6_fan_lights"]').waitFor();
    await page.locator('.light-groups-lights summary').click();
    await page.locator('[data-group-unique-id="fht_bedroom_6_fan_lights"]').fill("Chloe's Fan");
    await page.locator('[data-exclude-light="light.bedroom_6_desk_light"]').check();
    await page.locator('#light-groups-save').click();
    await page.waitForFunction(() => document.getElementById('light-groups-state').textContent === 'Light groups saved and rebuilt.');
    assert.deepEqual(saved, { names: { fht_bedroom_6_fan_lights: "Chloe's Fan" }, excluded_lights: ["light.bedroom_6_desk_light"] });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true);
    assert.deepEqual(errors, []);
    console.log(`Light Groups page passed at ${width}px`);
  }
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
