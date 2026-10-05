const fs = require('node:fs');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.FHT_PLAYWRIGHT || 'playwright');

// Security shows UniFi Protect devices only, with snapshots and live states.
(async () => {
  const html = fs.readFileSync('future_homes_tech_app/web/index.html', 'utf8');
  const reading = (entity_id, label, domain, state, extra = {}) => ({ entity_id, label, domain, state, device_class: '', unit: '', last_changed: '', ...extra });
  const devices = [
    { device_id: 'db', name: 'Front Doorbell', area: 'Porch', kind: 'Doorbell', online: true, camera_state: 'recording', snapshot_entity: 'camera.front_doorbell_high', readings: [
      reading('binary_sensor.front_doorbell_doorbell', 'Doorbell', 'binary_sensor', 'off'),
      reading('binary_sensor.front_doorbell_motion', 'Motion', 'binary_sensor', 'on', { device_class: 'motion' }),
      reading('binary_sensor.front_doorbell_person_detected', 'Person Detected', 'binary_sensor', 'on', { device_class: 'occupancy' }),
      reading('binary_sensor.front_doorbell_vehicle_detected', 'Vehicle Detected', 'binary_sensor', 'off', { device_class: 'occupancy' }),
      reading('event.front_doorbell_doorbell', 'Doorbell Ring', 'event', new Date(Date.now() - 12 * 60000).toISOString())] },
    { device_id: 'g4', name: 'Driveway G4 Pro', area: 'Driveway', kind: 'Camera', online: true, camera_state: 'streaming', snapshot_entity: 'camera.driveway_g4_pro_high', readings: [
      reading('binary_sensor.driveway_g4_pro_motion', 'Motion', 'binary_sensor', 'off', { device_class: 'motion' }),
      reading('binary_sensor.driveway_g4_pro_vehicle_detected', 'Vehicle Detected', 'binary_sensor', 'off', { device_class: 'occupancy' })] },
    { device_id: 'side', name: 'Side Yard G5 Bullet', area: 'Side Yard', kind: 'Camera', online: false, camera_state: 'unavailable', snapshot_entity: 'camera.side_yard_high', readings: [
      reading('binary_sensor.side_yard_motion', 'Motion', 'binary_sensor', 'unavailable', { device_class: 'motion' })] },
    { device_id: 'up', name: 'Garage UP-Sense', area: 'Garage', kind: 'Sensor', online: true, camera_state: '', snapshot_entity: '', readings: [
      reading('binary_sensor.garage_sense_contact', 'Contact', 'binary_sensor', 'off', { device_class: 'door' }),
      reading('sensor.garage_sense_temperature', 'Temperature', 'sensor', '68', { device_class: 'temperature', unit: '°F' }),
      reading('sensor.garage_sense_battery', 'Battery', 'sensor', '88', { device_class: 'battery', unit: '%' })] },
  ];
  const snapshot = name => `<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360"><defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#5b7895"/><stop offset=".6" stop-color="#2f3d48"/><stop offset="1" stop-color="#1b2228"/></linearGradient></defs><rect width="640" height="360" fill="url(#g)"/><rect x="0" y="250" width="640" height="110" fill="#3a3f42"/><text x="16" y="30" fill="#fff" font-family="monospace" font-size="16">${name}  (test image)</text></svg>`;
  const browser = await chromium.launch({ headless: true });
  try {
    for (const width of [1280, 390]) {
      const page = await browser.newPage({ viewport: { width, height: 900 } });
      const errors = [];
      const posts = [];
      const snapshots = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.route('**/*', route => {
        const request = route.request();
        const url = new URL(request.url());
        if (request.method() !== 'GET') posts.push(url.pathname);
        if (url.pathname === '/') return route.fulfill({ contentType: 'text/html', body: html });
        if (url.pathname === '/api/protect/devices') return route.fulfill({ json: { ok: true, devices, count: devices.length, stale: false } });
        if (url.pathname === '/api/protect/snapshot') {
          snapshots.push(url.searchParams.get('entity_id'));
          return route.fulfill({ contentType: 'image/svg+xml', body: snapshot(url.searchParams.get('entity_id')) });
        }
        if (/\.(png|webp|jpg)$/.test(url.pathname)) return route.fulfill({ status: 404, body: '' });
        return route.fulfill({ json: { ok: true, entities: [], floors: [] } });
      });
      await page.goto('http://fht.test/');
      await page.waitForTimeout(800);
      if (width < 800) await page.locator('#mobile-nav-toggle').click();
      await page.locator('[data-view="security"]').first().click();
      const grid = page.locator('#protect-device-grid');
      await grid.locator('.protect-device-card').first().waitFor();
      assert.deepEqual(await grid.locator('.protect-device-name').allTextContents(), devices.map(device => device.name));
      assert.deepEqual(await grid.locator('.protect-device-status').allTextContents(), ['Recording', 'Streaming', 'Offline', 'Online']);
      await page.waitForFunction(() => [...document.querySelectorAll('img[data-snapshot-entity]')].every(image => image.complete && image.naturalWidth > 0));
      assert.deepEqual([...new Set(snapshots)].sort(), ['camera.driveway_g4_pro_high', 'camera.front_doorbell_high'], 'Offline cameras are not fetched');
      assert.equal(await grid.locator('.protect-snapshot.is-missing').allTextContents().then(texts => texts.map(text => text.trim())).then(texts => texts.join()), 'Camera offline');
      const doorbell = grid.locator('.protect-device-card').first();
      assert.deepEqual(await doorbell.locator('.protect-reading.is-active .protect-reading-label').allTextContents(), ['Motion', 'Person Detected']);
      assert.equal((await doorbell.locator('.protect-reading').last().locator('.protect-reading-value').textContent()).trim(), '12 min ago');
      const sensor = grid.locator('.protect-device-card').last();
      assert.deepEqual(await sensor.locator('.protect-reading-value').allTextContents(), ['Closed', '68 °F', '88%']);
      assert.equal(await page.locator('#view-security button').count(), 0, 'Security has no controls');
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true, 'No horizontal overflow');
      if (process.env.FHT_SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.FHT_SCREENSHOT_DIR}/security-protect-${width}.png`, fullPage: true });
      assert.deepEqual(posts, [], 'Security sends nothing');
      assert.deepEqual(errors, []);
      console.log(`Security (UniFi Protect) page passed at ${width}px`);
      await page.close();
    }
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exit(1); });
