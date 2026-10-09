import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
import { chromium } from 'playwright';

const browser = await chromium.launch({headless: true, executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe'});
await mkdir('outputs/mobile/vlm-photo-flow', {recursive: true});
try {
  for (const width of [390, 720, 1280]) {
    const page = await browser.newPage({viewport: {width, height: 1000}});
    await page.route('**/api/**', route => route.fulfill({status: 200, contentType: 'application/json', body: '{}'}));
    await page.goto('http://127.0.0.1:8000/static/index.html?preview=meal-photo');
    await page.waitForFunction(() => typeof state !== 'undefined' && state.recordTarget?.item?.verification_type === 1);
    for (const id of ['contains-kimchi', 'strong-seasoning', 'white-food-on-white']) {
      assert.equal(await page.locator(`#v3-photo-${id}`).inputValue(), 'unsure');
    }
    await page.locator('#v3-photo-contains-kimchi').selectOption('yes');
    await page.locator('#v3-photo-strong-seasoning').selectOption('no');
    await page.locator('#v3-photo-white-food-on-white').selectOption('yes');
    const bounds = await page.locator('.v3-photo-context').evaluate(el => {
      const box = el.getBoundingClientRect();
      return {left: box.left, right: box.right, width: document.documentElement.clientWidth, overflow: el.scrollWidth > el.clientWidth};
    });
    assert.ok(bounds.left >= 0 && bounds.right <= bounds.width + 1 && !bounds.overflow);
    await page.locator('.v3-photo-context').screenshot({path: `outputs/mobile/vlm-photo-flow/controls-${width}.png`});
    await page.locator('[data-demo-name="demo-pass.png"]').click();
    await page.waitForFunction(() => document.getElementById('v3-photo-file').files.length === 1);
    await page.locator('input[name="v3-photo-value"][value="1"]').evaluate(el => el.closest('label').click());
    await page.evaluate(() => {
      state.token = 'synthetic-ui-session';
      window.submittedPhotoHints = null;
      api = async (_url, options) => {
        window.submittedPhotoHints = Object.fromEntries(['contains_kimchi', 'strong_seasoning', 'white_food_on_white'].map(name => [name, options.body.get(name)]));
        return {review_status: 'needs_review', challenge_completed: false, notice: '경계가 불명확해 다시 촬영해 주세요.'};
      };
    });
    await page.locator('#confirm-photo-record').click();
    await page.waitForFunction(() => !document.getElementById('photo-state-pending').hidden);
    assert.deepEqual(await page.evaluate(() => window.submittedPhotoHints), {contains_kimchi: 'yes', strong_seasoning: 'no', white_food_on_white: 'yes'});
    assert.equal(await page.evaluate(() => state.dailyCompleted.size), 0);
    await page.evaluate(() => {
      const item = {...state.recordTarget.item, user_challenge_id: 'synthetic-walk', verification_type: 2, goal: {target_minutes: 20}};
      openPhotoRecordModal(item);
    });
    assert.equal(await page.locator('.v3-photo-context').isVisible(), false);
    await page.close();
    console.log('PASS photo conditions and pending state', width);
  }
} finally {
  await browser.close();
}
