const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../../src/frontend/app.js'), 'utf8');
const CURRENT = 'diabetes_current_screening';
const FUTURE = 'diabetes_incidence';
function harness() {
  const nodes = {};
  const $ = key => nodes[key] ||= { hidden: true, disabled: false, textContent: '' };
  const state = { step: 5, token: 'test-session', checkupId: 1, capabilities: { currentHealth: true }, currentHealthOnly: false };
  const calls = [];
  const failures = new Set();
  let factorFailure = false;
  const context = vm.createContext({
    state, $, isLocalPreview: () => false, requireActiveHealthConsent: () => true, predictionFailureGuidance: {}, healthRecordAnalysisBlocked: () => false,
    requestPredictionModel: async key => {
      calls.push(key);
      if (failures.has(key)) throw Object.assign(new Error('unavailable'), { code: 'MODEL_UNAVAILABLE' });
      return { predictionId: key === CURRENT ? 10 : 20, prediction: { model_key: key, display_allowed: false } };
    },
    api: async url => { calls.push(url); if (factorFailure) throw new Error('503'); return { items: [] }; },
    renderPredictionStatus: status => { state.status = status; },
    renderPrediction: prediction => { state.renderedFuture = prediction; },
    renderTwoYearRiskForecast: () => {},
    renderCurrentHealthResult: prediction => { state.renderedCurrent = prediction; },
    renderModelComparisonGuidance: () => {},
    isPublicRiskDisplayAllowed: () => false,
    renderXaiExplanationLists: () => {},
    openResultStepAfterSuccessfulAnalysis: async guard => { if (!guard || guard()) state.step = 6; },
  });
  for (const name of ['analysisInputKey', 'renderPartialAnalysisNotice', 'runPrediction']) {
    const match = source.match(new RegExp(`^(?:async )?function ${name}\\([^]*?^}`, 'm'));
    assert.ok(match, name);
    vm.runInContext(match[0], context);
  }
  return { state, $, context, calls, failures, run: context.runPrediction, setFactorFailure: value => { factorFailure = value; } };
}
for (const failed of [CURRENT, FUTURE]) {
  test(`partial failure ${failed} preserves success and retries only the failed model`, async () => {
    const h = harness();
    h.failures.add(failed);
    await h.run();
    assert.equal(h.state.step, 6);
    assert.equal(h.$('#partial-analysis-notice').hidden, false);
    assert.match(h.$('#partial-analysis-message').textContent, /잠시 후 다시 시도해 주세요/);
    assert.doesNotMatch(h.$('#partial-analysis-message').textContent, /위험 (?:높음|낮음)|위험도/);
    const successful = failed === CURRENT ? h.state.prediction : h.state.currentScreeningPrediction;
    assert.ok(successful);
    assert.equal(successful.display_allowed, false);
    if (failed === FUTURE) {
      assert.equal(h.state.predictionId, null);
      assert.equal(h.state.renderedFuture.display_allowed, false);
    }
    h.failures.clear();
    h.calls.length = 0;
    await h.run({ retryFailed: true });
    assert.deepEqual(h.calls.filter(call => !call.startsWith('/')), [failed]);
    assert.equal(failed === CURRENT ? h.state.prediction : h.state.currentScreeningPrediction, successful);
    assert.equal(h.$('#partial-analysis-notice').hidden, true);
  });
}
test('both failures remain on status screen; retry uses the same inputs', async () => {
  const h = harness();
  h.failures.add(CURRENT).add(FUTURE);
  await h.run();
  assert.equal(h.state.step, 5);
  assert.equal(h.$('#retry-analysis').hidden, false);
  assert.equal(h.state.prediction, null);
  h.failures.clear();
  await h.run({ retryFailed: true });
  assert.equal(h.state.step, 6);
  assert.equal(h.state.checkupId, 1);
});
test('current-only flow does not request future prediction', async () => {
  const h = harness();
  h.state.currentHealthOnly = true;
  await h.run();
  assert.deepEqual(h.calls, [CURRENT, '/predictions/10/risk-factors']);
  assert.equal(h.state.step, 6);
});
test('explanation failure preserves models; retry only fetches explanations', async () => {
  const h = harness();
  h.setFactorFailure(true);
  await h.run();
  assert.equal(h.state.step, 6);
  assert.ok(h.state.prediction);
  assert.match(h.$('#partial-analysis-message').textContent, /확인된 결과는 유지되지만 설명 요인을 불러오지 못했어요/);
  h.calls.length = 0;
  h.setFactorFailure(false);
  await h.run({ retryFailed: true });
  assert.deepEqual(h.calls.sort(), ['/predictions/10/risk-factors', '/predictions/20/risk-factors']);
  assert.equal(h.$('#partial-analysis-notice').hidden, true);
});
test('changed checkup invalidates cached success, even with retry requested', async () => {
  const h = harness();
  await h.run();
  h.calls.length = 0;
  h.state.checkupId = 2;
  h.failures.add(CURRENT).add(FUTURE);
  h.state.step = 5;
  await h.run({ retryFailed: true });
  assert.deepEqual(h.calls, [CURRENT, FUTURE]);
  assert.equal(h.state.currentScreeningPrediction, null);
  assert.equal(h.state.prediction, null);
  assert.equal(h.state.step, 5);
});
test('duplicate clicks do not start duplicate requests; stale session cannot commit', async () => {
  const h = harness();
  const resolvers = {};
  let count = 0;
  // 오늘이·내일이는 이제 병렬로 요청되므로(runPrediction의 Promise.all), 모델별로
  // 독립된 resolve를 잡아둔다. count는 "한 번의 run() 호출"당 모델 수(2)만큼
  // 올라가는 게 정상이고, 여기서 확인하려는 건 두 번째(중복) run() 호출이
  // 추가 요청을 만들지 않는지다.
  h.context.requestPredictionModel = key => {
    count++;
    return new Promise(done => { resolvers[key] = done; });
  };
  const pending = h.run();
  await h.run();
  assert.equal(count, 2);
  h.state.token = 'another-test-session';
  resolvers[CURRENT]({ predictionId: 10, prediction: { model_key: CURRENT } });
  resolvers[FUTURE]({ predictionId: 20, prediction: { model_key: FUTURE } });
  await pending;
  assert.equal(h.state.currentScreeningPrediction, undefined);
  assert.equal(h.state.step, 5);
});
