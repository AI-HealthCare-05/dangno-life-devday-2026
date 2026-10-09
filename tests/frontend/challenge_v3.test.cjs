const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../../src/frontend/app.js'), 'utf8');
function load(names, data) {
  const context = vm.createContext(data);
  for (const name of names) {
    const fn = source.match(new RegExp(`^(?:async )?function ${name}\\([^]*?^}`, 'm'));
    assert.ok(fn, name);
    vm.runInContext(fn[0], context);
  }
  return context;
}
test('preview keeps three domains and bounded non-preferred difficulty without fake AI proof', () => {
  const catalog = ['v3_hydration_choice', ...['easy', 'moderate', 'advanced'].flatMap(level =>
    ['wholegrain', 'walk', 'indoor_aerobic'].map(kind => `v3_${kind}_${level}`))].map(code => ({ code }));
  const context = load(['previewV3Recommendations'], {});
  for (const [focus, expected] of [['diet', ['advanced', 'moderate']], ['activity', ['moderate', 'advanced']], ['balanced', ['advanced', 'advanced']]]) {
    for (let rotation = 0; rotation < 8; rotation++) {
      const result = context.previewV3Recommendations(catalog, focus, 'advanced', rotation);
      assert.equal(result.items.length, 3);
      assert.equal(result.items[0].code, 'v3_hydration_choice');
      assert.ok(result.items[1].code.endsWith(expected[0]));
      assert.ok(result.items[2].code.endsWith(expected[1]));
      assert.equal(result.photo_review_available, false);
    }
  }
});
function recommendationHarness(api) {
  const nodes = {};
  const $ = key => nodes[key] ||= { value: key.includes('difficulty') ? 'easy' : 'balanced', hidden: true, disabled: false, replaceChildren() {} };
  const state = { token: 'session-A' };
  const challengeV3 = { active: false, busy: false, owner: null, request: 0, rotation: 0, focus: 'balanced', difficulty: 'easy' };
  let renders = 0;
  const context = load(['recommendationDomain', 'normalizeRecommendationResult', 'loadChallenges'], {
    $, state, challengeV3, api, URLSearchParams, isLocalPreview: () => false,
    showChallengeSelectionView() {}, updateChallengeStartState() {},
    closeRagChallengeGenerator() {}, renderChallengeChoices() { renders++; }, showMessage() {},
  });
  return { ...context, $, state, challengeV3, renders: () => renders };
}
const result = () => ({ items: [1, 2, 3].map(challenge_id => ({ challenge_id, catalog_version: 'evidence-v3' })), policy: {} });
test('backend catalog recommendations without v3 display fields are accepted and normalized', async () => {
  const harness = recommendationHarness(async url => {
    assert.ok(url.startsWith('/challenge-recommendations'));
    return {
      items: [
        { challenge_id: 1, category: 'activity', title: '식후 걷기', daily_goal: '10분', recommendation_reason: '운동 실천 제안' },
        { challenge_id: 2, category: 'diet', title: '채소 먼저', daily_goal: '1회', source: { title: '가이드' } },
        { challenge_id: 3, category: 'tracking', title: '체중 기록', daily_goal: '주 1회' },
      ],
      notice: '일반 건강 실천입니다.',
    };
  });
  await harness.loadChallenges();
  assert.equal(harness.challengeV3.active, true);
  assert.equal(harness.renders(), 1);
  assert.deepEqual([...harness.state.selectedChallengeIds], [1, 2, 3]);
  assert.deepEqual(harness.state.challengeRecommendations.map(item => item.domain), ['aerobic_activity', 'fiber_diet', 'tracking']);
  assert.ok(harness.state.challengeRecommendations.every(item => item.catalog_version === 'evidence-v3'));
  assert.ok(harness.state.challengeRecommendations.every(item => item.verification_type === 3));
});
test('late follow-up response cannot expose previous session identifiers', async () => {
  let resolveActions;
  const harness = recommendationHarness(async url => url.startsWith('/challenge-recommendations')
    ? { ...result(), medical_guidance_required_first: true }
    : new Promise(resolve => { resolveActions = resolve; }));
  const pending = harness.loadChallenges();
  await new Promise(resolve => setImmediate(resolve));
  harness.state.token = 'session-B';
  resolveActions({ items: [{ action_id: 123 }] });
  await pending;
  assert.deepEqual([...harness.state.openFollowUpActionIds], []);
  assert.equal(harness.renders(), 0);
  assert.equal(harness.$('#start-challenge').disabled, true);
});
test('new account request is not blocked by previous request and old finalizer cannot alter it', async () => {
  const pendingResults = [];
  const harness = recommendationHarness(() => new Promise(resolve => pendingResults.push(resolve)));
  const first = harness.loadChallenges();
  harness.state.token = 'session-B';
  const second = harness.loadChallenges();
  pendingResults[0](result());
  await first;
  assert.equal(harness.challengeV3.busy, true);
  assert.equal(harness.$('#start-challenge').disabled, true);
  pendingResults[1](result());
  await second;
  assert.equal(harness.challengeV3.owner, 'session-B');
  assert.equal(harness.challengeV3.busy, false);
  assert.equal(harness.renders(), 1);
});
test('daily log lookup uses Korean date around UTC previous day', async () => {
  const state = { token: 'test', cycle: { user_challenges: [{ user_challenge_id: 2 }] } };
  const context = load(['isServerChallengeId', 'clearCurrentChallengeCycle', 'loadDailyRecords'], {
    hasCurrentChallengeCycle: () => true, state, challengeDay: () => '2026-09-09', isLocalPreview: () => false,
    renderDailyRecordList() {}, renderTodayTaskStatus() {},
    $: () => ({ innerHTML: '' }),
    api: async url => {
      assert.ok(url.endsWith('start_date=2026-09-09&end_date=2026-09-09'));
      return { items: [{ log_date: '2026-09-09', is_completed: true }] };
    },
  });
  await context.loadDailyRecords();
  assert.deepEqual([...state.dailyCompleted], ['2']);
});
test('V3 photo card states proof scope, not simple-check fallback', () => {
  const list = { innerHTML: '', closest() { return this; } };
  const context = load(['renderDailyRecordList'], {
    hasCurrentChallengeCycle: () => true, $: () => list, state: { dailyCompleted: new Set(), cycle: { user_challenges: [{
      user_challenge_id: 1, title: '걷기', catalog_version: 'evidence-v3', verification_type: 2,
      daily_goal: '누적 20분', verification_scope: '사진 제출만 확인',
    }] } }, challengeRecordType: () => 'photo', habitRecordIcon: () => '',
    challengeProofLabel: type => `유형 ${type}`, escapeHtml: value => value,
    recordActionLabel: () => '사진 제출',
  });
  context.renderDailyRecordList();
  assert.match(list.innerHTML, /누적 20분/);
  assert.match(list.innerHTML, /사진 제출만 확인/);
  assert.match(list.innerHTML, /^<button class="daily-record-card daily-record-open/);
  assert.doesNotMatch(list.innerHTML, /record-type-badge/);
  assert.doesNotMatch(list.innerHTML, /간편 체크/);
});

function photoHarness(response) {
  const target = { id: '9', item: { catalog_version: 'evidence-v3', verification_type: 2, goal: { target_minutes: 20 } } };
  const state = { token: 'session-A', cycle: { cycle_id: 1 }, recordTarget: target, dailyCompleted: new Set() };
  const nodes = { '#v3-photo-file': { files: [{ size: 1200 }] }, '#v3-photo-minutes': { value: '20' } };
  const $ = key => nodes[key] ||= { classList: { toggle() {}, add() {}, remove() {} }, scrollIntoView() {} };
  let calls = 0;
  let photoState;
  const formFields = {};
  const context = load(['submitV3Photo'], {
    $, state, isLocalPreview: () => false, challengeDay: () => '2026-09-09',
    FormData: class { append(key, value) { formFields[key] = value; } set(key,value) { formFields[key] = value; } },
    window: { confirm: () => true },
    setButtonBusy: () => () => {}, showPhotoRecordState(value) { photoState = value; },
    api: async (url, options) => { calls++; assert.match(url, /\/9\/photo-verifications$/); assert.equal(options.method, 'POST'); return await response(); },
    renderDailyRecordList() {}, updateDailyRecordSummary() {}, showMessage() {}, loadWeeklyReport: async () => {},
  });
  return { ...context, $, state, target, fields: formFields, calls: () => calls, photoState: () => photoState };
}
test('photo review pending never marks a challenge done and shows pending guidance', async () => {
  for (const response of [
    { challenge_completed: false, review_status: 'needs_review' },
    { challenge_completed: true, review_status: 'needs_review' },
    { challenge_completed: false, review_status: 'pending' },
    { challenge_completed: false, review_status: 'in_review' },
  ]) {
    const h = photoHarness(async () => response);
    await h.submitV3Photo();
    assert.equal(h.state.dailyCompleted.size, 0);
    assert.equal(h.photoState(), 'photo-state-pending');
    assert.equal(h.target.submitting, false);
  }
});
test('HTTP success without accepted completion never marks a photo challenge done', async () => {
  for (const response of [
    { challenge_completed: false, review_status: 'rejected' },
    { challenge_completed: 'true', review_status: 'accepted' },
  ]) {
    const h = photoHarness(async () => response);
    await h.submitV3Photo();
    assert.equal(h.state.dailyCompleted.size, 0);
    assert.equal(h.photoState(), 'photo-state-fail');
    assert.equal(h.target.submitting, false);
  }
});
test('accepted photo uses self-reported amount and Korean date, and cannot submit twice', async () => {
  const h = photoHarness(async () => ({ challenge_completed: true, review_status: 'accepted' }));
  await h.submitV3Photo();
  await h.submitV3Photo();
  assert.equal(h.calls(), 1);
  assert.equal(h.fields.actual_value, '20');
  assert.equal(h.fields.verification_date, '2026-09-09');
  assert.ok(h.state.dailyCompleted.has('9'));
  assert.equal(h.photoState(), 'photo-state-success');
});
test('late photo responses cannot mark a new account or a new cycle done', async () => {
  for (const change of ['token', 'cycle']) {
    let resolve;
    const h = photoHarness(() => new Promise(r => { resolve = r; }));
    const pending = h.submitV3Photo();
    await h.submitV3Photo();
    assert.equal(h.calls(), 1);
    if (change === 'token') h.state.token = 'session-B';
    else h.state.cycle = { cycle_id: 2 };
    resolve({ challenge_completed: true, review_status: 'accepted' });
    await pending;
    assert.equal(h.state.dailyCompleted.size, 0);
  }
});
test('missing, insufficient and out-of-contract amounts send no photo request', async () => {
  for (const amount of ['', '0', '19', '721', 'Infinity']) {
    const h = photoHarness(async () => { throw new Error('must not submit'); });
    h.$('#v3-photo-minutes').value = amount;
    await h.submitV3Photo();
    assert.equal(h.calls(), 0);
  }
});

test('meal photo preview opens the evidence-v3 upload with three demo cases', () => {
  for (const file of ['src/frontend/app.js', 'src/frontend/intro-retro-app.js']) {
    const source = fs.readFileSync(file, 'utf8');
    assert.match(source, /get\("preview"\) !== "meal-photo"/);
    assert.match(source, /openPhotoRecordModal\(item\)/);
    assert.match(source, /file\.name === "demo-pass\.png"/);
    assert.match(source, /인증을 통과했어요/);
    assert.match(source, /Number\(item\.verification_type\) !== 1/);
    assert.doesNotMatch(source, /input\.checked = input\.value === targetCount/);
    assert.match(source, /element\.hidden = !vegetableReview/);
    assert.match(source, /result\.notice \|\| "사진은 제출됐지만/);
    assert.match(source, /\["image\/jpeg", "image\/png", "image\/webp"\]/);
    assert.match(source, /dimensions\.width \* dimensions\.height > 12_000_000/);
    assert.match(source, /URL\.createObjectURL\(file\)/);
    assert.match(source, /#v3-photo-file"\)\.addEventListener\("change"/);
  }
  for (const file of ['src/frontend/index.html', 'src/frontend/intro-retro.html']) {
    const html = fs.readFileSync(file, 'utf8');
    assert.equal((html.match(/class="demo-photo-card"/g) || []).length, 3);
    assert.equal((html.match(/class="demo-photo-card" aria-pressed="false"/g) || []).length, 3);
    assert.equal((html.match(/name="v3-photo-value"/g) || []).length, 3);
    assert.equal((html.match(/v3-vegetable-only/g) || []).length, 4);
    assert.doesNotMatch(html, /external_vlm_consent/);
    assert.match(html, /로컬 모델이 판단하기 어려운 경우 OpenAI VLM을 보완 검토에 자동으로 사용할 수 있습니다/);
    assert.match(html, /id="v3-photo-preview"/);
    assert.match(html, /id="v3-photo-change-label"[^>]*hidden>사진 변경/);
    assert.match(html, /업로드 조건: 대표 사진 1장 · JPG·PNG·WEBP · 8MB·1200만 화소 이하/);
    assert.match(html, /사진을 선택하면 형식·용량·해상도를 확인합니다/);
  }
  const indexHtml = fs.readFileSync('src/frontend/index.html', 'utf8');
  assert.doesNotMatch(indexHtml, /id="v3-vlm-consent"/);
  assert.doesNotMatch(indexHtml, /OpenAI VLM으로 보완 검토하는 데 동의/);
  for (const file of ['src/frontend/styles.css', 'src/frontend/intro-retro-base.css']) {
    const css = fs.readFileSync(file, 'utf8');
    assert.match(css, /\.demo-photo-card\[aria-pressed="true"\]/);
    assert.match(css, /content:"✓ 선택"/);
  }
});

test('walking photo proof hides every vegetable-only demo and guidance block', () => {
  for (const file of ['src/frontend/app.js', 'src/frontend/intro-retro-app.js']) {
    const source = fs.readFileSync(file, 'utf8');
    assert.match(source, /const vegetableReview = v3 && Number\(item\.verification_type\) === 1/);
    assert.match(source, /\$\$\("\.v3-vegetable-only"\)\.forEach/);
    assert.match(source, /인증 대상이 잘 보이도록 다시 찍어주세요/);
  }
});


test('photo runtime outage describes a server problem without accepting evidence', async () => {
  const error = Object.assign(new Error('서버 실행 환경을 복구해야 합니다.'), {status:503});
  const h = photoHarness(async () => {throw error;});
  await h.submitV3Photo();
  assert.equal(h.$('#photo-fail-title').textContent, '사진 검토를 진행할 수 없어요');
  assert.equal(h.$('#photo-fail-hint').textContent, error.message);
  assert.equal(h.photoState(), 'photo-state-fail');
  assert.equal(h.state.dailyCompleted.size, 0);
  assert.equal(h.target.submitting, false);
});


for (const confirmed of [true, false]) test(`valid photo requires final confirmation: ${confirmed}`, async () => {
  let count=0;
  const h=photoHarness(async()=> ++count === 1
    ? {review_status:'needs_confirmation',challenge_completed:false,notice:'최종 확인'}
    : {review_status:'accepted',challenge_completed:true});
  h.target.item.verification_type=1;
  h.window.confirm=()=>confirmed;
  await h.submitV3Photo();
  assert.equal(h.calls(),confirmed ? 2 : 1);
  assert.equal(h.state.dailyCompleted.has('9'),confirmed);
  assert.equal(h.fields.confirmed,confirmed ? 'true' : undefined);
  assert.equal(h.photoState(),confirmed ? 'photo-state-success' : 'photo-state-fail');
});

test('meal photo sends tri-state hints and preserves them through confirmation', async () => {
  let count = 0;
  const h = photoHarness(async () => ++count === 1
    ? {review_status:'needs_confirmation',challenge_completed:false}
    : {review_status:'accepted',challenge_completed:true});
  h.target.item.verification_type = 1;
  h.window.confirm = () => true;
  h.$('#v3-photo-contains-kimchi').value = 'yes';
  h.$('#v3-photo-strong-seasoning').value = 'no';
  h.$('#v3-photo-white-food-on-white').value = 'unsure';
  await h.submitV3Photo();
  assert.equal(h.calls(), 2);
  assert.equal(h.fields.contains_kimchi, 'yes');
  assert.equal(h.fields.strong_seasoning, 'no');
  assert.equal(h.fields.white_food_on_white, 'unsure');
  assert.equal(h.fields.confirmed, 'true');
});

test('unknown meal hints remain unknown and pending review cannot complete', async () => {
  const h = photoHarness(async () => ({review_status:'needs_review',challenge_completed:false}));
  h.target.item.verification_type = 1;
  h.$('#v3-photo-contains-kimchi').value = 'unexpected';
  await h.submitV3Photo();
  assert.equal(h.fields.contains_kimchi, 'unsure');
  assert.equal(h.fields.white_food_on_white, 'unsure');
  assert.equal(h.state.dailyCompleted.size, 0);
});

test('activity submission sends no meal hints', async () => {
  const h = photoHarness(async () => ({review_status:'accepted',challenge_completed:true}));
  await h.submitV3Photo();
  for (const name of ['contains_kimchi', 'strong_seasoning', 'white_food_on_white']) {
    assert.equal(h.fields[name], undefined);
  }
});
