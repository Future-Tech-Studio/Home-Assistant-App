const fs = require('node:fs');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.FHT_PLAYWRIGHT || 'playwright');

// On iPad the Home Assistant app paints a strip behind the status bar in the
// frontend's --app-theme-color (white on the default light theme). The host
// page here stands in for Home Assistant and the app: it serves the panel in
// an ingress-style iframe and paints a strip from what the app is told.
const hostPage = `<!doctype html><html><head><meta name="theme-color" content="#ffffff">
<style>html { --app-theme-color: #ffffff; --app-header-background-color: #ffffff; --primary-background-color: #fafafa; }
body { margin: 0; background: var(--primary-background-color); font: 16px sans-serif; }
#strip { position: fixed; inset: 0 0 auto 0; height: 24px; margin: 0; padding: 0 16px; border: 0; width: 100%; box-sizing: border-box;
  font: 600 13px -apple-system, sans-serif; line-height: 24px; display: flex; justify-content: space-between; }
iframe { width: 300px; height: 300px; border: 0; }</style></head>
<body><home-assistant>Home Assistant</home-assistant><div id="strip" popover="manual"><span>9:41</span><span>100%</span></div>
<iframe src="/app/"></iframe>
<script>
  const strip = document.getElementById('strip');
  window.webkit = { messageHandlers: { updateThemeColors: { postMessage(colors) {
    window.stripColor = colors['--app-theme-color'];
    strip.style.background = window.stripColor;
    strip.style.color = /255, 255, 255|#fff/.test(window.stripColor) ? '#000' : '#fff';
    window.raiseStrip();
  } } } };
  // The real strip is native, so it always sits above the web view.
  window.raiseStrip = () => {
    if (strip.matches(':popover-open')) strip.hidePopover();
    strip.showPopover();
  };
  window.webkit.messageHandlers.updateThemeColors.postMessage({ '--app-theme-color': getComputedStyle(document.documentElement).getPropertyValue('--app-theme-color').trim() });
</script></body></html>`;

(async () => {
  const html = fs.readFileSync('future_homes_tech_app/web/index.html', 'utf8');
  const shots = process.env.FHT_SCREENSHOT_DIR;
  const browser = await chromium.launch({ headless: true });
  try {
    for (const [width, height] of [[1180, 820], [820, 1180]]) {
      const page = await browser.newPage({ viewport: { width, height } });
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.route('**/*', route => {
        const url = new URL(route.request().url());
        if (url.pathname === '/') return route.fulfill({ contentType: 'text/html', body: hostPage });
        if (url.pathname === '/app/') return route.fulfill({ contentType: 'text/html', body: html });
        if (/\.(png|webp|jpg|svg)$/.test(url.pathname)) return route.fulfill({ status: 404, body: '' });
        return route.fulfill({ json: { ok: true, entities: [], floors: [], rooms: [], settings: {}, scenes: [], catalog: {}, current_modes: {}, house_settings: {}, buttons: [], control_settings: {}, aliases: {}, entries: [], users: [], devices: [] } });
      });
      await page.goto('http://fht.test/');
      await page.waitForTimeout(1000);
      await page.evaluate(() => window.raiseStrip());
      assert.equal(await page.evaluate(() => document.querySelector('iframe').matches(':popover-open')), true);
      assert.equal(await page.evaluate(() => window.stripColor), 'rgb(7, 16, 26)', `status-bar strip is not dark at ${width}px`);
      assert.equal(await page.evaluate(() => document.querySelector('meta[name="theme-color"]').content), '#07101a');
      if (shots) await page.screenshot({ path: `${shots}/ipad-status-bar-${width}.png` });
      // Leaving the panel hands Home Assistant its own colours back.
      await page.evaluate(() => document.querySelector('iframe').contentWindow.fhtExitEmbedded('/config'));
      await page.waitForTimeout(200);
      assert.equal(await page.evaluate(() => window.stripColor), 'rgb(255, 255, 255)');
      assert.equal(await page.evaluate(() => document.querySelector('meta[name="theme-color"]').content), '#ffffff');
      assert.equal(await page.evaluate(() => document.body.style.cssText), '');
      assert.deepEqual(errors, []);
      await page.close();
    }
  } finally {
    await browser.close();
  }
  console.log('iPad status-bar strip follows the panel while it is shown and returns to Home Assistant\'s theme after.');
})().catch(error => { console.error(error); process.exit(1); });
