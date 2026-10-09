const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../src/frontend/challenge-v2.js'), 'utf8');
const app = fs.readFileSync(path.join(__dirname, '../src/frontend/app.js'), 'utf8');
const settled = () => new Promise(resolve => setImmediate(resolve));

async function widget({ authenticated = true, enrolled = true, hash = '', requestHook, initialToken } = {}) {
  const handlers = {}, requests = [], message = { classList: { add() {} } }, section = { hidden: true };
  const root = {
    hidden: true, innerHTML: '', parentElement: { matches: () => false },
    addEventListener: (type, listener) => { handlers[type] = listener; },
    querySelector: selector => selector === '[data-message]' ? message : selector === '[data-settings]' ? section : { focus() {} },
  };
  const document = { querySelector: () => root, addEventListener() {}, documentElement: { classList: { add() {} } } };
  const window = { addEventListener() {}, dispatchEvent() {}, challengeV2TokenProvider: () => initialToken };
  vm.runInNewContext(source, {
    document, window, location: { hash }, setTimeout: () => 0, clearTimeout() {}, FormData: class {}, CustomEvent: class {},
    fetch: async (url, options) => {
      requests.push(url);
      if (requestHook) {
        const response = await requestHook(url, options);
        if (response) return response;
      }
      if (url.includes('capabilities')) return { json: async () => ({ data: { enabled: true } }) };
      if (url.includes('refresh')) return { ok: authenticated, status: authenticated ? 200 : 401, json: async () => ({ access_token: 'synthetic' }) };
      return { ok: true, json: async () => ({ data: { enrolled, items: [], preferences: {} } }) };
    },
  });
  await settled();
  return { root, handlers, requests, message, section };
}

test('signed-out users get a return-aware login link, not an unsavable settings form', async () => {
  const { root, message, requests } = await widget({ authenticated: false });
  assert.match(root.innerHTML, /href="\/\?returnTo=forest-challenges"/);
  assert.doesNotMatch(root.innerHTML, /data-preferences/);
  assert.match(message.textContent, /로그인/);
  assert.equal(requests.some(url => url.endsWith('/today')), false);
});

test('authentication outages are not mistaken for a signed-out user or writable setup', async () => {
  const { root, message } = await widget({ requestHook: async url => url.includes('refresh')
    ? { ok: false, status: 503, json: async () => { throw new Error('non-JSON outage'); } } : null });
  assert.doesNotMatch(root.innerHTML, /data-preferences|v2-setup-link/);
  assert.match(message.textContent, /새로고침/);
});

test('the backend invalid refresh cookie response offers login without loading a plan', async () => {
  const { root, message, requests } = await widget({ requestHook: async url => url.includes('refresh')
    ? { ok: false, status: 400, json: async () => ({ detail: 'Provided invalid token.' }) } : null });
  assert.match(root.innerHTML, /href="\/\?returnTo=forest-challenges"/);
  assert.doesNotMatch(root.innerHTML, /data-preferences/);
  assert.match(message.textContent, /로그인/);
  assert.equal(requests.some(url => url.endsWith('/today')), false);
});

test('unrecognized refresh 400 and validation failures remain connection errors', async () => {
  for (const [status, detail] of [[400, 'Bad request.'], [422, [{ loc: ['cookie', 'refresh_token'], type: 'missing' }]]]) {
    const { root, message, requests } = await widget({ requestHook: async url => url.includes('refresh')
      ? { ok: false, status, json: async () => ({ detail }) } : null });
    assert.doesNotMatch(root.innerHTML, /data-preferences|v2-setup-link/);
    assert.match(message.textContent, /새로고침/);
    assert.equal(requests.some(url => url.endsWith('/today')), false);
  }
});

test('invalid refresh after an expired access token stops retrying and offers login', async () => {
  const { root, requests } = await widget({ initialToken: 'expired-test-token', requestHook: async url => {
    if (url.endsWith('/today')) return { ok: false, status: 401, json: async () => ({ detail: 'expired' }) };
    if (url.includes('refresh')) return { ok: false, status: 400, json: async () => ({ detail: 'Provided invalid token.' }) };
  } });
  assert.equal(requests.filter(url => url.includes('refresh')).length, 1);
  assert.equal(requests.filter(url => url.endsWith('/today')).length, 1);
  assert.match(root.innerHTML, /v2-setup-link/);
  assert.doesNotMatch(root.innerHTML, /data-preferences/);
});

test('expired access token refreshes once via the same-origin cookie then retries', async () => {
  const authorization = [];
  const { root, requests } = await widget({ initialToken: 'expired-test-token', requestHook: async (url, options) => {
    if (url.endsWith('/today')) {
      authorization.push(options.headers.Authorization);
      if (authorization.length === 1) return { ok: false, status: 401, json: async () => ({ detail: 'expired' }) };
    }
    if (url.includes('refresh')) assert.equal(options.credentials, 'same-origin');
  } });
  assert.deepEqual(authorization, ['Bearer expired-test-token', 'Bearer synthetic']);
  assert.equal(requests.filter(url => url.includes('refresh')).length, 1);
  assert.match(root.innerHTML, /data-preferences/);
});

test('a repeated unauthorized response cannot cause an infinite refresh loop', async () => {
  const { root, requests } = await widget({ initialToken: 'expired-test-token', requestHook: async url => url.endsWith('/today')
    ? { ok: false, status: 401, json: async () => ({ detail: '로그인이 만료됐어요.' }) } : null });
  assert.equal(requests.filter(url => url.includes('refresh')).length, 1);
  assert.match(root.innerHTML, /v2-setup-link/);
  assert.doesNotMatch(root.innerHTML, /data-preferences/);
});

test('settings open button toggles existing form without discarding edits', async () => {
  const { root, handlers, section } = await widget();
  assert.match(root.innerHTML, /aria-expanded="false"/);
  const before = root.innerHTML;
  const button = { setAttribute(key, value) { this[key] = value; } };
  const event = { target: { closest: selector => selector === '[data-open-settings]' ? button : null } };
  await handlers.click(event);
  assert.equal(section.hidden, false);
  assert.equal(button['aria-expanded'], 'true');
  assert.equal(button.textContent, '다시 설정 닫기');
  assert.equal(root.innerHTML, before);
  await handlers.click(event);
  assert.equal(section.hidden, true);
});

test('first setup and a return from login open settings immediately', async () => {
  for (const options of [{ enrolled: false }, { hash: '#daily-settings' }]) {
    const { root } = await widget(options);
    assert.match(root.innerHTML, /aria-expanded="true"/);
    assert.match(root.innerHTML, /data-preferences/);
    assert.doesNotMatch(root.innerHTML, /data-settings hidden/);
  }
});

test('plain-language copy retains privacy, optional photos and medical boundaries', async () => {
  const { root } = await widget({ enrolled: false });
  assert.doesNotMatch(root.innerHTML, /\b(?:AI|V2|T1|T2|T3)\b/);
  for (const text of ['최대 7일', '선택', '보관한 사진을 삭제', '외부 자동 분석 서비스로 보내지', '진단·처방']) {
    assert.ok(root.innerHTML.includes(text), text);
  }
});

test('forest return uses a server safety gate in the current UI', () => {
  assert.match(app, /async function returnToForestSettings/);
  assert.match(app, /await api\("\/challenge-v2\/today", \{ method: "GET" \}\)/);
  assert.match(app, /window.location.assign\("\/forest#daily-settings"\)/);
});
