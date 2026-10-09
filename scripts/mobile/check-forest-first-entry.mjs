import assert from 'node:assert/strict';
import { chromium } from 'playwright';
const browser = await chromium.launch({ headless: true, executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe' });
try {
  for (const width of [390, 720]) {
    const page = await browser.newPage({ viewport: { width, height: 1256 } });
    let profileSaves = 0;
    await page.route('**/forest-phaser.js*', route => route.fulfill({ contentType: 'text/javascript', body: '' }));
    await page.route('**/api/**', route => {
      const pathname = new URL(route.request().url()).pathname;
      if (pathname.endsWith('/users/me') && route.request().method() === 'PATCH') {
        const updates = route.request().postDataJSON();
        assert.equal(updates.name, '테스트수정');
        assert.equal(updates.birthday, '1970-01-01');
        profileSaves++;
        return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ id: 1, ...updates }) });
      }
      const data = pathname.endsWith('/auth/token/refresh') ? { access_token: 'synthetic-navigation-test' }
        : pathname.endsWith('/users/me') ? { id: 1, name: '테스트', birthday: '1970-01-01', gender: 'MALE' } : null;
      return route.fulfill({ status: data ? 200 : 503, contentType: 'application/json', body: JSON.stringify(data || {}) });
    });
    await page.goto('http://127.0.0.1:8000/static/forest.html?demo=1');
    await page.waitForFunction(() => {
      const canvas = document.querySelector('#forest-canvas');
      const data = canvas.getContext('2d').getImageData(0,0,canvas.width,canvas.height).data;
      return data.some((v,i) => i%4===0 && v > 180);
    });
    assert.equal(await page.locator('#forest-canvas').evaluate(el => getComputedStyle(el).objectFit), 'cover');
    assert.equal(await page.evaluate(() => document.documentElement.classList.contains('phaser-world-ready')), false);
    await page.screenshot({ path: `outputs/mobile/forest/first-entry-${width}.png` });
    const before = await page.evaluate(() => localStorage.getItem('gandang-carrot-forest-demo-v1'));
    await page.locator('.forest-service-home').click();
    await page.waitForURL('**/?workspace=home');
    await page.waitForFunction(() => document.querySelector('#header-my-page')?.hidden === false);
    assert.equal(await page.locator('#header-my-page').evaluate(el => el.hidden), false);
    assert.equal(await page.evaluate(() => localStorage.getItem('gandang-carrot-forest-demo-v1')), before);
    for (const entry of ['/?account=profile', '/service?account=profile', '/static/suin/index.html?account=profile']) {
      await page.goto(`http://127.0.0.1:8000${entry}`);
      await page.waitForFunction(() => document.querySelector('#profile-editor')?.hidden === false);
      assert.equal(await page.locator('.screen.active').getAttribute('data-step'), '8', 'Signed-in profile entry never shows the intro');
      assert.equal(await page.locator('script[src*="/static/suin/app.js"]').count(), 0);
      assert.equal(await page.locator('script[src*="/static/app.js"]').count(), 1);
      assert.equal(await page.locator('#profile-name').inputValue(), '테스트');
      await page.locator('#profile-name').fill('테스트수정');
      await page.locator('#profile-editor-form button[type="submit"]').click();
      await page.waitForFunction(() => document.querySelector('#profile-editor')?.hidden === true);
    }
    assert.equal(profileSaves, 3, 'All profile routes save through the current account API');
    console.log(`PASS ${width}px: fallback fills screen, service home navigation preserves forest data`);
    await page.close();
  }
} finally { await browser.close(); }
