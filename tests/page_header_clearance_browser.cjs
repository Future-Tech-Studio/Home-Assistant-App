const fs = require('node:fs');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.FHT_PLAYWRIGHT || 'playwright');

// Every menu page's content starts below the page header and its Menu,
// Updates and Exit buttons, on a phone, a narrow iPad window, iPad portrait,
// iPad landscape and desktop. A new page that tucks under the header fails here.
const views = ['lighting', 'security', 'room-devices', 'rooms', 'portal', 'doors', 'switches', 'environment', 'presence',
  'alarm', 'buttons', 'climate-settings', 'room-modes', 'scenes', 'unifi', 'voice-control'];

(async () => {
  const html = fs.readFileSync('future_homes_tech_app/web/index.html', 'utf8');
  const browser = await chromium.launch({ headless: true });
  try {
    for (const [width, height] of [[390, 844], [604, 834], [768, 1024], [1024, 768], [1366, 1024]]) {
      const page = await browser.newPage({ viewport: { width, height } });
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.route('**/*', route => {
        const url = new URL(route.request().url());
        if (url.pathname === '/') return route.fulfill({ contentType: 'text/html', body: html });
        if (/\.(png|webp|jpg|svg)$/.test(url.pathname)) return route.fulfill({ status: 404, body: '' });
        return route.fulfill({ json: { ok: true, entities: [], floors: [], rooms: [], settings: {}, scenes: [], catalog: {}, current_modes: {}, house_settings: {}, buttons: [], control_settings: {}, aliases: {}, entries: [], users: [], devices: [] } });
      });
      await page.goto('http://fht.test/');
      await page.waitForTimeout(800);
      for (const view of views) {
        await page.evaluate(name => document.querySelector(`[data-view="${name}"]`)?.click(), view);
        await page.waitForTimeout(300);
        const { section, contentTop, headerBottom } = await page.evaluate(() => {
          const visible = element => {
            const style = getComputedStyle(element);
            const box = element.getBoundingClientRect();
            return style.display !== 'none' && style.visibility !== 'hidden' && box.width > 0 && box.height > 0;
          };
          const fade = Number.parseFloat(getComputedStyle(document.querySelector('.page-actions'), '::before').height) || 0;
          const buttons = ['.mobile-nav-toggle', '#exit-app', '#open-updates', '#update-app', '#page-revert']
            .map(selector => document.querySelector(selector))
            .filter(element => element && visible(element))
            .map(element => element.getBoundingClientRect().bottom);
          const active = [...document.querySelectorAll('main > section[id^="view-"]')].find(element => !element.hidden && visible(element));
          const tops = active ? [...active.querySelectorAll('*')]
            .filter(element => visible(element) && getComputedStyle(element).position !== 'fixed')
            .map(element => element.getBoundingClientRect().top) : [];
          return { section: active?.id, contentTop: tops.length ? Math.min(...tops) : null, headerBottom: Math.max(fade, ...buttons) };
        });
        assert.ok(section, `${view} opens at ${width}px`);
        if (contentTop === null) continue;
        assert.ok(contentTop >= headerBottom + 4, `${view} content top ${contentTop}px clears the ${headerBottom}px header at ${width}px`);
      }
      assert.deepEqual(errors, []);
      await page.close();
      console.log(`Page header clearance passed at ${width}px`);
    }
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exit(1); });
