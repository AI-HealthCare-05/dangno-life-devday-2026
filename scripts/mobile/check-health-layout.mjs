import assert from 'node:assert/strict';
import { chromium } from 'playwright';
import { mkdir } from 'node:fs/promises';
const browser = await chromium.launch({ headless: true,
  executablePath: process.env.MOBILE_TEST_BROWSER || 'C:/Program Files/Google/Chrome/Application/chrome.exe' });
try {
  await mkdir('outputs/mobile/layout', { recursive: true });
  for (const width of [360, 390, 600, 820]) {
    const page = await browser.newPage({ viewport: { width, height: 844 } });
    await page.goto('http://127.0.0.1:8000/?auth=login');
    await page.waitForFunction(() => typeof showMessage === 'function');
    await page.evaluate(() => {
      document.body.className = '';
      document.querySelectorAll('.screen').forEach(el => { el.hidden = true; });
      const panel = document.querySelector('#health-review-panel');
      document.querySelectorAll('.health-input-panel').forEach(el => { el.hidden = true; });
      for (let el = panel; el && el !== document.body; el = el.parentElement) {
        el.hidden = false; el.style.display = 'block';
      }
      panel.querySelectorAll('dl').forEach(dl => {
        dl.innerHTML = '<div><dt>허리둘레</dt><dd>95 cm</dd></div><div><dt>최근 1년 음주 빈도</dt><dd>최근 1년간 전혀 마시지 않음</dd></div><div><dt>관절염·류머티즘</dt><dd>진단받지 않음</dd></div>';
      });
      showMessage('챌린지 기록을 완료했어요.', 'success');
    });
    const measurements = await page.evaluate(() => ({
      columns: getComputedStyle(document.querySelector('#review-health')).gridTemplateColumns.split(' ').length,
      cards: [...document.querySelectorAll('#health-review-panel dl div')].map(el => ({ width: el.clientWidth, overflow: el.scrollWidth > el.clientWidth })),
      notice: (() => { const el = document.querySelector('#message'); const r = el.getBoundingClientRect(); return !el.hidden && r.left >= 0 && r.right <= innerWidth && r.top >= 0 && r.bottom <= innerHeight && r.height <= 160; })(),
    }));
    assert.equal(measurements.columns, 1, `${width}: review columns`);
    assert.ok(measurements.cards.every(card => card.width >= 150 && !card.overflow), `${width}: readable cards`);
    assert.ok(measurements.notice, `${width}: visible completion notice`);
    await page.screenshot({ path: `outputs/mobile/layout/review-${width}.png`, fullPage: true });
    if (width === 390) {
      const saved = await page.evaluate(async () => {
        // Browser-only service stubs verify the real record button's success path.
        api = async () => ({});
        loadWeeklyReport = async () => {};
        allDailyChallengesCompleted = () => false;
        state.dailyCompleted = new Set();
        state.recordTarget = { id: 'layout-test-record', item: { title: '테스트 챌린지', domain: 'activity' } };
        document.querySelector('#confirm-simple-record').click();
        await new Promise(resolve => setTimeout(resolve, 700));
        const box = document.querySelector('#message');
        return { completed: state.dailyCompleted.has('layout-test-record'),
          visible: !box.hidden && box.dataset.kind === 'success', text: box.textContent };
      });
      assert.ok(saved.completed && saved.visible);
      assert.match(saved.text, /기록/);
      console.log('PASS challenge record button: successful save shows completion notice');
    }
    await page.close();
    console.log(`PASS ${width}px: readable review cards and visible saved notice`);
  }
} finally { await browser.close(); }
