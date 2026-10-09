const assert = require('node:assert/strict');
const { mkdirSync } = require('node:fs');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.QA_BASE_URL || 'http://127.0.0.1:8022';
assert.ok(['localhost', '127.0.0.1'].includes(new URL(base).hostname));
(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROME_BIN });
  mkdirSync('tmp/challenge-flow-qa', { recursive: true });
  try {
    for (const width of [1440, 380]) {
      const page = await browser.newPage({ viewport: { width, height: 950 } });
      const errors = [];
      page.on('pageerror', e => errors.push(e.message));
      await page.goto(base, {waitUntil:'domcontentloaded'});
      await page.evaluate(() => {
        state.token = 'local-demo-token'; state.capabilities.challenge = true; state.healthConsentStatus = 'active';
        state.cycle = null; renderDailyRecordList(); renderTodayTaskStatus();
        showWorkspace('home', { moveFocus: false }); showStep(8);
      });
      await page.locator('#today-record-action').click();
      assert.equal(await page.locator('.daily-record-empty strong').innerText(), '기록할 챌린지가 없습니다');
      assert.ok(await page.locator('#challenge-form').isHidden());
      assert.ok(await page.locator('#daily-record-title').isHidden());
      assert.ok(await page.locator('#barrier-form').isHidden());
      await page.evaluate(async () => { await Promise.all(document.getAnimations().map(a => a.finished.catch(() => {}))); window.scrollTo({top:0,behavior:"instant"}); });
      await page.screenshot({path:`tmp/challenge-flow-qa/empty-${width}.png`,fullPage:true});
      await page.locator('.daily-record-select').focus();
      await page.keyboard.press('Enter');
      await page.waitForFunction(() => state.step === 7);
      assert.ok(await page.locator('#challenge-form').isVisible());
      await page.waitForSelector('.challenge-v3-card');
      assert.equal(await page.locator('.challenge-v3-card').count(), 3);
      await page.locator('#challenge-v3-focus').selectOption('diet');
      await page.waitForFunction(() => !challengeV3.busy && challengeV3.focus === 'diet');
      await page.locator('#challenge-v3-difficulty').selectOption('moderate');
      await page.waitForFunction(() => !challengeV3.busy && challengeV3.difficulty === 'moderate');
      assert.ok((await page.locator('[data-v3-domain="fiber_diet"]').innerText()).includes('2끼'));
      assert.ok((await page.locator('[data-v3-domain="aerobic_activity"]').innerText()).includes('10분'));
      await page.locator('#challenge-v3-refresh').click();
      await page.waitForFunction(() => !challengeV3.busy);
      await page.evaluate(() => window.scrollTo({top:0,behavior:"instant"}));
      await page.screenshot({path:`tmp/challenge-flow-qa/selection-v3-${width}.png`,fullPage:true});
      await page.locator('#start-challenge').click();
      await page.waitForFunction(() => state.step === 8 && state.activeWorkspace === 'challenge');
      assert.equal(await page.locator('.daily-record-card').count(), 3);
      assert.equal(await page.locator('button.daily-record-card').count(), 3);
      const recordBoxes = await Promise.all((await page.locator('.daily-record-card').all()).map(card => card.boundingBox()));
      for (let i = 1; i < recordBoxes.length; i++) {
        assert.ok(recordBoxes[i].y >= recordBoxes[i - 1].y + recordBoxes[i - 1].height, 'Recording items stack vertically');
        assert.ok(Math.abs(recordBoxes[i].width - recordBoxes[0].width) < 1, 'Recording items use the same full width');
      }
      assert.equal(await page.locator('.daily-record-card button').count(), 0);
      assert.equal(await page.locator('.daily-record-card:not(:disabled) .record-type-badge').count(), 0);
      assert.equal(await page.locator('#daily-log-list [data-lifestyle-topic]').count(), 0);
      assert.ok(await page.locator('#daily-record-title').isVisible());
      assert.ok(await page.locator('#barrier-form').isVisible());
      assert.equal(await page.locator('[data-top-step="7"]').getAttribute('aria-current'),'page');
      assert.equal(await page.getByText('선택이 완료되었습니다',{exact:true}).count(),0);
      await page.evaluate(async () => { await Promise.all(document.getAnimations().map(a => a.finished.catch(() => {}))); window.scrollTo({top:0,behavior:"instant"}); });
      await page.screenshot({path:`tmp/challenge-flow-qa/active-${width}.png`,fullPage:true});
      // Re-entering the challenge tab preserves the recording page and completed state.
      await page.locator('.daily-record-card').first().press('Enter');
      assert.ok(await page.locator('#record-modal').isVisible());
      assert.equal(await page.locator('#record-simple-visual').getAttribute('data-kind'), 'water');
      await page.locator('#confirm-simple-record').click();
      await page.waitForFunction(() => state.dailyCompleted.size === 1);
      await page.evaluate(() => showWorkspace('home'));
      await page.locator('[data-top-step="7"]').click();
      await page.waitForFunction(() => state.step === 8 && state.activeWorkspace === 'challenge');
      assert.ok(await page.locator('.daily-record-open').first().isEnabled());
      await page.locator('.daily-record-card').first().click();
      assert.equal(await page.locator('#confirm-simple-record').innerText(), '확인');
      assert.ok(await page.locator('#record-simple-panel .record-cancel').isHidden());
      await page.locator('#confirm-simple-record').click();
      assert.ok(await page.locator('#record-modal').isHidden());
      assert.equal(await page.locator('#challenge-form').isVisible(),false);
      await page.locator('.daily-record-card').first().click();
      assert.ok(await page.locator('#undo-daily-record').isVisible());
      await page.screenshot({path:`tmp/challenge-flow-qa/undo-${width}.png`,fullPage:true});
      await page.locator('#undo-daily-record').click();
      await page.waitForFunction(() => state.dailyCompleted.size === 0);
      assert.ok(await page.locator('#record-modal').isHidden());
      assert.equal(await page.locator('.daily-record-card.done').count(),0);
      await page.locator('.daily-record-card').first().click();
      assert.ok(await page.locator('#undo-daily-record').isHidden());
      await page.locator('#confirm-simple-record').click();
      await page.waitForFunction(() => state.dailyCompleted.size === 1);
      await page.waitForSelector('#record-modal', {state:'hidden'});

      await page.locator('.daily-record-card[data-record-type="photo"]').first().click();
      assert.ok(await page.locator('#v3-photo-fields').isVisible());
      assert.equal(await page.locator('.record-fallback:visible').count(), 0);
      assert.equal(await page.locator('.record-modal-card').evaluate(el => el.scrollWidth > el.clientWidth + 1), false, 'photo fields must fit inside the modal');
      await page.screenshot({path:`tmp/challenge-flow-qa/photo-v3-${width}.png`,fullPage:true});
      await page.locator('#confirm-photo-record').click();
      assert.equal(await page.locator('#photo-state-success').isVisible(), false);
      await page.locator('.record-modal-close').click();
      // Finished/cancelled cycles must never become today's record targets.
      for (const status of ['completed','cancelled']) {
        await page.evaluate(status => { state.cycle.status=status; showWorkspace('home'); }, status);
        await page.locator('#today-record-action').click();
        assert.ok(await page.locator('.daily-record-select').isVisible());
        assert.equal(await page.locator('.daily-record-card').count(),0);
      }
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth+1), false);
      assert.deepEqual(errors,[]);
      console.log(`PASS ${width}px: empty → choose → start → record, tab re-entry, completed/cancelled cycles, keyboard, no overflow/errors`);
      await page.close();
    }
    const page = await browser.newPage();
    await page.goto(base, {waitUntil:'domcontentloaded'});
    // API recovery and daily log loading are covered without writing any server data.
    await page.route('**/api/v1/challenge-cycles/current', r => r.fulfill({json:{cycle_number:1,status:'active',user_challenges:[{user_challenge_id:7,title:'가볍게 걷기'}]}}));
    await page.route('**/api/v1/user-challenges/7/logs?*', r => r.fulfill({json:{items:[{log_date:new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Seoul'}).format(new Date()),is_completed:true}]}}));
    await page.evaluate(async () => { state.token='qa-mock-token'; state.healthConsentStatus='active'; state.cycle=null; await openChallengeTab(); });
    assert.ok(await page.locator('.daily-record-open').first().isEnabled());
      await page.locator('.daily-record-card').first().click();
      assert.equal(await page.locator('#confirm-simple-record').innerText(), '확인');
      assert.ok(await page.locator('#record-simple-panel .record-cancel').isHidden());
      await page.locator('#confirm-simple-record').click();
      assert.ok(await page.locator('#record-modal').isHidden());
    await page.route('**/api/v1/challenge-cycles/current', r => r.fulfill({status:503,json:{detail:'일시적인 서버 오류'}}));
    const result = await page.evaluate(async () => {state.cycle=null; try {await openChallengeTab(); return 'unexpected';} catch {return 'error';}});
    assert.equal(result,'error');
    console.log('PASS mocked API: current cycle recovery, saved daily record, server error is not treated as no challenge');
    await page.close();
  } finally {await browser.close();}
})().catch(e => {console.error(e);process.exitCode=1;});
