// In-memory UI contract tests only: no real accounts, DB, or network writes.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const frontend = path.join(__dirname, '../src/frontend');
const source = fs.readFileSync(path.join(frontend, 'suin/app.js'), 'utf8');
const html = fs.readFileSync(path.join(frontend, 'suin/index.html'), 'utf8');
const editor = source.slice(source.indexOf('function openProfileEditor()'), source.indexOf('function showSignupEligibilityGuidance('));
const resume = source.slice(source.indexOf('async function resumeAuthenticatedAccount()'), source.indexOf('$("#login-form").addEventListener("submit"'));
const submit = source.slice(source.indexOf('$("#profile-editor-form")?.addEventListener("submit"'), source.indexOf("$$('.inner-step-tabs"));

function profileFlow({ search = '?account=profile', failure, storageBlocked = false } = {}) {
  const requests = [], screens = [], modes = [], notices = [], revisions = [];
  const elements = new Map();
  const $ = selector => {
    if (!elements.has(selector)) elements.set(selector, {
      value: '', hidden: true, open: false, focused: false,
      focus() { this.focused = true; },
      addEventListener(type, callback) { this[type] = callback; },
      getAttribute() { return null; },
    });
    return elements.get(selector);
  };
  const profile = { id: 7, name: '시험숲지기', birthday: '1986-01-01', gender: 'FEMALE' };
  const state = { token: null, userProfile: null, accountRecovery: null };
  const context = vm.createContext({
    URLSearchParams, Array, Date, JSON, Error, String,
    window: { location: { search }, localStorage: { setItem: (key, value) => {
      if (storageBlocked) throw new Error('Storage blocked');
      revisions.push({ key, value });
    } } },
    document: { body: { classList: { add() {}, remove() {} } } },
    $, state, openingAccountProfile: new URLSearchParams(search).get('account') === 'profile',
    showStep: step => screens.push(step),
    showAuthMode: (mode, options) => modes.push({ mode, options }),
    showMessage: (message, kind) => notices.push({ message, kind }),
    showAccountRecovery: () => notices.push({ recovery: true }),
    syncLifestyleAvatar() {}, getAgeFromBirth: () => 40,
    setFormBusy: () => () => {}, isLocalPreview: () => false,
    api: async (url, options = {}) => {
      const request = { url, method: options.method || 'GET' };
      if (options.body) request.body = JSON.parse(options.body);
      requests.push(request);
      if (failure) throw failure;
      if (url === '/auth/token/refresh') return { access_token: 'memory-only-test-token' };
      if (url === '/users/me') return { ...profile, ...(request.body || {}) };
      throw new Error(`Unexpected account-profile request: ${url}`);
    },
  });
  vm.runInContext(editor + '\n' + resume + '\n' + submit, context);
  return { context, state, profile, $, requests, screens, modes, notices, revisions };
}

async function submitName(flow, name) {
  flow.state.token = 'memory-only-test-token';
  flow.state.userProfile = { ...flow.profile };
  flow.context.openProfileEditor();
  flow.$('#profile-name').value = name;
  const form = flow.$('#profile-editor-form');
  await form.submit({ preventDefault() {}, currentTarget: form });
}

test('profile link restores only the same-origin account session and opens canonical name editor', async () => {
  const flow = profileFlow();
  await flow.context.resumeAccountProfileEntry();
  assert.deepEqual(flow.requests, [
    { url: '/auth/token/refresh', method: 'GET' },
    { url: '/users/me', method: 'GET' },
  ]);
  assert.equal(flow.$('#profile-editor').hidden, false);
  assert.equal(flow.$('#profile-name').value, flow.profile.name);
  assert.equal(flow.$('#profile-name').focused, true);
  assert.equal(flow.revisions.length, 0);
  assert.match(source, /syncLifestyleAvatar\(\);\s+if \(showRequestedAccountProfile\(\)\) return;\s+const consents/);
});

test('only exact account=profile triggers profile session restoration', async () => {
  for (const search of ['', '?account=https://example.test', '?account=/profile', '?account=Profile']) {
    const flow = profileFlow({ search });
    await flow.context.resumeAccountProfileEntry();
    assert.equal(flow.requests.length, 0);
    assert.equal(flow.context.showRequestedAccountProfile(), false);
    assert.equal(flow.$('#profile-editor').hidden, true);
  }
});

test('unsigned users stay at login without opening an editable profile', async () => {
  for (const failure of [Object.assign(new Error('Refresh token is missing.'), { status: 401 }), Object.assign(new Error('Provided invalid token.'), { status: 400 })]) {
    const flow = profileFlow({ failure });
    await flow.context.resumeAccountProfileEntry();
    assert.equal(flow.state.token, null);
    assert.equal(flow.$('#profile-editor').hidden, true);
    assert.equal(flow.requests.length, 1);
    assert.match(flow.notices[0].message, /로그인하면 개인정보 수정/);
  }
});

test('session server failures are not mislabeled as logout and never open the profile', async () => {
  const flow = profileFlow({ failure: Object.assign(new Error('서버 연결 실패'), { status: 503 }) });
  await flow.context.resumeAccountProfileEntry();
  assert.equal(flow.$('#profile-editor').hidden, true);
  assert.equal(flow.requests.length, 1);
  assert.equal(flow.notices[0].message, '서버 연결 실패');
});

test('name edits PATCH canonical user name and broadcast only a timestamp invalidation', async () => {
  const flow = profileFlow();
  await submitName(flow, '  새숲지기  ');
  assert.deepEqual(flow.requests, [{
    url: '/users/me', method: 'PATCH',
    body: { name: '새숲지기', birthday: flow.profile.birthday, gender: flow.profile.gender },
  }]);
  assert.equal(flow.state.userProfile.name, '새숲지기');
  assert.equal(flow.state.userProfile.birthday, flow.profile.birthday);
  assert.equal(flow.state.userProfile.gender, flow.profile.gender);
  assert.equal(flow.$('#eligibility-birth-date').value, flow.profile.birthday);
  assert.equal(flow.$('#gender').value, flow.profile.gender);
  assert.match(flow.notices[0].message, /닉네임은 당근의 숲에도 반영/);
  assert.equal(flow.revisions.length, 1);
  assert.equal(flow.revisions[0].key, 'gandang-account-profile-revision');
  assert.match(flow.revisions[0].value, /^\d+$/);
  assert.equal(flow.$('#profile-editor').hidden, true);
});

test('empty original name remains optional and invalid names never call the account API', async () => {
  for (const name of ['', ' ', '가', '가'.repeat(21)]) {
    const flow = profileFlow();
    await submitName(flow, name);
    assert.equal(flow.requests.length, 0);
    assert.equal(flow.revisions.length, 0);
    assert.equal(flow.$('#profile-editor-message').hidden, false);
    assert.match(flow.$('#profile-editor-message').textContent, /닉네임은 2~20자로/);
  }
  const optional = profileFlow();
  optional.profile.name = null;
  await submitName(optional, '');
  assert.equal(optional.requests.length, 1);
  assert.equal('name' in optional.requests[0].body, false);
});

test('failed save preserves editor input without invalidation; blocked storage does not reject successful save', async () => {
  const failed = profileFlow({ failure: Object.assign(new Error('저장 실패'), { status: 503 }) });
  await submitName(failed, '새숲지기');
  assert.equal(failed.revisions.length, 0);
  assert.equal(failed.state.userProfile.name, failed.profile.name);
  assert.equal(failed.$('#profile-editor').hidden, false);
  assert.equal(failed.$('#profile-name').value, '새숲지기');
  const blocked = profileFlow({ storageBlocked: true });
  await submitName(blocked, '새숲지기');
  assert.equal(blocked.state.userProfile.name, '새숲지기');
  assert.equal(blocked.$('#profile-editor').hidden, true);
});

test('profile entry requires authentication and legacy forest outfit saving cannot edit names', () => {
  const flow = profileFlow();
  flow.context.openProfileEditor();
  assert.equal(flow.$('#profile-editor').hidden, true);
  assert.deepEqual(flow.screens, [2]);
  assert.match(html, /id="profile-name" minlength="2" maxlength="20" autocomplete="nickname"/);
  assert.match(html, /<label for="profile-name">닉네임 \(선택\)<\/label>/);
  assert.doesNotMatch(html + source, /표시 이름/);
  assert.match(html, /href="\/forest"/);
  const legacyHtml = fs.readFileSync(path.join(frontend, 'index.html'), 'utf8');
  const legacyJs = fs.readFileSync(path.join(frontend, 'app.js'), 'utf8');
  assert.doesNotMatch(legacyHtml + legacyJs, /forest-display-name/);
  assert.match(legacyJs, /const openingAccountProfile =/);
  const forestJs = fs.readFileSync(path.join(frontend, 'forest-game.js'), 'utf8');
  const outfitSave = forestJs.slice(forestJs.indexOf('$("#avatar-studio-save").addEventListener'), forestJs.indexOf('$("#asset-dock").addEventListener'));
  assert.doesNotMatch(outfitSave, /state\.avatar\.name\s*=/);
  assert.match(outfitSave, /state\.avatar\.cosmetics/);
});
