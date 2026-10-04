const fs = require('node:fs');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.FHT_PLAYWRIGHT || 'playwright');

// Renders the Alarm → Device Sensors outputs and a bedroom Armed Away / Armed Stay Kids
// panel with phones offered as outputs, at desktop and phone widths.
(async () => {
  const html = fs.readFileSync('future_homes_tech_app/web/index.html', 'utf8');
  const styles = [...html.matchAll(/<style\b[^>]*>([\s\S]*?)<\/style>/g)].map(match => match[1]).join('\n');
  const slice = (start, end) => {
    const from = html.indexOf(start);
    const to = html.indexOf(end, from);
    assert.ok(from >= 0 && to > from, `index.html no longer contains ${start.trim()} … ${end.trim()}`);
    return html.slice(from, to);
  };
  const fridgeSource = slice('      function fridgeAlarmDelayOptions(', '      function syncFridgeAlarmRow(');
  const bedroomSource = slice('      function bedroomModeOffsetOptions(', '      const alarmModes = [');
  const settingsSource = slice('      function bedroomModeSettingsFromCard(', '      async function saveBedroomModes(');
  const AUSTIN = 'notify.mobile_app_austins_iphone';
  const CHLOE = 'notify.mobile_app_chloes_pixel_8';
  const GONE = 'notify.mobile_app_old_phone';
  const phones = [
    { service: AUSTIN, name: "Austin's iPhone" },
    { service: CHLOE, name: 'Chloé’s Pixel 8 with a long device name that wraps' },
  ];
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: 1400 });
      await page.setContent(`<style>${styles}</style><main>
        <section id="view-alarm"><section id="alarm-device-card" aria-label="Device Sensors"><div id="alarm-device-list"></div></section></section>
        <section id="view-room-modes"><div class="room-mode-area-grid" id="room-mode-list"></div></section>
      </main>`);
      const result = await page.evaluate(({ fridgeSource, bedroomSource, settingsSource, phones, AUSTIN, GONE }) => {
        const escapeHtml = (value) => String(value).replace(/[&<>"']/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character]));
        const settingsApiPayloads = new Map([['api/bedroom-modes', { phone_targets: phones }]]);
        const fridge = new Function('escapeHtml', `${fridgeSource}; return { renderFridgeAlarmPanel };`)(escapeHtml);
        // The bedroom picker shares phoneAlertLabels with the fridge outputs, so both slices load together.
        const bedroom = new Function('escapeHtml', 'settingsApiPayloads', `${fridgeSource}; ${bedroomSource}; ${settingsSource}; return { renderBedroomModeCard, bedroomModeSettingsFromCard };`)(escapeHtml, settingsApiPayloads);

        document.getElementById('alarm-device-list').innerHTML = fridge.renderFridgeAlarmPanel({ fridge_alarms: {
          devices: [{ name: 'Garage Fridge',
            door_sensors: [{ entity_id: 'binary_sensor.garage_fridge_door', friendly_name: 'Garage Fridge Door', state: 'off' }],
            temperature_sensors: [{ entity_id: 'sensor.garage_fridge_temperature', friendly_name: 'Garage Fridge Temperature', state: '38', unit: '°F' }] }],
          settings: { 'sensor.garage_fridge_temperature': { enabled: true, threshold: 40, delay_minutes: 5, alert_targets: [], notify_targets: [AUSTIN, GONE] } },
          alarm_targets: { sirens: [{ entity_id: 'siren.hallway', name: 'Hallway siren' }], chimes: [] },
          webhook_configured: false,
          phone_targets: phones,
          phone_targets_error: null,
        } });
        document.getElementById('room-mode-list').innerHTML = bedroom.renderBedroomModeCard(
          'Bedroom 3', "Maverick's Bedroom",
          { armed_away_enabled: true, armed_stay_kids_enabled: true, armed_stay_kids_notify_targets: [AUSTIN] },
          'Day', [], { armed_away: false, armed_stay_kids: false }, {}, false, [], []);

        const describe = (selector) => [...document.querySelectorAll(selector)].map((input) => ({
          value: input.value, checked: input.checked, text: input.parentElement.textContent.trim(),
        }));
        const card = document.querySelector('[data-bedroom-mode-card]');
        const awayPhones = describe('[data-bedroom-list-field="armed_away_notify_targets"]');
        const kidsPhones = describe('[data-bedroom-list-field="armed_stay_kids_notify_targets"]');
        const pick = (settings) => ({ away: settings.armed_away_notify_targets, kids: settings.armed_stay_kids_notify_targets });
        const before = pick(bedroom.bedroomModeSettingsFromCard(card));
        card.querySelector('[data-bedroom-list-field="armed_away_notify_targets"]').checked = true;
        const after = pick(bedroom.bedroomModeSettingsFromCard(card));
        const rects = [...document.querySelectorAll('#alarm-device-list *, #room-mode-list *')].map((node) => node.getBoundingClientRect());
        return {
          doorPhones: describe('[data-fridge-alarm-sensor][data-kind="door"] [data-fridge-field="notify_targets"]'),
          temperaturePhones: describe('[data-fridge-alarm-sensor][data-kind="temperature"] [data-fridge-field="notify_targets"]'),
          sirenFirst: document.querySelector('[data-fridge-alarm-sensor][data-kind="door"] .device-output-options input').value,
          testButtons: [...document.querySelectorAll('[data-phone-alert-test]')].map((button) => button.dataset.phoneAlertTest),
          awayPhones, kidsPhones, before, after,
          checkboxWidths: [...document.querySelectorAll('#alarm-device-list input[type="checkbox"]')].map((input) => input.getBoundingClientRect().width),
          maxRight: Math.max(...rects.map((rect) => rect.right)),
          pageOverflow: document.documentElement.scrollWidth > window.innerWidth + 1,
        };
      }, { fridgeSource, bedroomSource, settingsSource, phones, AUSTIN, GONE });

      assert.deepEqual(result.doorPhones, [
        { value: AUSTIN, checked: false, text: "Phone: Austin's iPhone" },
        { value: CHLOE, checked: false, text: 'Phone: Chloé’s Pixel 8 with a long device name that wraps' },
      ], 'Phones are offered beside sirens and chimes, off by default');
      assert.equal(result.sirenFirst, 'siren.hallway', 'Audible outputs stay first in the row');
      assert.deepEqual(result.temperaturePhones.map((item) => [item.value, item.checked, item.text]), [
        [AUSTIN, true, "Phone: Austin's iPhone"],
        [CHLOE, false, 'Phone: Chloé’s Pixel 8 with a long device name that wraps'],
        [GONE, true, 'Phone: Unavailable saved phone'],
      ], 'Saved phones stay checked, even when no longer signed in');
      assert.deepEqual(result.testButtons, [AUSTIN, CHLOE], 'Every phone gets a Send test button');
      assert.deepEqual(result.awayPhones.map((item) => item.checked), [false, false]);
      assert.deepEqual(result.kidsPhones.map((item) => [item.value, item.checked]), [[AUSTIN, true], [CHLOE, false]]);
      assert.deepEqual(result.before, { away: [], kids: [AUSTIN] });
      assert.deepEqual(result.after, { away: [AUSTIN], kids: [AUSTIN] }, 'Ticked phones are part of the saved bedroom settings');
      assert.ok(result.checkboxWidths.length >= 8 && result.checkboxWidths.every((value) => value === 16), 'Phone checkboxes match the other outputs');
      assert.ok(result.maxRight <= width + 1, `Content stays inside ${width}px (widest element ends at ${result.maxRight}px)`);
      assert.equal(result.pageOverflow, false, 'No horizontal page scroll');
      assert.deepEqual(errors, []);
      console.log(`Phone alert outputs passed at ${width}px`);
    }
  } finally {
    await browser.close();
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });
