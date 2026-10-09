const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../src/frontend/app.js'), 'utf8');
const helper = source.slice(source.indexOf('const returningToForest ='), source.indexOf('function showRequestedAccountProfile('));
function setup(search, gate = async () => {}) {
  const destinations = [], calls = [], guidance = [];
  const context = {
    URLSearchParams, window: {location: {search, assign: value => destinations.push(value)}},
    beginReturningEligibility: value => guidance.push(value),
    showStoredEligibilityGuidance: () => guidance.push('blocked'),
    showStep: value => guidance.push(value), showMessage: value => guidance.push(value),
    api: async (url, options) => {calls.push([url, options.method]); await gate();},
  };
  vm.createContext(context); vm.runInContext(helper, context);
  return {context, destinations, calls, guidance};
}
test('forest return rejects arbitrary query destinations', async () => {
  for (const search of ['', '?returnTo=https://example.test', '?returnTo=forest-challenges-evil']) {
    const {context, destinations, calls} = setup(search);
    assert.equal(await context.returnToForestSettings({service_eligible:true, reason_codes:[]}), false);
    assert.equal(destinations.length, 0); assert.equal(calls.length, 0);
  }
});
test('missing, malformed and medically blocked eligibility never enters forest', async () => {
  const {context, destinations, calls, guidance} = setup('?returnTo=forest-challenges');
  for (const eligibility of [null, {}, {service_eligible:true}, {service_eligible:true,reason_codes:'DIAGNOSED_DIABETES'}, {service_eligible:true,reason_codes:[null]}, {service_eligible:1,reason_codes:[]}]) {
    assert.equal(await context.returnToForestSettings(eligibility), true);
  }
  for (const code of ['DIAGNOSED_DIABETES','URGENT_MEDICAL_ATTENTION','SAME_DAY_MEDICAL_ATTENTION','CONSENT_REQUIRED','UNDER_MINIMUM_SERVICE_AGE']) {
    await context.returnToForestSettings({service_eligible:true, reason_codes:[code]});
  }
  assert.equal(destinations.length, 0); assert.equal(calls.length, 0);
  assert.equal(guidance[0], 'forest-challenges');
});
test('forest return waits for read-only current server consent gate and handles rejection', async () => {
  let release;
  const waiting = new Promise(resolve => { release = resolve; });
  const valid = setup('?returnTo=forest-challenges', () => waiting);
  const result = valid.context.returnToForestSettings({service_eligible:true, reason_codes:[]});
  assert.equal(valid.destinations.length, 0);
  release(); assert.equal(await result, true);
  assert.deepEqual(valid.calls, [['/challenge-v2/today', 'GET']]);
  assert.deepEqual(valid.destinations, ['/forest#daily-settings']);
  const rejected = setup('?returnTo=forest-challenges', async () => {throw new Error('Consent revoked');});
  await rejected.context.returnToForestSettings({service_eligible:true, reason_codes:[]});
  assert.equal(rejected.destinations.length, 0); assert.ok(rejected.guidance.includes('Consent revoked'));
});
test('restored login and completed eligibility await guarded forest return', () => {
  assert.match(source, /syncReturningEligibilityState\(latestEligibility\);\s*if \(await returnToForestSettings\(latestEligibility\)\) return;/);
  assert.match(source, /syncReturningEligibilityState\(result\);\s*if \(await returnToForestSettings\(result\)\) return;/);
});
