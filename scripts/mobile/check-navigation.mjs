import assert from 'node:assert/strict';
import { chromium } from 'playwright';
import { mkdir } from 'node:fs/promises';
const browser = await chromium.launch({ headless: true, executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe' });
const origin = 'http://127.0.0.1:8000';
async function checkAccountMenu(page) {
  const styles = await page.locator('.header-my-page-menu > .text-button').evaluateAll(items => items.map(item => {
    const css = getComputedStyle(item), box = item.getBoundingClientRect();
    return [box.width, box.height, css.borderRadius, css.borderWidth, css.padding, css.fontSize, css.lineHeight];
  }));
  assert.ok(styles.length > 1);
  for (const style of styles) assert.deepEqual(style, styles[0], 'Replay link has the same box as every account button');
}
try {
  await mkdir('outputs/mobile/navigation', { recursive: true });
  for (const width of [390, 720, 1280]) {
    const page = await browser.newPage({ viewport: { width, height: 1000 } });
    let signedIn = false;
    await page.route('**/api/**', route => {
      const path = new URL(route.request().url()).pathname;
      let status = 200, data = {};
      if (path.endsWith('/auth/token/refresh')) { status = signedIn ? 200 : 401; data = { access_token: 'synthetic-navigation' }; }
      else if (path.endsWith('/users/me')) data = { id: 1, name: '테스트', birthday: '1970-01-01', gender: 'MALE' };
      else if (path.endsWith('/consents')) data = { items: [{ consent_item: 'health_data', version: '1.0', is_agreed: true }] };
      else if (path.endsWith('/eligibility-checks/latest')) data = { age: 56, service_eligible: true, model_eligible: true, current_health_check_eligible: true, future_prediction_eligible: true, challenge_eligible: true, reason_codes: [] };
      else if (path.endsWith('/health-checkups')) data = { items: [{ checkup_id: 1, created_at: '2026-10-01T00:00:00Z' }] };
      else status = 404;
      return route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) });
    });
    await page.goto(`${origin}/static/intro-retro.html`);
    await page.waitForFunction(() => !document.documentElement.classList.contains('intro-session-checking'));
    const bar = await page.locator('.topbar').boundingBox();
    assert.ok(Math.abs(bar.x) < 1 && Math.abs(bar.width - width) < 1, 'Guest header spans the viewport');
    await page.screenshot({ path: `outputs/mobile/navigation/guest-${width}.png` });
    signedIn = true;
    await page.reload();
    await page.waitForURL(url => url.pathname === '/');
    await page.waitForFunction(() => document.querySelector('.screen.active')?.dataset.step === '8');
    const account = await page.locator('#header-my-page').boundingBox();
    const utilities = await page.locator('.header-utilities').boundingBox();
    assert.ok(Math.abs(account.x + account.width - utilities.x - utilities.width) < 2, 'My page is the rightmost utility');
    assert.ok(utilities.x + utilities.width <= width, 'My page fits the viewport');
    await page.screenshot({ path: `outputs/mobile/navigation/home-${width}.png` });
    await page.locator('#open-health-management').click();
    for (const largeText of [false, true]) {
      await page.evaluate(large => document.body.classList.toggle('large-text', large), largeText);
      const panel = await page.locator('#home-health-management').boundingBox();
      const medical = await page.locator('#dashboard-find-nearby-medical-facilities').boundingBox();
      const close = await page.locator('#close-health-management').boundingBox();
      for (const button of [medical, close]) {
        assert.ok(button.x >= panel.x && button.x + button.width <= panel.x + panel.width, 'Health management action fits the panel');
        assert.ok(button.x + button.width <= width, 'Health management action fits the viewport');
      }
      assert.ok(medical.x + medical.width <= close.x, 'Medical shortcut and close button do not overlap');
      assert.ok(medical.height < 140 && close.height < 140, 'Actions stay compact rather than stretching vertically');
      await page.locator('#home-health-management > .dashboard-management-heading').first().screenshot({ path: `outputs/mobile/navigation/health-${width}${largeText ? '-large' : ''}.png`, animations: 'disabled' });
    }
    await page.evaluate(() => document.body.classList.remove('large-text'));
    await page.locator('#close-health-management').click();
    assert.equal(await page.locator('#home-health-management').isVisible(), false, 'Close folds health management');
    await page.locator('#header-my-page-toggle').click();
    await checkAccountMenu(page);
    await page.locator('.intro-replay-button').click();
    await page.waitForURL('**/static/intro-retro.html?intro=replay');
    await page.waitForFunction(() => document.body.classList.contains('intro-authenticated'));
    assert.equal(await page.locator('.retro-intro').isVisible(), true);
    await page.locator('#header-my-page-toggle').click();
    await checkAccountMenu(page);
    await page.screenshot({ path: `outputs/mobile/navigation/replay-menu-${width}.png` });
    await page.goBack();
    await page.waitForFunction(() => document.querySelector('.screen.active')?.dataset.step === '8');
    await page.locator('[data-top-workspace="tools"]').click();
    await page.locator('[data-top-workspace="report"]').click();
    await page.evaluate(async () => {
      const { handleAppBack } = await import('/static/mobile/back-navigation.mjs');
      handleAppBack({ document, window, app: { minimizeApp: async () => { throw new Error('Must not minimize'); } }, canGoBack: true });
    });
    assert.equal(await page.locator('[data-workspace-panel="tools"]').evaluate(el => el.hidden), false, 'Back returns to tools, not home');
    await page.evaluate(async () => {
      document.documentElement.classList.add('forest-ingame');
      const { handleAppBack } = await import('/static/mobile/back-navigation.mjs');
      window.testBack = () => handleAppBack({ document, window, app: {}, canGoBack: true });
      window.testBack();
    });
    assert.equal(await page.locator('#forest-exit-confirm').evaluate(el => el.open), true);
    assert.equal(await page.locator('#forest-exit-title').textContent(), '서비스 홈 화면으로 나가시겠습니까?');
    await page.locator('#forest-exit-confirm [data-close]').click();
    assert.equal(await page.locator('#forest-exit-confirm').evaluate(el => el.open), false);
    await page.evaluate(() => window.testBack());
    await page.locator('#forest-exit-confirm [data-exit]').click();
    await page.waitForURL(url => url.pathname === '/');
    console.log(`PASS ${width}px: health actions/close, matching replay menu, full header, intro skip/replay, previous view, forest cancel/exit`);
    await page.close();
  }
} finally { await browser.close(); }
