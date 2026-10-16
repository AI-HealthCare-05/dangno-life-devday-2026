const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function recordHarness(api, file) {
  const source = fs.readFileSync(`src/frontend/${file}`, 'utf8');
  const state = { token: 'synthetic-session', cycle: { cycle_id: 1 }, dailyCompleted: new Set() };
  const messages = [];
  const context = vm.createContext({
    state, api, isLocalPreview: () => false, challengeDay: () => '2026-10-09',
    isHydrationRecord: () => false, renderDailyRecordList() {}, updateDailyRecordSummary() {},
    loadWeeklyReport: async () => {}, allDailyChallengesCompleted: () => false,
    showMessage: message => messages.push(message),
  });
  vm.runInContext(source.match(/^async function completeDailyRecord\([^]*?^}/m)[0], context);
  const target = { id: '8', item: { catalog_version: 'evidence-v3', verification_type: 3 } };
  return { context, state, target, messages };
}

for (const file of ['app.js', 'intro-retro-app.js']) {
for (const notice of [
  '당근밭에 비료를 주었습니다. 당근 10개를 획득했습니다!',
  '당근밭의 잡초를 뽑았습니다. 당근 10개를 획득했습니다! 모든 챌린지를 완료해 당근 50개를 추가로 획득했습니다!',
]) test(`${file} direct record uses the server wallet notice: ${notice}`, async () => {
  let calls = 0;
  const h = recordHarness(async (url, options) => {
    calls++;
    assert.equal(url, '/user-challenges/8/logs/2026-10-09');
    assert.equal(JSON.parse(options.body).is_completed, true);
    return { wallet_reward: { notice } };
  }, file);
  await h.context.completeDailyRecord(h.target);
  await h.context.completeDailyRecord(h.target);
  assert.equal(calls, 1);
  assert.deepEqual(h.messages, [notice]);
  assert.ok(h.state.dailyCompleted.has('8'));
});

test(`${file} failed direct record creates neither local completion nor reward announcement`, async () => {
  const h = recordHarness(async () => { throw new Error('offline'); }, file);
  await assert.rejects(h.context.completeDailyRecord(h.target), /offline/);
  assert.equal(h.state.dailyCompleted.size, 0);
  assert.equal(h.messages.length, 0);
});

test(`${file} late direct record response cannot announce a previous account reward`, async () => {
  let finish;
  const h = recordHarness(() => new Promise(resolve => { finish = resolve; }), file);
  const pending = h.context.completeDailyRecord(h.target);
  h.state.token = 'another-session';
  finish({ wallet_reward: { notice: 'must not announce' } });
  await pending;
  assert.equal(h.state.dailyCompleted.size, 0);
  assert.equal(h.messages.length, 0);
});
}
