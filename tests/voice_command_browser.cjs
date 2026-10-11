const fs = require('node:fs');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.FHT_PLAYWRIGHT || 'playwright');

// Tapping the shield logo records a command from Chromium's fake microphone
// (a steady tone), sends it as 16 kHz 16-bit PCM, and shows what Assist did.
(async () => {
  const html = fs.readFileSync('future_homes_tech_app/web/index.html', 'utf8');
  const shots = process.env.FHT_SCREENSHOT_DIR;
  const browser = await chromium.launch({ headless: true, args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'] });
  try {
    const open = async (width, height, init) => {
      const page = await browser.newPage({ viewport: { width, height } });
      const errors = [];
      const voice = [];
      page.on('pageerror', error => errors.push(error.message));
      if (init) await page.addInitScript(init);
      await page.route('**/*', route => {
        const request = route.request();
        const url = new URL(request.url());
        if (url.pathname === '/') return route.fulfill({ contentType: 'text/html', body: html });
        if (url.pathname === '/api/voice/command') {
          const typed = request.headers()['content-type'] === 'application/json';
          voice.push({ contentType: request.headers()['content-type'], bytes: request.postDataBuffer()?.length || 0, text: typed ? request.postDataJSON().text : '' });
          return route.fulfill({ json: { ok: true, transcript: typed ? request.postDataJSON().text : "Turn off Chloe's bedroom light", reply: "Turned off Chloe's Bedroom light", success: true } });
        }
        if (/\.(png|webp|jpg|svg)$/.test(url.pathname)) return route.fulfill({ status: 404, body: '' });
        return route.fulfill({ json: { ok: true, entities: [], floors: [], rooms: [], settings: {}, scenes: [], catalog: {}, current_modes: {}, house_settings: {}, buttons: [], control_settings: {}, aliases: {}, entries: [], users: [], devices: [] } });
      });
      // localhost counts as https, which the microphone needs.
      await page.goto('http://localhost/');
      await page.waitForTimeout(800);
      return { page, errors, voice };
    };

    // iPad and computer: the shield in the sidebar listens straight away.
    {
      const { page, errors, voice } = await open(1180, 820);
      await page.click('#voice-command-shield');
      await page.waitForSelector('#voice-command-dialog.is-listening');
      assert.equal(await page.textContent('#voice-command-status'), 'Listening…');
      if (shots) await page.screenshot({ path: `${shots}/voice-listening-1180.png` });
      await page.waitForTimeout(1500);
      await page.click('#voice-command-stop');
      await page.waitForSelector('#voice-command-reply:not([hidden])');
      assert.equal(voice.length, 1);
      assert.equal(voice[0].contentType, 'application/octet-stream');
      assert.equal(voice[0].bytes % 2, 0, 'audio is 16-bit samples');
      assert.ok(voice[0].bytes > 16000 * 2 * 1 && voice[0].bytes < 16000 * 2 * 3, `about 1.5 s of 16 kHz audio, got ${voice[0].bytes} bytes`);
      assert.equal(await page.textContent('#voice-command-heard'), 'You said: “Turn off Chloe\'s bedroom light”');
      assert.equal(await page.textContent('#voice-command-reply'), "Turned off Chloe's Bedroom light");
      assert.equal(await page.isVisible('#voice-command-again'), true);
      if (shots) await page.screenshot({ path: `${shots}/voice-result-1180.png` });

      await page.fill('#voice-command-text', 'turn on the porch light');
      await page.press('#voice-command-text', 'Enter');
      await page.waitForFunction(() => document.querySelector('#voice-command-heard').textContent.includes('porch'));
      assert.deepEqual(voice[1], { contentType: 'application/json', bytes: voice[1].bytes, text: 'turn on the porch light' });
      await page.click('#voice-command-close');
      assert.equal(await page.evaluate(() => document.getElementById('voice-command-dialog').open), false);
      assert.deepEqual(errors, []);
      await page.close();
    }

    // Phone: tapping the shield still opens the menu; holding it opens Voice
    // Command with a Talk button, without opening the menu.
    {
      const { page, errors } = await open(390, 844);
      await page.click('#mobile-nav-toggle');
      assert.equal(await page.getAttribute('#mobile-nav-toggle', 'aria-expanded'), 'true');
      await page.click('#mobile-nav-backdrop', { force: true });
      assert.equal(await page.getAttribute('#mobile-nav-toggle', 'aria-expanded'), 'false');
      await page.hover('#mobile-nav-toggle');
      await page.mouse.down();
      await page.waitForTimeout(700);
      await page.mouse.up();
      await page.waitForSelector('#voice-command-dialog[open]');
      assert.equal(await page.getAttribute('#mobile-nav-toggle', 'aria-expanded'), 'false');
      assert.equal(await page.textContent('#voice-command-status'), 'Tap Talk, then say a command.');
      assert.equal(await page.textContent('#voice-command-again'), 'Talk');
      if (shots) await page.screenshot({ path: `${shots}/voice-hold-390.png` });
      await page.click('#voice-command-again');
      await page.waitForSelector('#voice-command-dialog.is-listening');
      await page.click('#voice-command-close');
      assert.deepEqual(errors, []);
      await page.close();
    }

    // No speech-to-text yet: the sheet offers Set up voice, shows progress,
    // and ends on a Talk button.
    {
      const { page, errors } = await open(1180, 820);
      let polls = 0;
      await page.route('**/api/voice/command', route => route.fulfill({ json: { ok: false, error: "Voice isn't set up yet. Tap Set up voice, or type the command.", setup: true } }));
      await page.route('**/api/voice/setup', route => {
        if (route.request().method() === 'POST') return route.fulfill({ json: { ok: true, state: 'working', message: 'Installing Speech-to-Phrase… this takes a minute or two.' } });
        polls += 1;
        return route.fulfill({ json: polls < 2 ? { ok: true, state: 'working', message: 'Connecting Speech-to-Phrase to Home Assistant…' } : { ok: true, state: 'ready', message: 'Voice is set up. Tap the shield and say a command.' } });
      });
      await page.click('#voice-command-shield');
      await page.waitForSelector('#voice-command-dialog.is-listening');
      await page.waitForTimeout(600);
      await page.click('#voice-command-stop');
      await page.waitForSelector('#voice-command-setup:not([hidden])');
      assert.equal(await page.isVisible('#voice-command-again'), false);
      if (shots) await page.screenshot({ path: `${shots}/voice-setup-offer-1180.png` });
      await page.click('#voice-command-setup');
      await page.waitForFunction(() => document.querySelector('#voice-command-status').textContent.startsWith('Installing'));
      if (shots) await page.screenshot({ path: `${shots}/voice-setup-working-1180.png` });
      await page.waitForFunction(() => document.querySelector('#voice-command-reply').textContent.startsWith('Voice is set up'), null, { timeout: 10000 });
      assert.equal(await page.textContent('#voice-command-again'), 'Talk');
      assert.equal(await page.isVisible('#voice-command-setup'), false);
      if (shots) await page.screenshot({ path: `${shots}/voice-setup-ready-1180.png` });
      assert.deepEqual(errors, []);
      await page.close();
    }

    // A screen that refuses the microphone says so and keeps the text box.
    {
      const { page, errors } = await open(1024, 1366, () => {
        navigator.mediaDevices.getUserMedia = () => Promise.reject(new DOMException('denied', 'NotAllowedError'));
      });
      await page.click('#voice-command-shield');
      await page.waitForFunction(() => document.querySelector('#voice-command-status').textContent.includes('Microphone access is off'));
      assert.equal(await page.isVisible('#voice-command-text'), true);
      assert.equal(await page.isVisible('#voice-command-stop'), false);
      if (shots) await page.screenshot({ path: `${shots}/voice-denied-1024.png` });
      assert.deepEqual(errors, []);
      await page.close();
    }
  } finally {
    await browser.close();
  }
  console.log('The shield listens, sends 16 kHz audio or typed text, shows what Assist did, and falls back to typing.');
})().catch(error => { console.error(error); process.exit(1); });
