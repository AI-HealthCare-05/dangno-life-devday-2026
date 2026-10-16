const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { HealthInputRewards, knownAnswer, FIELD_IDS, HINT } = require('../../src/frontend/health-input-rewards.js');

function fixture() {
  const storage = new Map(), summaries = [];
  const host = { setTimeout, clearTimeout,
    localStorage: { getItem: key => storage.get(key), setItem: (key, value) => storage.set(key, value) } };
  const ui = new HealthInputRewards(host);
  ui.renderSummary = (value, error) => summaries.push({ value, error });
  const response = { user_id: 7, checkup_id: 2, earned_carrots: 100, checkup_reward_carrots: 100,
    carrots_per_field: 100, carrot_balance: 200, eligible_fields: ['waist_cm'],
    rewarded_fields: [{ key: 'waist_cm', label: '허리둘레', amount: 100 }] };
  const calls = [];
  const options = { ownerId: 7, checkupId: 2, inputId: 3, api: async (url, request) => {
    calls.push({ url, request }); return response;
  } };
  return { ui, storage, summaries, response, options, calls };
}

test('only known valid optional answers qualify, including zero and false', () => {
  for (const value of ['0', 'false', 'code_1']) assert.equal(knownAnswer({ value }), true);
  for (const value of ['', ' ', null, undefined, 'code_97']) assert.equal(knownAnswer({ value }), false);
  assert.equal(knownAnswer({ value: '999', type: 'number', validity: { valid: false } }), false);
  assert.equal(knownAnswer({ value: 'NaN', type: 'number' }), false);
});

test('first carrot click displays the exact requested notice once per account', () => {
  const f = fixture(); f.ui.setOwner(7);
  let shown = 0, focused = 0;
  f.ui.dialog = { showModal() { shown++; } };
  const field = { row: { classList: { add() {} } }, input: { focus() { focused++; } } };
  f.ui.activate(field); f.ui.activate(field);
  assert.equal(shown, 1); assert.equal(focused, 1);
  assert.equal(HINT, '더 많은 건강정보를 입력하고, 더 높은 예측 결과를 받아보세요. 당근의 숲에서 사용할 수 있는 당근 100개는 덤!');
  assert.deepEqual([...f.storage.values()], ['seen']);
  f.ui.setOwner(8); f.ui.activate(field);
  assert.equal(shown, 2);
});

test('concurrent and repeated analysis checks send one claim containing only saved record IDs', async () => {
  const f = fixture();
  const results = await Promise.all([f.ui.claim(f.options), f.ui.claim(f.options)]);
  await f.ui.claim(f.options);
  assert.equal(f.calls.length, 1);
  assert.equal(results[0].earned_carrots, 100);
  assert.deepEqual(JSON.parse(f.calls[0].request.body), { checkup_id: 2, current_screening_input_id: 3 });
  assert.equal(f.calls[0].url, '/health-input-rewards/claim');
  assert.ok(f.ui.claimed.has('waist_cm'));
});

test('failed reward lookup does not create coins, is retryable, and can confirm an already-committed receipt', async () => {
  const f = fixture(); let attempts = 0;
  const options = { ...f.options, api: async () => {
    if (++attempts === 1) throw new Error('response disconnected');
    return { ...f.response, earned_carrots: 0, rewarded_fields: [] };
  } };
  assert.equal(await f.ui.claim(options), null);
  assert.equal(f.ui.claimed.size, 0);
  const retried = await f.ui.claim(options);
  assert.equal(attempts, 2);
  assert.equal(retried.earned_carrots, 0);
  assert.equal(retried.checkup_reward_carrots, 100);
  assert.equal(retried.carrot_balance, 200);
});

test('late account and analysis responses cannot overwrite another reward view', async () => {
  for (const scenario of ['owner', 'analysis']) {
    const f = fixture(); let finish, current = true;
    const pending = f.ui.claim({ ...f.options, isCurrent: () => current,
      api: () => new Promise(resolve => { finish = resolve; }) });
    await Promise.resolve();
    if (scenario === 'owner') f.ui.setOwner(8); else current = false;
    finish(f.response); await pending;
    assert.equal(f.ui.claimed.size, 0);
    assert.ok(!f.summaries.some(item => item.value?.earned_carrots === 100));
  }
});

test('a native transport that ignores abort cannot hold up analysis indefinitely', async () => {
  const f = fixture(); let expire;
  f.ui.host.setTimeout = callback => { expire = callback; return 1; };
  f.ui.host.clearTimeout = () => {};
  const pending = f.ui.claim({ ...f.options, api: () => new Promise(() => {}) });
  await Promise.resolve(); expire();
  assert.equal(await pending, null);
  assert.equal(f.ui.claimed.size, 0);
  assert.ok(f.summaries.at(-1).error);
});

test('wrong-account and malformed receipts never announce rewards', async () => {
  for (const response of [{ user_id: 8 }, { earned_carrots: 99999 }, { checkup_id: 9 }]) {
    const f = fixture();
    const result = await f.ui.claim({ ...f.options, api: async () => ({ ...f.response, ...response }) });
    assert.equal(result, null); assert.equal(f.ui.claimed.size, 0);
  }
});

test('invalid or absent saved record IDs cannot issue a reward request', async () => {
  const f = fixture();
  for (const checkupId of [null, 0, -1, 'local-preview']) await f.ui.claim({ ...f.options, checkupId });
  assert.equal(f.calls.length, 0);
});

test('both pages load the shared widget, with no demo defaults in the three optional measurements', () => {
  for (const file of ['index.html', 'intro-retro.html']) {
    const html = fs.readFileSync(`src/frontend/${file}`, 'utf8');
    assert.match(html, /health-input-rewards\.js/);
    assert.match(html, /health-input-rewards\.css/);
    for (const id of ['waist', 'systolic', 'diastolic']) {
      const input = html.match(new RegExp(`<input id="${id}"[^>]*>`))[0];
      assert.doesNotMatch(input, /\bvalue=/);
      assert.doesNotMatch(input, /\brequired\b/);
    }
  }
  const html = fs.readFileSync('src/frontend/index.html', 'utf8');
  assert.equal(FIELD_IDS.length, 17);
  for (const id of FIELD_IDS) assert.match(html, new RegExp(`id="${id}"`));
});

for (const file of ['app.js', 'intro-retro-app.js']) {
  test(`${file} runs the reward check alongside both models without changing model arguments`, async () => {
    const source = fs.readFileSync(`src/frontend/${file}`, 'utf8');
    const nodes = {}, modelCalls = [], rewards = [];
    const state = { step: 5, token: 'synthetic', userProfile: { id: 7 }, checkupId: 2, currentScreeningInputId: 3,
      capabilities: { currentHealth: true }, currentHealthOnly: false };
    const context = vm.createContext({ state,
      $: key => nodes[key] ||= { hidden: true, disabled: false, textContent: '' },
      isLocalPreview: () => false, requireActiveHealthConsent: () => true, predictionFailureGuidance: {}, healthRecordAnalysisBlocked: () => false,
      window: { HealthInputRewards: { claim: async options => { rewards.push(options); return null; } } },
      requestPredictionModel: async key => { modelCalls.push(key); return { predictionId: 1, prediction: { display_allowed: false } }; },
      api: async () => ({ items: [] }), renderPredictionStatus() {}, renderPrediction() {}, renderTwoYearRiskForecast() {},
      renderCurrentHealthResult() {}, renderModelComparisonGuidance() {}, isPublicRiskDisplayAllowed: () => false,
      renderXaiExplanationLists() {}, openResultStepAfterSuccessfulAnalysis: async () => { state.step = 6; },
    });
    for (const name of ['analysisInputKey', 'renderPartialAnalysisNotice', 'runPrediction']) {
      vm.runInContext(source.match(new RegExp(`^(?:async )?function ${name}\\([^]*?^}`, 'm'))[0], context);
    }
    await context.runPrediction();
    assert.deepEqual(modelCalls, ['diabetes_current_screening', 'diabetes_incidence']);
    assert.equal(rewards.length, 1);
    assert.equal(rewards[0].checkupId, 2); assert.equal(rewards[0].inputId, 3);
    assert.equal(rewards[0].ownerId, 7); assert.equal(state.step, 6);
  });
}
