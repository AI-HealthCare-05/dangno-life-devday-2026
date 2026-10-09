import assert from 'node:assert/strict';
import { chromium } from 'playwright';
import { mkdir } from 'node:fs/promises';

const browser = await chromium.launch({ headless: true, executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe' });
const origin = 'http://127.0.0.1:8000';
function inside(child, parent) {
  assert.ok(child.x >= parent.x - 1 && child.y >= parent.y - 1
    && child.x + child.width <= parent.x + parent.width + 1
    && child.y + child.height <= parent.y + parent.height + 1, `Text/control fits its container: ${JSON.stringify({ child, parent })}`);
}
try {
  await mkdir('outputs/mobile/analysis-xai', { recursive: true });
  for (const width of [390, 720, 1280]) {
    const page = await browser.newPage({ viewport: { width, height: 1256 } });
    await page.route('**/api/**', route => route.fulfill({ status: 401, contentType: 'application/json', body: '{}' }));
    await page.goto(`${origin}/static/index.html?preview=analysis-status&status=succeeded`);
    await page.waitForFunction(() => document.querySelector('.screen.active')?.dataset.step === '5');
    for (const status of ['queued', 'running', 'succeeded', 'failed']) {
      for (const large of [false, true]) {
        await page.evaluate(({ status, large }) => {
          document.body.classList.toggle('large-text', large);
          renderPredictionStatus(status, { resultAvailable: status === 'succeeded', showResult: false });
        }, { status, large });
        await page.locator('.screen.active').evaluate(async el => { await Promise.all(el.getAnimations().map(animation => animation.finished.catch(() => {}))); });
        const card = await page.locator('#prediction-status-card').boundingBox();
        const message = await page.locator('.prediction-status-message-card').boundingBox();
        const track = await page.locator('.prediction-status-track').boundingBox();
        inside(message, card); inside(track, card);
        assert.ok(track.y >= message.y + message.height + 8, 'Progress steps follow the message without overlap');
        for (const selector of ['#result-stage', '#result-explain', ...(status === 'failed' ? ['#retry-analysis'] : [])]) {
          inside(await page.locator(selector).boundingBox(), message);
        }
        assert.ok(card.x >= 0 && card.x + card.width <= width + 1);
        for (const item of await page.locator('.prediction-status-track li').all()) inside(await item.boundingBox(), track);
        await page.locator('#prediction-status-card').screenshot({ path: `outputs/mobile/analysis-xai/status-${width}-${status}${large ? '-large' : ''}.png`, animations: 'disabled' });
      }
    }
    await page.goto(`${origin}/static/index.html?preview=results`);
    await page.waitForFunction(() => document.querySelector('.screen.active')?.dataset.step === '6');
    await page.evaluate(() => {
      document.querySelector('#message').style.setProperty('display','none','important');
      const numeric = { status: 'available', model_score: .115, decision_threshold: .1, score_minus_threshold: .015 };
      const metadata = {result_status:'approved',promotion_status:'approved',display_allowed:true,output_status:'screening_not_diagnosis',raw_probability_exposed:false,model_analysis:numeric,input_as_of_date:'2026-10-01',model_version:'synthetic-test'};
      Object.assign(state.currentScreeningPrediction, metadata, {screening_signal_detected:true,risk_category:'high'});
      Object.assign(state.prediction, metadata, {risk_category:'low'});
      window.syntheticCurrentXai = {
        status: 'approved', display_allowed: true, shap_claimed: true,
        selection_status: 'insufficient_directional_factors', additivity_verified: true,
        baseline_label: '학습 자료의 대표 표본 기준 (2016–2020년)',
        shap_graph: {complete:true,reference_value:.1,explained_score:.115,contribution_sum:.015,items:[
          {feature:'alcohol_frequency',display_name:'최근 1년 음주',contribution:.02},
          {feature:'blood_pressure',display_name:'혈압',contribution:.01},
          {feature:'bmi',display_name:'BMI',contribution:-.015},
        ]},
        items: [
          { feature: 'alcohol_frequency', display_name: '최근 1년 음주', input_value_label: '최근 1년간 전혀 마시지 않음', direction: 'increase', contribution: .02 },
          { feature: 'blood_pressure', display_name: '혈압', input_value_label: '수축기 130 mmHg · 이완기 80 mmHg', direction: 'increase', contribution: .01 },
        ],
      };
      renderXaiExplanationLists(window.syntheticCurrentXai, { approved: true, currentFactors: window.syntheticCurrentXai, currentApproved: true });
    });
    assert.equal(await page.locator('#current-factor-list li').count(), 2);
    assert.equal(await page.locator('#current-factor-note').isVisible(), true);
    assert.equal(await page.locator('#current-factor-title').textContent(), '현재 위험 신호 설명');
    assert.match(await page.locator('#current-factor-baseline').textContent(), /대표 표본/);
    assert.match(await page.locator('#current-factor-list').textContent(), /입력: 최근 1년간 전혀 마시지 않음/);
    assert.doesNotMatch(await page.locator('#current-factor-list').textContent(), /주의 요인|긍정 요인/);
    assert.equal(await page.locator('#risk-confirm-label, #forecast-status-badge').count(), 0);
    assert.equal(await page.locator('#current-factor-list details, #factor-list details').count(), 0);
    for (const prefix of ['current','future']) {
      const graph = page.locator(`#${prefix}-shap-graph`);
      assert.equal(await graph.isVisible(), true);
      const shapDetails = graph.locator('.shap-details');
      const shapSummary = shapDetails.locator('summary');
      assert.equal(await shapDetails.getAttribute('open'), null);
      assert.equal(await graph.locator('.shap-rows').isVisible(), false);
      await shapSummary.click();
      assert.equal(await graph.locator('.shap-rows').isVisible(), true);
      await shapSummary.click();
      assert.equal(await graph.locator('.shap-rows').isVisible(), false);
      await shapSummary.click();
      assert.equal(await graph.locator('.shap-row').count(), 3);
      assert.match(await graph.textContent(), /SHAP 분석 결과/);
      assert.match(await graph.textContent(), /−0\.020000|−0\.015000|-0\.015000/);
      const graphBox = await graph.boundingBox();
      const cardBox = await graph.locator('..').boundingBox();
      inside(graphBox, cardBox);
      const lastFactor = page.locator(prefix === 'current' ? '#current-factor-list li' : '#factor-list li').last();
      const lastBox = await lastFactor.boundingBox();
      assert.ok(graphBox.y >= lastBox.y + lastBox.height);
      for (const row of await graph.locator('.shap-row').all()) inside(await row.boundingBox(), graphBox);
      const details = page.locator(`#${prefix}-model-details`);
      assert.equal(await details.isVisible(), true);
      assert.equal(await details.getAttribute('open'), null);
      await details.locator('summary').click();
      assert.match(await details.textContent(), /0\.115000/);
      assert.match(await details.textContent(), /0\.100000/);
      assert.match(await details.textContent(), /\+0\.015000/);
      inside(await details.boundingBox(), await details.locator('..').boundingBox());
      await details.locator('summary').click();
      await graph.screenshot({path:`outputs/mobile/analysis-xai/${prefix}-graph-${width}.png`,animations:'disabled'});
    }
    await page.locator('[aria-labelledby="current-factor-title"]').screenshot({ path: `outputs/mobile/analysis-xai/today-${width}.png`, animations: 'disabled' });
    await page.evaluate(() => renderXaiExplanationLists(window.syntheticCurrentXai, { approved: true, currentFactors: window.syntheticCurrentXai, currentApproved: true }));
    for (const prefix of ['current','future']) {
      assert.equal(await page.locator(`#${prefix}-shap-graph .shap-details`).getAttribute('open'), null);
      assert.equal(await page.locator(`#${prefix}-shap-graph .shap-rows`).isVisible(), false);
    }
    await page.evaluate(() => renderXaiExplanationLists(null, { currentFactors: { ...window.syntheticCurrentXai, display_allowed: false }, currentApproved: true }));
    assert.equal(await page.locator('#current-factor-note').isVisible(), false);
    assert.equal(await page.locator('#current-shap-graph').isVisible(), false);
    assert.equal(await page.locator('#future-shap-graph').isVisible(), false);
    assert.equal(await page.locator('[aria-labelledby="current-factor-title"]').evaluate(el => el.classList.contains('xai-ready')), false);
    await page.close();
    console.log(`PASS ${width}px: all analysis states/large text fit; two verified Today factors display; unapproved explanations stay hidden`);
  }
} finally { await browser.close(); }
