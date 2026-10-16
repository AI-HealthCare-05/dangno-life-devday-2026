const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../../src/frontend/app.js'), 'utf8');
function harness() {
  const nodes = new Map();
  const state = { dailyCompleted: new Set(['7', '9']), waterServingsByChallenge: {}, cycle: { user_challenges: [{ user_challenge_id: 7 }, { user_challenge_id: 8 }, { user_challenge_id: 9 }] } };
  let writes = 0;
  const $ = key => {
    if (!nodes.has(key)) nodes.set(key, { hidden: false, dataset: {}, style: { setProperty() {}, removeProperty() {} }, classList: { add() {}, remove() {}, toggle() {} }, setAttribute() {}, focus() {} });
    return nodes.get(key);
  };
  const ctx = vm.createContext({ state, $, $$: () => [], Date, challengeDay: () => "2026-09-08", isLocalPreview: () => false,
    api: async () => { writes++; return {}; }, renderDailyRecordList() {}, updateDailyRecordSummary() {},
    loadWeeklyReport: async () => {}, showMessage() {}, habitRecordIcon: kind => kind, openForestEntryDialog() {},
  });
  for (const name of ['challengeRecordType', 'simpleRecordPresentation', 'isHydrationRecord', 'clampWaterServings', 'waterLevelForServings', 'currentWaterServings', 'syncWaterServingControl', 'openSimpleRecordModal', 'showPhotoRecordState', 'clearPhotoSelectionPreview', 'resetPhotoRecordModal', 'openPhotoRecordModal', 'closeRecordModal', 'dailyChallengeTargetCount', 'allDailyChallengesCompleted', 'closeChallengeRewardDialog', 'openChallengeRewardDialog', 'maybeOpenDailyReward', 'completeDailyRecord', 'undoDailyRecord']) {
    const match = source.match(new RegExp(`^(?:async )?function ${name}\\([^]*?^}`, 'm'));
    assert.ok(match, name); vm.runInContext(match[0], ctx);
  }
  const handler = source.slice(source.indexOf('$("#confirm-simple-record").addEventListener("click", async (event) => {'));
  const end = handler.indexOf('\n});');
  $('confirm-handler').addEventListener = (_, fn) => { ctx.confirm = fn; };
  vm.runInContext(handler.slice(0,end+4).replace('$("#confirm-simple-record")', '$("confirm-handler")'), ctx);
  return { ctx, state, $, writes: () => writes };
}
test('saved completion opens a review and confirming sends no write or reset', async () => {
  const {ctx,state,$,writes} = harness();
  ctx.openSimpleRecordModal({ user_challenge_id: 7, title: '식후 10분 천천히 걷기' });
  assert.equal($('#record-modal').hidden, false);
  assert.equal($('#confirm-simple-record').textContent, '확인');
  assert.equal($('#record-simple-panel .record-cancel').hidden, true);
  assert.equal(state.recordTarget.completed, true);
  assert.equal($('#undo-daily-record').hidden, false);
  await ctx.confirm({});
  assert.equal($('#record-modal').hidden, true);
  assert.ok(state.dailyCompleted.has('7'));
  assert.equal(writes(), 0);
});
test('completed meal opens review without re-upload; next unfinished water shows normal choices', () => {
  const {ctx,state,$} = harness();
  ctx.openPhotoRecordModal({ user_challenge_id: 9, title: '식사 리듬 지키기' });
  assert.equal(state.recordTarget.completed, true);
  assert.equal($('#record-photo-panel').hidden, true);
  ctx.closeRecordModal();
  ctx.openSimpleRecordModal({ user_challenge_id: 8, title: '물 마시기' });
  assert.equal($('#record-simple-visual').dataset.kind, 'water');
  assert.equal($('#record-simple-panel .record-cancel').hidden, false);
  assert.equal($('#confirm-simple-record').textContent, '네, 물을 선택했어요');
  assert.equal(state.recordTarget.completed, false);
  assert.equal($('#undo-daily-record').hidden, true);
});
test('duplicate completion never overwrites stored logs, while new completion writes once', async () => {
  const {ctx,writes} = harness();
  await ctx.completeDailyRecord({ id: '7' });
  await ctx.completeDailyRecord({ id: '10', completed: true });
  assert.equal(writes(), 0);
  await ctx.completeDailyRecord({ id: '8' });
  await ctx.completeDailyRecord({ id: '8' });
  assert.equal(writes(), 2);
});

test('last daily completion claims reward and opens reward dialog', async () => {
  const {ctx,$} = harness();
  const requests = [];
  ctx.api = async (url, options) => {
    requests.push({ url, method: options?.method });
    if (url.startsWith('/challenge-rewards/daily/')) return { carrot_amount: 55, carrot_balance: 155, claimed: true };
    return {};
  };
  $('#challenge-reward-dialog').showModal = () => { $('#challenge-reward-dialog').open = true; };
  await ctx.completeDailyRecord({ id: '8' });
  assert.deepEqual(requests.map((item) => [item.method, item.url]), [
    ['PUT', '/user-challenges/8/logs/2026-09-08'],
    ['POST', '/challenge-rewards/daily/2026-09-08'],
  ]);
  assert.equal($('#challenge-reward-dialog').open, true);
  assert.equal($('#challenge-reward-amount').textContent, '+55 당근');
  assert.equal($('#challenge-reward-balance').textContent, '현재 보유 당근 155개');
});

test('undo saves false for today, removes only that completion and allows recording again', async () => {
  const {ctx,state} = harness();
  const requests = [];
  ctx.api = async (url, options) => requests.push({url, body:JSON.parse(options.body)});
  ctx.openSimpleRecordModal({user_challenge_id:7,title:'식후 10분 천천히 걷기'});
  const target = state.recordTarget;
  assert.equal(await ctx.undoDailyRecord(target), true);
  assert.equal(requests[0].url, '/user-challenges/7/logs/2026-09-08');
  assert.equal(requests[0].body.is_completed, false);
  assert.equal(requests[0].body.value, null);
  assert.equal(state.dailyCompleted.has('7'), false);
  assert.equal(state.dailyCompleted.has('9'), true);
  assert.equal(target.completed, false);
  await ctx.completeDailyRecord(target);
  assert.equal(state.dailyCompleted.has('7'), true);
});
test('failed undo preserves completion and can be retried', async () => {
  const {ctx,state} = harness();
  const target = {id:'7',completed:true};
  ctx.api = async () => {throw new Error('network unavailable');};
  await assert.rejects(ctx.undoDailyRecord(target), /network unavailable/);
  assert.ok(state.dailyCompleted.has('7'));
  assert.equal(target.completed,true);
  assert.equal(target.undoPending,false);
  ctx.api = async () => ({});
  assert.equal(await ctx.undoDailyRecord(target),true);
});
test('duplicate undo clicks send once and late responses cannot alter another account or cycle', async () => {
  for (const change of ['token','cycle']) {
    const {ctx,state} = harness();
    let resolve; let writes=0;
    ctx.api = () => {writes++; return new Promise(r => {resolve=r;});};
    const target = {id:'7',completed:true};
    const pending = ctx.undoDailyRecord(target);
    assert.equal(await ctx.undoDailyRecord(target),false);
    assert.equal(writes,1);
    if (change==='token') state.token='new-account'; else state.cycle={cycle_id:'new-cycle'};
    state.dailyCompleted = new Set(['7','new']);
    resolve({});
    assert.equal(await pending,false);
    assert.deepEqual([...state.dailyCompleted],['7','new']);
  }
});
