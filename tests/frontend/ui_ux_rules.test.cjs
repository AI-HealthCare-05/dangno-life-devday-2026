const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../../src/frontend/app.js'), 'utf8');
function load(name, data = {}) {
  const context = vm.createContext(data);
  const fn = source.match(new RegExp(`^(?:async )?function ${name}\\([^]*?^}`, 'm'));
  assert.ok(fn);
  vm.runInContext(fn[0], context);
  return context[name];
}
function loadMany(names, data = {}) {
  const context = vm.createContext(data);
  for (const name of names) {
    const fn = source.match(new RegExp(`^(?:async )?function ${name}\\([^]*?^}`, 'm'));
    assert.ok(fn, name);
    vm.runInContext(fn[0], context);
  }
  return context;
}
test('pending future result shows only the gauge and clears a previous risk marker', () => {
  const element = () => ({ dataset: {}, children: [], setAttribute() {}, append(...children) { this.children.push(...children); }, replaceChildren() { this.children = []; } });
  const elements = new Map();
  const context = loadMany(['normalizeForecastSignal', 'forecastSignalLabel', 'selectTwoYearForecastPoint', 'renderTwoYearRiskForecast'], {
    $: id => { if (!elements.has(id)) elements.set(id, element()); return elements.get(id); },
    document: { createElement: element },
    isDemoEnvironment: () => true,
  });
  context.renderTwoYearRiskForecast({}, { canDisplayRisk: true, fallbackLevel: 'moderate' });
  assert.equal(elements.get('#future-risk-points').children[0].children[0].textContent, '주의');
  context.renderTwoYearRiskForecast({}, { canDisplayRisk: false, fallbackLevel: 'moderate' });
  const pending = elements.get('#future-risk-points').children[0].children;
  assert.equal(pending.length, 2);
  assert.equal(pending[0].dataset.level, 'pending');
  assert.equal(pending[0].children.length, 0);
  assert.equal(elements.get('#future-risk-visual').hidden, false);
  assert.equal(elements.has('#forecast-status-badge'), false);
});
test('medical continuation requires challenge permission and preserves every safety exclusion', () => {
  const state = { capabilities: { challenge: true }, eligibility: { reason_codes: [] }, medicalGuidanceRequired: false };
  const allowed = load('canContinueAfterMedicalGuidance', { state });
  assert.equal(allowed(), true);
  for (const code of ['URGENT_MEDICAL_ATTENTION', 'SAME_DAY_MEDICAL_ATTENTION', 'DIAGNOSED_DIABETES', 'UNDER_MINIMUM_SERVICE_AGE', 'CONSENT_REQUIRED']) {
    state.eligibility.reason_codes = [code];
    assert.equal(allowed(), false, code);
  }
  state.eligibility.reason_codes = [];
  state.capabilities.challenge = false;
  assert.equal(allowed(), false);
  state.capabilities.challenge = true;
  state.medicalGuidanceRequired = true;
  assert.equal(allowed(), false);
});
test('profile writes use the canonical current backend path', () => {
  const writes = [...source.matchAll(/api\("([^"\n]+)", \{ method: "PATCH"/g)]
    .map(match => match[1]).filter(route => route.startsWith('/users/me'));
  assert.equal(writes.length, 3);
  assert.ok(writes.every(route => route === '/users/me'));
});
test('current-only allowed user reanalyses, medically restricted user does not', () => {
  const state = { currentHealthOnly: true, capabilities: { currentHealth: true }, medicalGuidanceRequired: false };
  const run = load('shouldRunPredictionAfterHealthEdit', { state });
  assert.equal(run(), true);
  state.medicalGuidanceRequired = true;
  assert.equal(run(), false);
  state.medicalGuidanceRequired = false;
  state.capabilities.currentHealth = false;
  assert.equal(run(), false);
});
test('missing or incomplete forecast stays hidden without throwing', () => {
  const allowed = load('forecastCurveDisplayAllowed');
  for (const forecast of [null, undefined, {}, { public_display_approved: true, risk_curve_status: 'available', points: [] }]) {
    assert.equal(allowed(forecast, true), false);
  }
});
test('error navigation follows field DOM instead of outdated field-name lists', () => {
  let panel, focused = false;
  const focus = load('focusHealthField', {
    document: { getElementById: () => ({ closest: () => ({ id: 'health-activity-panel' }), focus: () => { focused = true; } }) },
    showHealthInputPanel: value => { panel = value; },
  });
  focus('walking-days');
  assert.equal(panel, 'activity');
  assert.equal(focused, true);
});
test('missing snapshot endpoint is explicit and cannot reuse stale snapshot ID', async () => {
  const state = { checkupId: 3, currentScreeningInputId: 99 };
  const save = load('saveCurrentScreeningInputSnapshot', {
    state, detailHealthPayload: () => ({}), isLocalPreview: () => false,
    api: async () => { throw { status: 404 }; },
  });
  await save();
  assert.equal(state.currentScreeningInputSaveUnavailable, true);
  assert.equal(state.currentScreeningInputId, null);
});
test('snapshot contract mismatch remains non-blocking for reanalysis', async () => {
  const state = { checkupId: 3, currentScreeningInputId: 99 };
  const save = load('saveCurrentScreeningInputSnapshot', {
    state, detailHealthPayload: () => ({}), isLocalPreview: () => false,
    api: async () => { throw { status: 422 }; },
  });
  await save();
  assert.equal(state.currentScreeningInputSaveUnavailable, true);
  assert.equal(state.currentScreeningInputId, null);
});
test('XAI explanation cards show only approved returned factors with safe labels', () => {
  const nodes = {
    '#current-factor-list': { innerHTML: '' },
    '#factor-list': { innerHTML: '' },
    '#current-factor-title': { textContent: '' },
    '#future-factor-title': { textContent: '' },
  };
  for (const id of ['#current-factor-list', '#factor-list']) {
    nodes[id].closest = () => ({ classList: { toggle: (name, ready) => { nodes[id].ready = ready; } } });
  }
  const state = { currentScreeningPrediction: { screening_signal_detected: false }, prediction: { risk_category: 'low' } };
  const context = loadMany(['normalizeRiskKey', 'factorDirectionLabel', 'factorModifiableLabel', 'factorIdentity', 'renderFactorItems', 'selectXaiFactors', 'formatModelNumber', 'renderModelAnalysisDetails', 'renderShapGraph', 'renderXaiExplanationLists'], {
    state,
    $: selector => nodes[selector] || null,
    escapeHtml: value => String(value).replace(/[&<>'"]/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[character]),
  });
  const render = context.renderXaiExplanationLists;
  const approvedFactors = { status: 'approved', shap_claimed: true, display_allowed: true, items: [{ display_name: '걷기 시간', input_value_label: '20분 <확인>', contribution: -.01, direction: 'decrease', modifiable: true, message: '당뇨 위험을 낮춘 방향입니다.' }] };
  render(approvedFactors, { approved: true, currentFactors: approvedFactors, currentApproved: true });
  assert.match(nodes['#current-factor-list'].innerHTML, /걷기 시간/);
  assert.equal(nodes['#current-factor-title'].textContent, '현재 위험 신호 설명');
  assert.equal(nodes['#future-factor-title'].textContent, '미래 당뇨 위험 설명');
  assert.equal(nodes['#factor-list'].ready, true);
  assert.match(nodes['#factor-list'].innerHTML, /걷기 시간/);
  assert.match(nodes['#factor-list'].innerHTML, /입력: 20분 &lt;확인&gt;/);
  assert.doesNotMatch(nodes['#factor-list'].innerHTML, /<details|SHAP 기여도 상세보기/);
  assert.doesNotMatch(nodes['#factor-list'].innerHTML, /당뇨 위험을 낮춘 방향|<details[^>]* open/);
  assert.match(nodes['#factor-list'].innerHTML, /class="xai-factor-direction is-positive">점수를 낮춘 요인<\/span>/);
  assert.doesNotMatch(nodes['#factor-list'].innerHTML, /(?:참고 요인|바꿀 수 있는 요인|xai-factor-modifier)/);
  assert.doesNotMatch(nodes['#factor-list'].innerHTML, /[↑↓] (?:주의|긍정) 요인/);
  render({ ...approvedFactors, display_allowed: false }, { approved: true });
  assert.doesNotMatch(nodes['#factor-list'].innerHTML, /걷기 시간/);
  render({ items: [{ display_name: '임의 표시 금지' }] }, { approved: false });
  assert.doesNotMatch(nodes['#factor-list'].innerHTML, /임의 표시 금지/);
  assert.match(nodes['#factor-list'].innerHTML, /미래 위험 XAI 연결 대기/);
  assert.equal(nodes['#future-factor-title'].textContent, '미래 위험 XAI 연결 대기');
  assert.equal(nodes['#current-factor-title'].textContent, '현재 건강 신호 XAI 연결 대기');
  assert.equal(nodes['#factor-list'].ready, false);
});
test('XAI preserves opposite directions across models with different references', () => {
  const nodes = {
    '#current-factor-list': { innerHTML: '', closest: () => ({ classList: { toggle() {} } }) },
    '#factor-list': { innerHTML: '', closest: () => ({ classList: { toggle() {} } }) },
    '#current-factor-title': { textContent: '' },
    '#future-factor-title': { textContent: '' },
  };
  const state = { currentScreeningPrediction: { screening_signal_detected: true }, prediction: { risk_category: 'high' } };
  const context = loadMany(['normalizeRiskKey', 'factorDirectionLabel', 'factorModifiableLabel', 'factorIdentity', 'renderFactorItems', 'selectXaiFactors', 'formatModelNumber', 'renderModelAnalysisDetails', 'renderShapGraph', 'renderXaiExplanationLists'], {
    state,
    $: selector => nodes[selector] || null,
    escapeHtml: value => String(value),
  });
  const current = { display_allowed: true, items: [
    { display_name: 'BMI', direction: 'increase', contribution: .5 },
    { display_name: '혈압', direction: 'increase', contribution: .4 },
    { display_name: '운동', direction: 'decrease', contribution: -.3 },
  ] };
  const future = { display_allowed: true, items: [
    { display_name: 'BMI', direction: 'decrease', contribution: -.8 },
    { display_name: '연령', direction: 'increase', contribution: .6 },
    { display_name: '가구소득', direction: 'increase', contribution: .4 },
    { display_name: '운동시간', direction: 'decrease', contribution: -.2 },
  ] };
  context.renderXaiExplanationLists(future, { approved: true, currentFactors: current, currentApproved: true });
  assert.match(nodes['#factor-list'].innerHTML, />BMI</);
  assert.match(nodes['#factor-list'].innerHTML, />연령</);
  assert.match(nodes['#factor-list'].innerHTML, />가구소득</);
  assert.doesNotMatch(nodes['#factor-list'].innerHTML, />운동시간</);
});
test('XAI picks directional 2+1 without padding and hides unknown result states', () => {
  const context = loadMany(['factorDirectionLabel', 'selectXaiFactors']);
  const items = [-0.1, 0.4, -0.3, 0.2, 0, NaN].map((value, index) => ({
    feature: String(index), contribution: value, direction: value > 0 ? 'increase' : 'decrease',
  }));
  const select = context.selectXaiFactors;
  assert.deepEqual(Array.from(select(items, false), i => i.contribution), [-0.3, -0.1, 0.4]);
  assert.deepEqual(Array.from(select(items, true), i => i.contribution), [0.4, 0.2, -0.3]);
  assert.equal(select(items, null).length, 0);
  assert.equal(select(items.filter(i => i.contribution > 0), false).length, 1);
});
test('model conflict guidance prioritizes current signal and never treats failure as low risk', () => {
  const context = loadMany(['normalizeRiskKey', 'isPublicRiskDisplayAllowed', 'modelComparisonGuidance']);
  const approved = risk => ({
    risk_category: risk,
    result_status: 'approved',
    promotion_status: 'approved',
    display_allowed: true,
  });
  const current = { status: 'succeeded', prediction: approved('high') };
  const future = { status: 'succeeded', prediction: approved('low') };
  assert.equal(context.modelComparisonGuidance(current, future).code, 'CURRENT_SIGNAL_FUTURE_LOW');
  assert.match(context.modelComparisonGuidance(current, future).message, /현재 신호 확인을 우선/);
  const futureElevated = { status: 'succeeded', prediction: approved('moderate') };
  const currentLow = { status: 'succeeded', prediction: approved('low') };
  assert.equal(context.modelComparisonGuidance(currentLow, futureElevated).code, 'CURRENT_LOW_FUTURE_ELEVATED');
  assert.match(context.modelComparisonGuidance(currentLow, futureElevated).message, /정기 검사와 생활습관 점검/);
  const incomplete = context.modelComparisonGuidance(current, { status: 'failed' });
  assert.equal(incomplete.code, 'MODEL_RESULT_INCOMPLETE');
  assert.match(incomplete.message, /완료하지 못한 분석은 다시 시도/);
  assert.doesNotMatch(incomplete.message, /위험 (?:높음|낮음)|위험도/);
});

test('unapproved model outputs cannot create a public conflict explanation', () => {
  const context = loadMany(['normalizeRiskKey', 'isPublicRiskDisplayAllowed', 'modelComparisonGuidance']);
  const research = { status: 'succeeded', prediction: { risk_category: 'high', display_allowed: false } };
  const result = context.modelComparisonGuidance(research, research);
  assert.equal(result.code, 'MODEL_RESULT_NOT_PUBLIC');
  assert.equal(result.display, false);
});


test('missing or unapproved prediction clears numerical details without leaking cached values', () => {
  const nodes = {'#current-model-details': {hidden:false,open:true}, '#current-model-numbers':{innerHTML:'old numbers'}};
  const context = loadMany(['formatModelNumber','renderModelAnalysisDetails'], {
    $: key => nodes[key], escapeHtml: String,
    isPublicRiskDisplayAllowed: value => value.result_status === 'approved',
  });
  context.renderModelAnalysisDetails('current', null);
  assert.equal(nodes['#current-model-details'].hidden, true);
  assert.equal(nodes['#current-model-details'].open, false);
  assert.equal(nodes['#current-model-numbers'].innerHTML, '');
  context.renderModelAnalysisDetails('current', {result_status:'development_only',model_analysis:{status:'available',model_score:.2,decision_threshold:.1,score_minus_threshold:.1}});
  assert.equal(nodes['#current-model-details'].hidden, true);
});
