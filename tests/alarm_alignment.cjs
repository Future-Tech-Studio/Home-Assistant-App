const fs = require('node:fs');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.FHT_PLAYWRIGHT || 'playwright');

(async () => {
  const html = fs.readFileSync('future_homes_tech_app/web/index.html', 'utf8');
  const styles = [...html.matchAll(/<style\b[^>]*>([\s\S]*?)<\/style>/g)].map(match => match[1]).join('\n');
  const renderer = html.slice(html.indexOf('      function fridgeAlarmDelayOptions('), html.indexOf('      function renderFridgeAlarmPanel('));
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage();
    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: 1000 });
      await page.setContent(`<style>${styles}</style><div id="alarm-device-list"><div class="device-alarm-sensor-grid"></div></div>`);
      await page.evaluate(({ renderer }) => {
        const render = new Function('escapeHtml', `${renderer}; return renderFridgeAlarmSensor;`)(value => String(value));
        document.querySelector('.device-alarm-sensor-grid').innerHTML = [1, 2, 3, 4].map(number => render({ entity_id: `binary_sensor.fridge_${number}`, friendly_name: `Refrigerator Door Sensor ${number} with a longer title`, state: 'off' }, 'Fridge', 'door', {}, { sirens: [{ entity_id: 'siren.stairway', name: 'Stairway siren' }], chimes: [{ entity_id: 'button.kitchen', name: 'Kitchen chime' }, { entity_id: 'button.upstairs', name: 'Upstairs hallway chime' }] }, false)).join('');
      }, { renderer });
      const cards = await page.locator('.fridge-alarm-sensor').evaluateAll(nodes => nodes.map(node => {
        const boxes = [...node.querySelectorAll('input[type="checkbox"]')].map(input => { const rect = input.getBoundingClientRect(); return { left: rect.left, width: rect.width, height: rect.height }; });
        return boxes;
      }));
      for (const boxes of cards) {
        for (const box of boxes) { assert.equal(box.width, 16); assert.equal(box.height, 16); }
        assert.equal(boxes[0].left, boxes[1].left);
        assert.equal(boxes[0].left, boxes.at(-1).left);
      }
      console.log(`Alarm checkbox alignment passed at ${width}px`);
    }
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
