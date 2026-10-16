const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { ForestAccountWallet } = require('../src/frontend/forest-wallet.js');

function fixture() {
  let balance = 100, version = 0, failAfterCommit = false;
  const receipts = new Set(), requests = [], events = [];
  const snapshot = () => ({ user_id: 7, carrot_balance: balance, wallet_revision: version, wallet_updated_at: new Date(1700000000000 + version).toISOString() });
  const host = {
    crypto: { randomUUID: () => '68c9dc37-31f0-4ac2-89e9-94f80e96cdf9' },
    GandangAuthSession: { resolve: async () => ({ token: 'synthetic', profile: { id: 7 } }) },
    CustomEvent: class { constructor(type, options) { this.type = type; this.detail = options.detail; } },
    dispatchEvent: event => events.push(event),
    fetch: async (url, options) => {
      requests.push({ url, options });
      if (options.body) {
        const { action, request_id } = JSON.parse(options.body);
        if (!receipts.has(request_id)) { balance += action === 'pet_feed' ? -1 : 1; version++; receipts.add(request_id); }
        if (failAfterCommit) { failAfterCommit = false; throw new TypeError('response disconnected'); }
      }
      return { ok: true, status: 200, json: async () => ({ data: snapshot() }) };
    },
  };
  return { wallet: new ForestAccountWallet(host), host, requests, events, snapshot, drop: () => { failAfterCommit = true; } };
}

test('a disconnected response retries the same receipt key and spends only once', async () => {
  const f = fixture(); await f.wallet.connect(); f.drop();
  await f.wallet.perform('pet_feed');
  assert.equal(f.wallet.value.carrot_balance, 99);
  assert.equal(f.requests.length, 3);
  assert.equal(f.requests[1].options.body, f.requests[2].options.body);
  assert.equal(f.requests[1].options.cache, 'no-store');
});

test('server errors never create optimistic coins or spend a local balance', async () => {
  const f = fixture(); await f.wallet.connect();
  f.host.fetch = async () => ({ ok: false, status: 409, json: async () => ({ detail: 'insufficient carrots' }) });
  await assert.rejects(f.wallet.perform('pet_feed'), /insufficient/);
  assert.equal(f.wallet.value.carrot_balance, 100);
  assert.equal(f.events.length, 1);
});

test('another account and an older response cannot replace the active wallet', async () => {
  const f = fixture(); await f.wallet.connect(); await f.wallet.perform('rabbit_catch');
  assert.equal(f.wallet.accept({ ...f.snapshot(), user_id: 8, carrot_balance: 9000 }), false);
  f.wallet.accept({ user_id: 7, carrot_balance: 5, wallet_updated_at: new Date(1600000000000).toISOString() });
  assert.equal(f.wallet.value.carrot_balance, 101);
  f.wallet.accept({ user_id: 7, carrot_balance: 3, wallet_revision: 0, wallet_updated_at: f.wallet.value.wallet_updated_at });
  assert.equal(f.wallet.value.carrot_balance, 101, 'receipt revision handles updates within the same timestamp millisecond');
});

test('UUID receipt keys also work on HTTP development origins without randomUUID', () => {
  const f = fixture(); f.host.crypto = { getRandomValues: bytes => bytes.fill(5) };
  assert.match(f.wallet.newRequestId(), /^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/);
});

test('HTTP authentication retry refuses to credit a different newly logged-in account', async () => {
  const f = fixture(); await f.wallet.connect();
  f.host.fetch = async () => ({ status: 401 });
  f.host.GandangAuthSession.resolve = async () => ({ token: 'other', profile: { id: 8 } });
  await assert.rejects(f.wallet.perform('rabbit_catch'), /계정이 변경/);
  assert.equal(f.wallet.value.carrot_balance, 100);
});

test('account presentation saves discard guest money and pending claims while preserving outfits', async () => {
  const source = fs.readFileSync('src/frontend/forest-game.js', 'utf8');
  const start = source.indexOf('  class AccountForestAdapter'), end = source.indexOf('  const adapter =', start);
  const storage = new Map([['forest-save', JSON.stringify({ carrots: 9999, challengeCarrotClaims: { fake: { amount: 99 } }, avatar: { name: 'saved', outfit: 'keep' } })]]);
  const context = vm.createContext({
    DemoForestAdapter: class {}, STORAGE_KEY: 'forest-save', normalizeState: value => value,
    defaultState: () => ({ avatar: { name: 'default' } }),
    localStorage: { getItem: key => storage.get(key), setItem: (key, value) => storage.set(key, value) },
    window: { ForestWallet: { connect: async () => ({ user_id: 7, carrot_balance: 110, daily_actions: { water: true } }) } },
  });
  vm.runInContext(source.slice(start, end) + '\nglobalThis.account = new AccountForestAdapter();', context);
  const loaded = await context.account.load();
  assert.equal(loaded.carrots, 110); assert.equal(loaded.avatar.outfit, 'keep');
  assert.equal(Object.keys(loaded.challengeCarrotClaims).length, 0);
  const saved = JSON.parse(storage.get('forest-save:account:7'));
  assert.equal('carrots' in saved, false); assert.equal('challengeCarrotClaims' in saved, false);
  context.window.ForestWallet.connect = async () => ({ user_id: 8, carrot_balance: 100 });
  await context.account.load();
  assert.ok(storage.has('forest-save:account:8')); assert.ok(storage.has('forest-save:account:7'));
});

function certification(mode) {
  const source = fs.readFileSync('src/frontend/challenge-v2.js', 'utf8');
  const callbacks = {}, notices = [], celebrations = [], saved = [];
  const item = { id: 1, slot: 1, status: 'assigned', sessions: [], goal: { domain: 'diet', target_sessions: 1, goal_unit: 'count', per_session_quantity: 1 } };
  const context = vm.createContext({
    root: { addEventListener: (type, callback) => { callbacks[type] = callback; }, querySelector: () => null },
    plan: { day_id: 2, items: [item], rewards: [] }, busy: false,
    quickSessionPayload: () => ({ done: true }), render() {},
    notify: message => notices.push(message), saveMvpCompletion: item => saved.push(item),
    showCelebration: (item, bonus) => celebrations.push({ item, bonus }),
    channel: null,
    api: async () => {
      if (mode === 'error') throw new Error('server failed');
      return { day_id: 2, items: [{ ...item, status: mode === 'pending' ? 'submitted' : 'completed' }],
        rewards: mode === 'pending' ? [] : [{ source_key: 'v2-slot:2:1', carrot_amount: 10 }] };
    },
  });
  const applyStart = source.indexOf('  function applyPlan('), applyEnd = source.indexOf('  root.addEventListener("click"', applyStart);
  const clickEnd = source.indexOf('  root.addEventListener("input"', applyEnd);
  vm.runInContext(source.slice(applyStart, clickEnd), context);
  return { context, callbacks, notices, celebrations, saved,
    click: () => callbacks.click({ target: { closest: selector => selector === '[data-certify]' ? { dataset: { certify: '1' } } : null } }) };
}

test('failed certification and pending photo review cannot display a reward celebration', async () => {
  for (const mode of ['error', 'pending']) {
    const f = certification(mode); await f.click();
    assert.equal(f.celebrations.length, 0); assert.equal(f.saved.length, 0);
    assert.match(f.notices[0], mode === 'error' ? /완료하지 못/ : /검토/);
  }
});

test('successful server receipt celebrates once, while repeated responses cannot celebrate or reward again', async () => {
  const f = certification('success'); await f.click(); await f.click();
  assert.equal(f.celebrations.length, 1); assert.equal(f.saved.length, 1);
});

test('the final completion displays the additional 50-carrot receipt with the domain reward', () => {
  const f = certification('success');
  f.context.applyPlan({ day_id: 2, items: [{ ...f.context.plan.items[0], status: 'completed' }], rewards: [
    { source_key: 'v2-slot:2:1', carrot_amount: 10 }, { source_key: 'v2-day:7:2026-10-09', carrot_amount: 50 },
  ] });
  assert.equal(f.celebrations[0].bonus, 50);
});
