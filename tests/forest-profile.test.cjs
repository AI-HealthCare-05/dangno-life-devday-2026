const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const base = path.join(__dirname, '../src/frontend');
const source = fs.readFileSync(path.join(base, 'forest-profile.js'), 'utf8');
const game = fs.readFileSync(path.join(base, 'forest-game.js'), 'utf8');
const reply = (body, status = 200) => ({ ok: status >= 200 && status < 300, status, json: async () => body });
function harness(fetch) {
  const events = {}, docEvents = {}, messages = {}, writes = [];
  const window = {
    fetch, setTimeout, clearTimeout, document: { hidden: false,
      addEventListener: (k, fn) => docEvents[k] = fn,
      removeEventListener: k => delete docEvents[k] },
    addEventListener: (k, fn) => events[k] = fn,
    removeEventListener: k => delete events[k],
    localStorage: { setItem: (...args) => writes.push(args) },
    BroadcastChannel: class { addEventListener(k, fn) { messages[k] = fn; } close() {} },
  };
  vm.runInNewContext(source, { window, AbortController });
  return { api: window.ForestProfile, events, docEvents, messages, writes, window };
}
test('reads canonical name from bare users/me response with an in-memory token only', async () => {
  const calls = [], app = harness(async (url, options) => {
    calls.push({ url, options });
    return reply(url.endsWith('/refresh') ? { access_token: 'test-token' } : { name: '새 닉네임' });
  });
  assert.equal(await app.api.loadName(), '새 닉네임');
  assert.equal(app.api.PROFILE_URL, '/?account=profile');
  assert.deepEqual(calls.map(c => c.url), ['/api/v1/auth/token/refresh', '/api/v1/users/me']);
  assert.equal(calls[1].options.headers.Authorization, 'Bearer test-token');
  assert.ok(calls.every(c => !c.options.method && c.options.cache === 'no-store' && c.options.credentials === 'same-origin'));
  assert.deepEqual(app.writes, []);
});
test('no session, malformed token, or unavailable account never invents a profile name', async () => {
  for (const status of [400, 401, 403]) {
    let calls = 0;
    const app = harness(async () => { calls++; return reply({}, status); });
    assert.equal(await app.api.loadName(), null); assert.equal(calls, 1);
  }
  assert.equal(await harness(async () => reply({})).api.loadName(), null);
  for (const name of [null, '', '  ', 123]) {
    const app = harness(async url => reply(url.endsWith('/refresh') ? { access_token: 'test-token' } : { name }));
    assert.equal(await app.api.loadName(), name === 123 ? null : '숲지기');
  }
});

test('temporary account failures retain the last name; confirmed logout clears it', async () => {
  for (const bridge of [false, true]) {
    let failure = null;
    const seen = [], app = harness(async url => {
      if (failure === 'network') throw new TypeError('offline');
      if (failure === 'timeout') throw Object.assign(new Error('timeout'), { name: 'AbortError' });
      return reply(url.endsWith('/refresh') ? { access_token: 'test-token' } : { name: '확인된 이름' }, failure || 200);
    });
    if (bridge) app.window.GandangAuthSession = { async resolve() {
      if (failure) throw Object.assign(new Error('account unavailable'), { status: failure });
      return { profile: { name: '확인된 이름' } };
    } };
    const sync = app.api.watch(name => seen.push(name));
    await sync.refresh();
    const count = seen.length;
    for (failure of [503, 'network', 'timeout']) {
      await sync.refresh();
      assert.equal(seen.length, count, `bridge=${bridge}: ${failure} must not replace name`);
      assert.equal(seen.at(-1), '확인된 이름');
    }
    failure = 401; await sync.refresh(); assert.equal(seen.at(-1), null);
    failure = null; await sync.refresh(); assert.equal(seen.at(-1), '확인된 이름');
    sync.dispose();
  }
});

test('legacy account lookup distinguishes a server outage from a missing session', async () => {
  for (const endpoint of ['refresh', 'me']) {
    const app = harness(async url => reply({ access_token: 'test-token' }, url.endsWith('/' + endpoint) ? 503 : 200));
    await assert.rejects(app.api.loadName(), { status: 503 });
  }
});

test('nameplate keeps the account name when the renderer still holds an older name', () => {
  const start = game.indexOf('  function projectMapLabels() {');
  const end = game.indexOf('  window.addEventListener("forest-camera-view"', start);
  const plate = { style: {} }, state = { avatar: { name: '현재 계정', x: 100, y: 100 } };
  const context = { state, currentScene: 'world', $: selector => selector === '#avatar-nameplate' ? plate : null,
    window: { ForestCamera: { avatarAnchor: () => ({ x: .4, y: .6, name: '오래된 캐시 이름' }) } } };
  vm.runInNewContext(game.slice(start, end) + '\nprojectMapLabels();', context);
  assert.equal(plate.textContent, '현재 계정');
  assert.equal(plate.style.left, '40%'); assert.equal(plate.style.top, '60%'); assert.equal(plate.hidden, false);
});
test('focus and profile revision re-read the account; logout restores guest display', async () => {
  let name = '첫 이름', authenticated = true;
  const seen = [], app = harness(async url => url.endsWith('/refresh')
    ? reply({ access_token: 'test-token' }, authenticated ? 200 : 401) : reply({ name }));
  const sync = app.api.watch(value => seen.push(value));
  await sync.refresh(); assert.equal(seen.at(-1), '첫 이름');
  name = '바뀐 이름'; app.events.storage({ key: app.api.REVISION_KEY });
  await new Promise(resolve => setImmediate(resolve)); assert.equal(seen.at(-1), '바뀐 이름');
  authenticated = false; app.events.focus();
  await new Promise(resolve => setImmediate(resolve)); assert.equal(seen.at(-1), null);
  sync.dispose(); assert.equal(Object.keys(app.events).length, 0); assert.deepEqual(app.writes, []);
});
test('a superseded account request cannot restore the old name', async () => {
  let resolveOld, profiles = 0;
  const seen = [], app = harness(async url => {
    if (url.endsWith('/refresh')) return reply({ access_token: 'test-token' });
    profiles++;
    return profiles === 1 ? new Promise(resolve => resolveOld = resolve) : reply({ name: '현재 계정' });
  });
  const sync = app.api.watch(name => seen.push(name));
  await new Promise(resolve => setImmediate(resolve));
  await sync.refresh(); resolveOld(reply({ name: '이전 계정' }));
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(seen, ['현재 계정']); sync.dispose();
});
test('forest guest save does not cache the authenticated name or change cosmetics', async () => {
  const start = game.indexOf('  class DemoForestAdapter {');
  const end = game.indexOf('  class ApiForestAdapter {', start);
  const saved = {}, guest = { avatar: { name: '기존 숲지기', cosmetics: { hair: 'hair-1' } }, carrots: 10 };
  const context = { STORAGE_KEY: 'save', normalizeState: value => value || structuredClone(guest), defaultState: () => structuredClone(guest),
    localStorage: { getItem: key => saved[key] || null, setItem: (key, value) => saved[key] = value } };
  vm.runInNewContext(game.slice(start, end) + '\nthis.Adapter = DemoForestAdapter;', context);
  const adapter = new context.Adapter(), state = await adapter.load(); state.avatar.name = '계정에서 받은 이름';
  state.carrots = 20; await adapter.save(state);
  assert.equal(JSON.parse(saved.save).avatar.name, '기존 숲지기');
  assert.equal(state.avatar.name, '계정에서 받은 이름');
  assert.equal(JSON.parse(saved.save).carrots, 20);
  assert.equal(JSON.parse(saved.save).avatar.cosmetics.hair, 'hair-1');
});
test('forest has no local nickname editor, retains customization and loads the bridge offline', () => {
  const html = fs.readFileSync(path.join(base, 'forest.html'), 'utf8');
  const worker = fs.readFileSync(path.join(base, 'forest-sw.js'), 'utf8');
  for (const id of ['avatar-name', 'profile-nickname', 'profile-form', 'profile-dialog']) assert.ok(!html.includes(`id="${id}"`));
  assert.ok(!html.includes('닉네임 저장')); assert.ok(!game.includes('renderProfileAvatar'));
  assert.ok(html.includes('id="open-avatar-studio"')); assert.ok(html.includes('id="avatar-nameplate"'));
  assert.ok(html.includes('/static/forest-profile.js?v=20261003-navigation-session-v1'));
  assert.ok(worker.includes('/static/forest-profile.js?v=20261003-navigation-session-v1'));
  assert.equal((game.match(/ForestProfile.watch\(applyAccountNickname\)/g) || []).length, 1);
  assert.ok(game.indexOf('ForestProfile.watch(applyAccountNickname)') > game.indexOf('adapter.load().then'));
});
