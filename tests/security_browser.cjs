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
      const streams = [];
      let liveChange = false;
      let revision = 1;
      devices[1].readings[1].state = 'off';
      page.on('pageerror', error => errors.push(error.message));
      await page.route('**/*', route => {
        const request = route.request();
        const url = new URL(request.url());
        if (request.method() !== 'GET') posts.push(url.pathname);
        if (url.pathname === '/') return route.fulfill({ contentType: 'text/html', body: html });
        if (url.pathname === '/api/live/revision') {
          const changed = liveChange;
          liveChange = false;
          return new Promise(resolve => setTimeout(resolve, changed ? 0 : 400)).then(() => route.fulfill({ json: { ok: true, changed, revision: ++revision, channels: changed ? ['protect'] : [], areas: [] } }));
        }
        if (url.pathname === '/api/protect/devices') return route.fulfill({ json: { ok: true, devices, count: devices.length, stale: false } });
        if (url.pathname === '/api/protect/snapshot' && url.searchParams.get('live') === '1') {
          streams.push(url.searchParams.get('entity_id'));
          return route.fulfill({ contentType: 'image/svg+xml', body: snapshot(`LIVE ${url.searchParams.get('entity_id')} frame ${streams.length}`) });
        }
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
      assert.equal(await grid.locator('.protect-device-meta').count(), 0, 'No type or room line under the name');
      assert.deepEqual(await grid.locator('.protect-device-status').allTextContents(), ['Recording', 'Streaming', 'Offline', 'Online']);
      await page.waitForFunction(() => [...document.querySelectorAll('img[data-snapshot-entity]')].every(image => image.complete && image.naturalWidth > 0));
      assert.deepEqual([...new Set(snapshots)].sort(), ['camera.driveway_g4_pro_high', 'camera.front_doorbell_high'], 'Offline cameras are not fetched');
      assert.equal(await grid.locator('.protect-snapshot.is-missing').allTextContents().then(texts => texts.map(text => text.trim())).then(texts => texts.join()), 'Camera offline');
      const doorbell = grid.locator('.protect-device-card').first();
      // Only detections happening now show; idle sensors and past rings stay hidden.
      assert.deepEqual(await doorbell.locator('.protect-reading-label').allTextContents(), ['Motion', 'Person Detected']);
      assert.equal((await grid.locator('.protect-device-card').nth(1).locator('.protect-quiet').textContent()).trim(), 'Nothing detected right now');
      assert.equal(await grid.locator('.protect-device-card').nth(2).locator('.protect-reading, .protect-quiet').count(), 0, 'An offline camera lists nothing');
      const sensor = grid.locator('.protect-device-card').last();
      assert.deepEqual(await sensor.locator('.protect-reading-label').allTextContents(), ['Temperature', 'Battery'], 'A Protect sensor keeps its readings; a closed contact is hidden');
      assert.deepEqual(await page.locator('#view-security button').evaluateAll(buttons => buttons.map(button => button.dataset.liveEntity)),
        ['camera.front_doorbell_high', 'camera.driveway_g4_pro_high'], 'The only buttons open live views of online cameras');
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true, 'No horizontal overflow');
      if (process.env.FHT_SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.FHT_SCREENSHOT_DIR}/security-protect-${width}.png`, fullPage: true });
      // Tapping a camera opens its live view; closing it drops the stream.
      await grid.locator('[data-live-entity="camera.driveway_g4_pro_high"]').click();
      const dialog = page.locator('#protect-live-dialog');
      await dialog.waitFor();
      assert.equal(await page.locator('#protect-live-title').textContent(), 'Driveway G4 Pro');
      await page.waitForFunction(() => document.querySelector('#protect-live-image').complete && document.querySelector('#protect-live-image').naturalWidth > 0);
      // Frames keep coming while the pop-up is open.
      await page.waitForFunction(() => document.querySelector('#protect-live-image').src.includes('live=1'));
      await page.waitForTimeout(1300);
      assert.ok(streams.length >= 2, `live view loads frame after frame (${streams.length})`);
      assert.deepEqual([...new Set(streams)], ['camera.driveway_g4_pro_high']);
      assert.equal((await page.locator('#protect-live-readings').textContent()).trim(), 'Nothing detected right now');
      // A vehicle drives up: the detection appears in the pop-up and on the card, live.
      devices[1].readings[1].state = 'on';
      liveChange = true;
      await page.locator('#protect-live-readings .protect-reading-label').waitFor({ timeout: 15000 });
      assert.deepEqual(await page.locator('#protect-live-readings .protect-reading-label').allTextContents(), ['Vehicle Detected']);
      assert.deepEqual(await grid.locator('.protect-device-card').nth(1).locator('.protect-reading-label').allTextContents(), ['Vehicle Detected']);
      if (process.env.FHT_SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.FHT_SCREENSHOT_DIR}/security-live-view-${width}.png` });
      await page.locator('#protect-live-close').click();
      assert.equal(await dialog.evaluate(element => element.open), false);
      const framesAtClose = streams.length;
      await page.waitForTimeout(1200);
      assert.ok(streams.length <= framesAtClose + 1, 'Closing stops loading frames');
      assert.equal(await page.locator('#protect-live-image').getAttribute('src'), null, 'Closing drops the stream');
      await grid.locator('[data-live-entity="camera.front_doorbell_high"]').click();
      await page.keyboard.press('Escape');
      await page.waitForFunction(() => !document.querySelector('#protect-live-dialog').open && !document.querySelector('#protect-live-image').hasAttribute('src'));
      assert.equal(await page.locator('#protect-live-image').getAttribute('src'), null, 'Escape also drops the stream');
      assert.deepEqual(posts, [], 'Security sends nothing');
      assert.deepEqual(errors, []);
      console.log(`Security (UniFi Protect) page passed at ${width}px`);
      await page.close();
    }
    // The live view and camera cards follow the App color.
    for (const [color, rgb] of [['blue', 'rgb(53, 174, 247)'], ['red', 'rgb(255, 69, 69)'], ['green', 'rgb(57, 223, 101)']]) {
      const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.route('**/*', route => {
        const url = new URL(route.request().url());
        if (url.pathname === '/') return route.fulfill({ contentType: 'text/html', body: html });
        if (url.pathname === '/api/app-color') return route.fulfill({ json: { ok: true, color } });
        if (url.pathname === '/api/protect/devices') return route.fulfill({ json: { ok: true, devices, count: devices.length, stale: false } });
        if (url.pathname === '/api/protect/snapshot' || url.pathname === '/api/protect/stream') return route.fulfill({ contentType: 'image/svg+xml', body: snapshot(url.searchParams.get('entity_id')) });
        if (/\.(png|webp|jpg)$/.test(url.pathname)) return route.fulfill({ status: 404, body: '' });
        return route.fulfill({ json: { ok: true, entities: [], floors: [] } });
      });
      await page.goto('http://fht.test/');
      await page.waitForFunction(expected => document.documentElement.dataset.appColor === expected, color);
      await page.locator('[data-view="security"]').first().click();
      await page.locator('[data-live-entity="camera.driveway_g4_pro_high"]').click();
      await page.locator('#protect-live-dialog').waitFor();
      const colors = await page.evaluate(() => ({
        dialog: getComputedStyle(document.querySelector('#protect-live-dialog')).borderTopColor,
        close: getComputedStyle(document.querySelector('#protect-live-close')).borderTopColor,
        card: getComputedStyle(document.querySelector('.protect-device-card')).borderTopColor,
      }));
      const channels = value => value.replace(/^color\(srgb/, '').match(/[\d.]+/g).slice(0, 3).map(Number).map(part => value.startsWith('color(') ? Math.round(part * 255) : part);
      assert.deepEqual(channels(colors.close), channels(rgb), `${color} close circle`);
      for (const key of ['dialog', 'card']) {
        const [r, g, b] = channels(colors[key]);
        const [er, eg, eb] = channels(rgb);
        // Mixed with transparency, the color keeps the accent's hue.
        assert.ok(Math.abs(r - er) < 2 && Math.abs(g - eg) < 2 && Math.abs(b - eb) < 2, `${color} ${key} border is ${colors[key]}`);
      }
      if (process.env.FHT_SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.FHT_SCREENSHOT_DIR}/security-live-view-${color}.png` });
      assert.deepEqual(errors, []);
      console.log(`Security live view follows the ${color} App color`);
      await page.close();
    }
    // Inside Home Assistant, tapping a camera opens Home Assistant's own camera window.
    {
      const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      const hostPage = `<!doctype html><html><body><home-assistant></home-assistant><iframe id="panel" src="/app/" style="width:800px;height:600px"></iframe>
        <script>window.moreInfo = []; document.querySelector('home-assistant').addEventListener('hass-more-info', event => window.moreInfo.push(event.detail.entityId));</script></body></html>`;
      await page.route('**/*', route => {
        const url = new URL(route.request().url());
        if (url.pathname === '/') return route.fulfill({ contentType: 'text/html', body: hostPage });
        if (url.pathname === '/app/') return route.fulfill({ contentType: 'text/html', body: html.replaceAll('__FHT_CSP_NONCE__', 'n') });
        const path = url.pathname.replace(/^\/app/, '');
        if (path === '/api/protect/devices') return route.fulfill({ json: { ok: true, devices, count: devices.length, stale: false } });
        if (path === '/api/protect/snapshot') return route.fulfill({ contentType: 'image/svg+xml', body: snapshot(url.searchParams.get('entity_id')) });
        if (/\.(png|webp|jpg)$/.test(path)) return route.fulfill({ status: 404, body: '' });
        return route.fulfill({ json: { ok: true, entities: [], floors: [] } });
      });
      await page.goto('http://fht.test/');
      const app = page.frameLocator('#panel');
      const appFrame = page.frame({ url: /\/app\/$/ });
      await app.locator('[data-view="security"]').first().click();
      const promoted = () => page.evaluate(() => document.querySelector('#panel').matches(':popover-open'));
      assert.equal(await promoted(), true, 'The App fills the screen inside Home Assistant');
      await app.locator('[data-live-entity="camera.driveway_g4_pro_high"]').click();
      assert.deepEqual(await page.evaluate(() => window.moreInfo), ['camera.driveway_g4_pro_high']);
      assert.equal(await appFrame.evaluate(() => document.querySelector('#protect-live-dialog').open), false, 'The App pop-up stays closed');
      assert.equal(await promoted(), false, "Home Assistant's window shows above the App");
      await page.evaluate(() => window.dispatchEvent(new CustomEvent('dialog-closed', { detail: { dialog: 'ha-more-info-dialog' } })));
      assert.equal(await promoted(), true, 'The App returns to full screen when the window closes');
      assert.deepEqual(errors, []);
      console.log("Security camera opens Home Assistant's camera window inside Home Assistant");
      await page.close();
    }
    // With Home Assistant's player available, it plays inside the App's pop-up design.
    {
      const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      const hostPage = `<!doctype html><html><head></head><body><home-assistant></home-assistant><iframe id="panel" src="/app/" style="width:800px;height:600px"></iframe>
        <script>
          window.moreInfo = [];
          const root = document.querySelector('home-assistant');
          root.hass = { states: { 'camera.driveway_g4_pro_high': { entity_id: 'camera.driveway_g4_pro_high', state: 'streaming' } } };
          root.addEventListener('hass-more-info', event => window.moreInfo.push(event.detail.entityId));
          window.players = [];
          customElements.define('ha-camera-stream', class extends HTMLElement {
            connectedCallback() { window.players.push(this); this.textContent = 'HA PLAYER ' + this.stateObj.entity_id; this.style.cssText = 'display:grid;place-items:center;height:400px;color:#fff;background:#334'; }
            disconnectedCallback() { window.playerStopped = true; }
          });
        </script></body></html>`;
      await page.route('**/*', route => {
        const url = new URL(route.request().url());
        if (url.pathname === '/') return route.fulfill({ contentType: 'text/html', body: hostPage });
        if (url.pathname === '/app/') return route.fulfill({ contentType: 'text/html', body: html.replaceAll('__FHT_CSP_NONCE__', 'n') });
        const path = url.pathname.replace(/^\/app/, '');
        if (path === '/api/app-color') return route.fulfill({ json: { ok: true, color: 'red' } });
        if (path === '/api/protect/devices') return route.fulfill({ json: { ok: true, devices, count: devices.length, stale: false } });
        if (path === '/api/protect/snapshot') return route.fulfill({ contentType: 'image/svg+xml', body: snapshot(url.searchParams.get('entity_id')) });
        if (/\.(png|webp|jpg)$/.test(path)) return route.fulfill({ status: 404, body: '' });
        return route.fulfill({ json: { ok: true, entities: [], floors: [] } });
      });
      await page.goto('http://fht.test/');
      const app = page.frameLocator('#panel');
      await page.frame({ url: /\/app\/$/ }).waitForFunction(() => document.documentElement.dataset.appColor === 'red');
      await app.locator('[data-view="security"]').first().click();
      await app.locator('[data-live-entity="camera.driveway_g4_pro_high"]').click();
      const live = page.locator('dialog[data-fht-live]');
      await live.waitFor();
      assert.equal(await live.evaluate(dialog => dialog.open), true);
      assert.equal(await page.locator('dialog[data-fht-live] .fht-live-title').textContent(), 'Driveway G4 Pro');
      assert.deepEqual(await page.evaluate(() => window.players.map(player => [player.stateObj.entity_id, Boolean(player.hass), player.controls])), [['camera.driveway_g4_pro_high', true, true]]);
      assert.deepEqual(await page.evaluate(() => window.moreInfo), [], "Home Assistant's own window is not needed");
      assert.equal(await page.evaluate(() => document.querySelector('#panel').matches(':popover-open')), true, 'The App stays full screen underneath');
      const close = await page.evaluate(() => getComputedStyle(document.querySelector('[data-fht-live] .fht-live-close')).borderTopColor);
      assert.equal(close, 'rgb(255, 69, 69)', 'Pop-up follows the App color');
      assert.ok((await page.locator('dialog[data-fht-live] .fht-live-readings').textContent()).includes('Vehicle Detected'), 'Current detections show under the video');
      if (process.env.FHT_SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.FHT_SCREENSHOT_DIR}/security-ha-player-popup.png` });
      await page.locator('dialog[data-fht-live] .fht-live-close').click();
      await page.waitForFunction(() => !document.querySelector('dialog[data-fht-live]'));
      assert.equal(await page.evaluate(() => window.playerStopped), true, 'and stops the player');
      assert.deepEqual(errors, []);
      console.log("Security camera plays Home Assistant's player in the App's pop-up");
      await page.close();
    }
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exit(1); });
