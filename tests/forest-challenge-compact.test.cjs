const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../src/frontend/challenge-v2.js'), 'utf8');
const forest = fs.readFileSync(path.join(__dirname, '../src/frontend/forest.html'), 'utf8');
const settled = () => new Promise(resolve => setImmediate(resolve));
const voidTags = new Set(['area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr']);

// This small DOM double preserves nesting so hidden detail content cannot pass
// assertions meant for the visible quest summary. No browser/account is used.
function element(tag = 'div', attrs = {}, parentElement = null) {
  const node = {
    tag, attrs, parentElement, children: [], listeners: {}, _html: '',
    classList: { add() {}, remove() {}, toggle() {} },
    get dataset() {
      return Object.fromEntries(Object.entries(this.attrs).filter(([key]) => key.startsWith('data-'))
        .map(([key, value]) => [key.slice(5).replace(/-([a-z])/g, (_, letter) => letter.toUpperCase()), value]));
    },
    get hidden() { return 'hidden' in this.attrs; },
    set hidden(value) { if (value) this.attrs.hidden = ''; else delete this.attrs.hidden; },
    get open() { return 'open' in this.attrs; },
    set open(value) { if (value) this.attrs.open = ''; else delete this.attrs.open; },
    get disabled() { return 'disabled' in this.attrs; },
    set disabled(value) { if (value) this.attrs.disabled = ''; else delete this.attrs.disabled; },
    get name() { return this.attrs.name || ''; },
    get checked() { return 'checked' in this.attrs; },
    set checked(value) { if (value) this.attrs.checked = ''; else delete this.attrs.checked; },
    get textContent() { return this.children.map(child => typeof child === 'string' ? child : child.textContent).join(''); },
    set textContent(value) { this.children = [String(value)]; },
    get innerHTML() { return this._html; },
    set innerHTML(value) { this._html = value; this.children = []; parse(value, this); },
    setAttribute(key, value) { this.attrs[key] = String(value); },
    getAttribute(key) { return this.attrs[key] ?? null; },
    hasAttribute(key) { return key in this.attrs; },
    removeAttribute(key) { delete this.attrs[key]; },
    addEventListener(type, listener) { this.listeners[type] = listener; },
    matches(selector) {
      return selector.split(',').some(part => {
        part = part.trim();
        const excluded = [...part.matchAll(/:not\(([^)]+)\)/g)].map(match => match[1]);
        if (excluded.some(value => this.matches(value))) return false;
        part = part.replace(/:not\([^)]+\)/g, '').replace(/:first-child/g, '');
        const tagMatch = part.match(/^[a-z][\w-]*/i);
        if (tagMatch && this.tag !== tagMatch[0]) return false;
        const id = part.match(/#([\w-]+)/);
        if (id && this.attrs.id !== id[1]) return false;
        for (const [, name] of part.matchAll(/\.([\w-]+)/g)) {
          if (!(this.attrs.class || '').split(/\s+/).includes(name)) return false;
        }
        for (const [, key, , value] of part.matchAll(/\[([^\s=\]]+)(?:=(['"]?)([^\]'"]*)\2)?\]/g)) {
          if (!(key in this.attrs) || (value !== undefined && this.attrs[key] !== value)) return false;
        }
        return true;
      });
    },
    querySelectorAll(selector) {
      const groups = selector.split(',').map(group => group.trim().split(/\s+(?![^[]*\])/));
      return descendants(this).filter(candidate => groups.some(parts => {
        if (!candidate.matches(parts.at(-1))) return false;
        let ancestor = candidate.parentElement;
        for (let index = parts.length - 2; index >= 0; index--) {
          while (ancestor && !ancestor.matches(parts[index])) ancestor = ancestor.parentElement;
          if (!ancestor) return false;
          ancestor = ancestor.parentElement;
        }
        return true;
      }));
    },
    querySelector(selector) { return this.querySelectorAll(selector)[0] || null; },
    closest(selector) { return this.matches(selector) ? this : this.parentElement?.closest(selector) || null; },
    contains(candidate) { return candidate === this || descendants(this).includes(candidate); },
    focus() { this.focused = true; },
    scrollIntoView() {},
    insertAdjacentHTML(position, value) { parse(value, this); },
  };
  return node;
}

function descendants(node) {
  return node.children.flatMap(child => typeof child === 'string' ? [] : [child, ...descendants(child)]);
}

function parse(html, root) {
  const stack = [root];
  for (const match of html.matchAll(/<!--[\s\S]*?-->|<\/?([\w-]+)\b([^>]*)>|([^<]+)/g)) {
    if (match[0].startsWith('<!--')) continue;
    if (match[3]) { stack.at(-1).children.push(match[3]); continue; }
    if (match[0].startsWith('</')) { if (stack.length > 1) stack.pop(); continue; }
    const attrs = {};
    for (const [, key, double, single, unquoted] of match[2].matchAll(/([^\s=/>]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+)))?/g)) {
      attrs[key] = double ?? single ?? unquoted ?? '';
    }
    const child = element(match[1], attrs, stack.at(-1));
    stack.at(-1).children.push(child);
    if (!voidTags.has(child.tag) && !match[0].endsWith('/>')) stack.push(child);
  }
}

function visibleText(node) {
  if (typeof node === 'string') return node;
  if (node.hidden) return '';
  if (node.tag === 'details' && !node.open) return visibleText(node.children.find(child => child.tag === 'summary') || '');
  return node.children.map(visibleText).join(' ').replace(/\s+/g, ' ').trim();
}

function assignment(id, overrides = {}) {
  return {
    id, status: 'assigned', completed_sessions: 0, total_quantity: 0,
    sessions: [], evidence: [], verification_status: 'not_required',
    goal: {
      title: `오늘 활동 ${id}`, domain: 'activity', difficulty: 'E', proof_type: 'T3',
      family_id: 'A01', goal_unit: 'minute', per_session_quantity: 5,
      target_sessions: 1, required_uploads: 0, safety: `무리하지 않기 ${id}`,
      sources: [{ title: `확인된 출처 ${id}`, url: `https://example.test/source/${id}` }],
    },
    ...overrides,
  };
}

function today(overrides = {}) {
  const diet = assignment(1); diet.goal.domain = 'diet'; diet.goal.family_id = 'D03'; diet.goal.goal_unit = 'count';
  const activity = assignment(2);
  const routine = assignment(3); routine.goal.domain = 'routine'; routine.goal.family_id = 'H02'; routine.goal.goal_unit = 'count';
  return {
    enrolled: true, day_id: 1, completed: 0, carrot_balance: 100, chest_issued: false,
    preferences: {}, items: [diet, activity, routine],
    proof_mix_exception_reason: ['real_visual_review_unavailable'], substitutions: [],
    ...overrides,
  };
}

async function widget({ forestView = true, plan = today(), authenticated = true, hash = '', requestHook, storedCompletions = null } = {}) {
  const parent = element('section', { id: 'quest-panel' });
  const root = element('div', { 'data-challenge-v2': '', ...(forestView ? { 'data-challenge-v2-view': 'forest' } : {}) }, parent);
  parent.children.push(root);
  const settingsButton = element('button', { id: 'forest-quest-settings', hidden: '' });
  const windowHandlers = {}, requests = [], dispatchedEvents = [], storage = new Map();
  if (storedCompletions) storage.set('gandang.challenge-v2.mvp-completions.v1', JSON.stringify(storedCompletions));
  const document = {
    hidden: false, activeElement: null, documentElement: element('html'),
    querySelector: selector => selector === '[data-challenge-v2]' ? root : selector === '#forest-quest-settings' ? settingsButton : null,
    getElementById: id => id === 'forest-quest-settings' ? settingsButton : null,
    addEventListener() {},
  };
  class TestFormData {
    constructor(form) { this.values = form.values || {}; }
    [Symbol.iterator]() { return Object.entries(this.values)[Symbol.iterator](); }
    get(key) { return this.values[key]; }
  }
  const window = { addEventListener: (type, handler) => { windowHandlers[type] = handler; }, dispatchEvent(event) { dispatchedEvents.push(event); windowHandlers[event.type]?.(event); },
    localStorage: { getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value) } };
  vm.runInNewContext(source, {
    document, window, location: { hash }, FormData: TestFormData,
    clearTimeout() {}, setTimeout() { return 1; },
    CustomEvent: class { constructor(type, init = {}) { this.type = type; this.detail = init.detail; } },
    Event: class { constructor(type) { this.type = type; } },
    fetch: async (url, options = {}) => {
      requests.push({ url, options });
      if (requestHook) {
        const result = await requestHook(url, options);
        if (result) return result;
      }
      if (url.includes('capabilities')) return { json: async () => ({ data: { enabled: true } }) };
      if (url.includes('refresh')) return { ok: authenticated, status: authenticated ? 200 : 401, json: async () => ({ access_token: 'synthetic-test-only' }) };
      return { ok: true, json: async () => ({ data: plan }) };
    },
  });
  await settled();
  return { root, settingsButton, requests, windowHandlers, document, storage, dispatchedEvents };
}

test('only the forest opts into the compact challenge view', () => {
  assert.match(forest, /data-challenge-v2\s+data-challenge-v2-view="forest"/);
  const mvp = fs.readFileSync(path.join(__dirname, '../src/frontend/index.html'), 'utf8');
  assert.doesNotMatch(mvp, /data-challenge-v2-view="forest"/);
});

test('enrolled forest shows three short quests while preserving every original detail', async () => {
  const { root } = await widget();
  const cards = root.querySelectorAll('.v2-quest-card');
  assert.equal(cards.length, 3);
  assert.ok(root.innerHTML.indexOf('class="v2-compact-cards"') < root.innerHTML.indexOf('id="forest-quest-settings"'));
  assert.match(root.querySelector('#forest-quest-settings').textContent, /나에게 맞게 다시 설정하기/);
  for (const [index, card] of cards.entries()) {
    const id = index + 1;
    const details = card.querySelector('.v2-quest-details');
    assert.ok(details, 'each short quest must retain an expandable detail section');
    assert.equal(details.tag, 'details');
    assert.equal(details.open, false);
    assert.match(details.querySelector('summary').textContent, /자세히 보기/);
    assert.match(visibleText(card), new RegExp(`오늘 활동 ${id}`));
    assert.match(visibleText(card), /인증하기/);
    assert.doesNotMatch(visibleText(card), /무리하지 않기|회차 저장|근거·확인 범위|당근 10개 지급/);
    assert.match(details.textContent, new RegExp(`무리하지 않기 ${id}`));
    assert.ok(details.querySelector(`[data-session="${id}"]`));
    assert.ok(details.querySelector(`[data-alternatives="${id}"]`));
    assert.equal(details.querySelector('a').getAttribute('href'), `https://example.test/source/${id}`);
  }
  assert.doesNotMatch(visibleText(root), /당뇨 예방 챌린지|나에게 맞게 설정하기|계정 당근|담당자가 사진 확인/);
});

test('direct-record quests save an honest self-attestation and optional detail with one certify click', async () => {
  const { root, requests } = await widget();
  const before = requests.length;
  const card = root.querySelector('[data-certify="2"]').closest('.v2-quest-card');
  card.querySelector('[name="note"]').value = '저녁 산책 후 몸이 가벼웠어요.';
  await root.listeners.click({ target: card.querySelector('[data-certify]') });
  const writes = requests.slice(before).filter(request => request.url.includes('/sessions/'));
  assert.equal(writes.length, 1);
  assert.equal(writes[0].options.method, 'PUT');
  const payload = JSON.parse(writes[0].options.body);
  assert.equal(payload.done, true);
  assert.equal(payload.quantity, 5);
  assert.equal(payload.note, '저녁 산책 후 몸이 가벼웠어요.');
  assert.equal(Number.isNaN(Date.parse(payload.performed_at)), false);
});

test('three completed quests can be repeated without increasing their displayed session count', async () => {
  const { root, storage } = await widget();
  for (const id of ['1', '2', '3']) await root.listeners.click({ target: root.querySelector(`[data-certify="${id}"]`) });
  const repeat = root.querySelector('[data-repeat-quests]');
  assert.ok(repeat);
  assert.equal(repeat.textContent.trim(), '오늘의 퀘스트 다시 하기');
  await root.listeners.click({ target: repeat });
  assert.equal(root.querySelectorAll('[data-certify]').filter(button => button.textContent.trim() === '인증하기').length, 3);
  await root.listeners.click({ target: root.querySelector('[data-certify="1"]') });
  const saved = JSON.parse(storage.get('gandang.challenge-v2.mvp-completions.v1'));
  assert.ok(saved['1:cycle-1:1']);
  assert.equal(root.querySelector('[data-certify="1"]').textContent.trim(), '인증완료');
});

test('MVP certify immediately completes photo and measurement cards while preserving optional detail locally', async () => {
  const photo = assignment(1); photo.goal.proof_type = 'T2'; photo.goal.required_uploads = 1;
  const drink = assignment(2); drink.goal.family_id = 'H02'; drink.goal.goal_unit = 'count';
  const { root, requests, storage } = await widget({ plan: today({ items: [photo, drink, assignment(3)] }) });
  const before = requests.length;
  await root.listeners.click({ target: root.querySelector('[data-certify="1"]') });
  await root.listeners.click({ target: root.querySelector('[data-certify="2"]') });
  const laterNote = root.querySelector('[data-session="1"] [name="note"]');
  laterNote.value = '채소가 있는 점심을 먹었어요.';
  root.listeners.input({ target: laterNote });
  assert.equal(requests.length, before);
  assert.equal(root.querySelector('[data-certify="1"]').textContent.trim(), '인증완료');
  assert.equal(root.querySelector('[data-certify="2"]').textContent.trim(), '인증완료');
  const saved = JSON.parse(storage.get('gandang.challenge-v2.mvp-completions.v1'));
  assert.equal(saved['1:cycle-0:1'].note, '채소가 있는 점심을 먹었어요.');
});

test('confirmed personal water goal shows 200mL cups, persists taps, then certifies once', async () => {
  const water = assignment(3);
  water.goal.domain = 'routine';
  water.goal.family_id = 'H02';
  water.goal.proof_type = 'T3';
  water.goal.goal_unit = 'cup';
  water.goal.target_sessions = 1;
  water.goal.per_session_quantity = 4;
  water.goal.water_mission_version = 'cup-v1';
  water.goal.water_goal_status = 'confirmed';
  water.goal.water_cup_ml = 200;
  water.goal.water_goal_cups = 4;
  const { root, requests, storage, dispatchedEvents } = await widget({ plan: today({ items: [assignment(1), assignment(2), water] }) });
  assert.match(visibleText(root), /200mL 컵 4개 · 0\/4/);
  assert.equal(root.querySelector('[data-certify="3"]').disabled, true);
  assert.equal(root.querySelectorAll('.v2-water-icon').length, 4);
  assert.equal(root.querySelector('[data-water-cup="3"][data-cup-index="1"]').getAttribute('aria-label'), '물컵 1/4 체크하기');
  for (const index of [1, 2, 3]) await root.listeners.click({ target: root.querySelector(`[data-water-cup="3"][data-cup-index="${index}"]`) });
  assert.match(visibleText(root), /200mL 컵 4개 · 3\/4/);
  assert.deepEqual(JSON.parse(JSON.stringify(dispatchedEvents.filter(event => event.type === 'forest-water-cup-progress').at(-1).detail)), {
    assignmentId: 3,
    completionKey: '1:cycle-0:3',
    checked: 3,
    total: 4,
    cupMl: 200,
    complete: false,
  });
  await root.listeners.click({ target: root.querySelector('[data-refresh]') });
  assert.match(visibleText(root), /200mL 컵 4개 · 3\/4/);
  await root.listeners.click({ target: root.querySelector('[data-water-cup="3"][data-cup-index="4"]') });
  assert.equal(root.querySelector('[data-certify="3"]').disabled, false);
  assert.equal(dispatchedEvents.filter(event => event.type === 'forest-water-cup-progress').at(-1).detail.complete, true);
  const before = requests.length;
  await root.listeners.click({ target: root.querySelector('[data-certify="3"]') });
  const writes = requests.slice(before).filter(request => request.url.includes('/assignments/3/sessions/1'));
  assert.equal(writes.length, 1);
  assert.deepEqual(JSON.parse(writes[0].options.body), {
    performed_at: JSON.parse(writes[0].options.body).performed_at,
    done: true,
    note: '직접 인증 완료',
    quantity: 4,
    intake_ml: 800,
  });
  await root.listeners.click({ target: root.querySelector('[data-certify="3"]') });
  assert.equal(requests.slice(before).filter(request => request.url.includes('/assignments/3/sessions/1')).length, 1);
  const saved = JSON.parse(storage.get('gandang.challenge-v2.water-cups.v1'));
  assert.deepEqual(saved['1:cycle-0:3:cups'], [1, 2, 3, 4]);
});

test('unconfirmed water cards do not display numeric cup controls', async () => {
  const water = assignment(3);
  water.goal.domain = 'routine';
  water.goal.family_id = 'H02';
  water.goal.water_mission_version = 'cup-v1';
  water.goal.water_goal_status = 'unconfirmed';
  water.goal.water_cup_ml = 200;
  water.goal.water_goal_cups = null;
  const { root } = await widget({ plan: today({ items: [assignment(1), assignment(2), water] }) });
  assert.equal(root.querySelectorAll('[data-water-cup]').length, 0);
  assert.doesNotMatch(visibleText(root), /200mL 컵/);
});

test('a server-completed MVP quest keeps an editable optional note under details', async () => {
  const completed = assignment(1, { status: 'completed', completed_sessions: 1, sessions: [{ index: 1 }] });
  const initial = { '1:1': { assignmentId: 1, domain: 'activity', note: '처음 기록', completedAt: '2026-09-08T00:00:00.000Z' } };
  const { root, storage } = await widget({ plan: today({ items: [completed, assignment(2), assignment(3)] }), storedCompletions: initial });
  const note = root.querySelector('[data-mvp-note="1"]');
  assert.ok(note);
  assert.equal(note.textContent, '처음 기록');
  note.value = '완료 후에 추가한 기록';
  root.listeners.input({ target: note });
  const saved = JSON.parse(storage.get('gandang.challenge-v2.mvp-completions.v1'));
  assert.equal(saved['1:cycle-0:1'].note, '완료 후에 추가한 기록');
});

test('compact quests expose one diet, activity and drink label with three distinct garden celebrations', async () => {
  const water = assignment(1); water.goal.domain = 'routine';
  const diet = assignment(2); diet.goal.domain = 'diet';
  const activity = assignment(3); activity.goal.domain = 'activity';
  const { root } = await widget({ plan: today({ items: [water, diet, activity] }) });
  assert.deepEqual(root.querySelectorAll('.v2-domain-badge').map(node => node.textContent.trim()), ['식단', '운동', '음료']);
  assert.match(source, /당근 밭에 물을 주었습니다/);
  assert.match(source, /당근 밭에 거름을 주었습니다/);
  assert.match(source, /당근 밭에 잡초를 제거했습니다/);
  for (const name of ['challenge-water-team-v171.webp', 'challenge-compost-team-v171.webp', 'challenge-weeding-team-v171.webp']) {
    assert.ok(fs.existsSync(path.join(__dirname, `../src/frontend/assets/${name}`)));
  }
});

test('only server-completed assignments show certification complete; review stays pending', async () => {
  const plan = today({ items: [
    assignment(1, { status: 'completed', completed_sessions: 1, sessions: [{ index: 1 }] }),
    assignment(2, { status: 'submitted', completed_sessions: 1, sessions: [{ index: 1 }], verification_status: 'pending' }),
    assignment(3, { status: 'in_progress', completed_sessions: 1, sessions: [{ index: 1 }], verification_status: 'needs_retry' }),
  ] });
  const { root } = await widget({ plan });
  const cards = root.querySelectorAll('.v2-quest-card');
  const complete = cards[0].querySelector('[data-certify]');
  assert.equal(complete.textContent.trim(), '인증완료');
  assert.equal(complete.disabled, true);
  assert.match(visibleText(cards[1]), /확인 중/);
  assert.doesNotMatch(visibleText(cards[1]), /인증완료/);
  assert.doesNotMatch(visibleText(cards[2]), /인증완료/);
  assert.match(cards[1].querySelector('.v2-quest-details').textContent, /완료·보상은 확인 후 지급/);
  assert.match(cards[2].querySelector('.v2-quest-details').textContent, /다시 올리거나 사진 없이 기록/);
});

test('photo uploads, saved sessions, safety and original sources survive compact presentation', async () => {
  const photo = assignment(1, { sessions: [{ index: 1 }], completed_sessions: 1 });
  photo.goal.proof_type = 'T2';
  photo.goal.required_uploads = 1;
  photo.goal.target_sessions = 2;
  const { root } = await widget({ plan: today({ items: [photo, assignment(2), assignment(3)] }) });
  const details = root.querySelector('.v2-quest-details');
  assert.match(details.textContent, /회차 1 저장됨/);
  assert.equal(details.querySelectorAll('[data-session]').length, 1);
  assert.equal(details.querySelector('[data-session]').dataset.index, '2');
  assert.ok(details.querySelector('[data-upload="1"]'));
  assert.ok(details.querySelector('input[type="file"]'));
  assert.match(details.textContent, /사진으로 실제 섭취나 걷기 진위를 증명하지 않습니다/);
  assert.match(details.textContent, /무리하지 않기 1/);
});

test('full MVP and first setup retain the complete preferences interface', async () => {
  const full = await widget({ forestView: false });
  assert.ok(full.root.querySelector('[data-preferences]'));
  assert.equal(full.root.querySelectorAll('.v2-quest-card').length, 0);
  assert.match(full.root.textContent, /진단·처방/);
  assert.match(full.root.textContent, /최대 7일/);
  const firstSetup = await widget({ plan: today({ enrolled: false, items: [] }) });
  assert.ok(firstSetup.root.querySelector('[data-preferences]'));
  assert.equal(firstSetup.root.querySelectorAll('.v2-quest-card').length, 0);
  assert.doesNotMatch(firstSetup.root.textContent, /생활습관을 돌아보는 활동이에요/);
  assert.match(firstSetup.root.textContent, /최대 7일/);
  const { root } = await widget({ forestView: false });
  assert.equal(root.querySelectorAll('.v2-card').length, 3);
});

test('saving first setup loads the server plan and returns to three collapsed quests', async () => {
  let todayLoads = 0;
  const { root, requests } = await widget({
    requestHook: url => {
      if (url.endsWith('/today')) {
        todayLoads++;
        return { ok: true, json: async () => ({ data: todayLoads === 1 ? today({ enrolled: false, items: [] }) : today() }) };
      }
    },
  });
  assert.equal(root.querySelector('[data-settings]').hidden, false);
  const form = root.querySelector('[data-preferences]');
  form.values = { mode: 'balanced', max_difficulty: 'E', planned_meals: '1', sugary_drink_opportunities: '0' };
  form.querySelector('[name="transition_consent"]').checked = true;
  await root.listeners.submit({ target: form, preventDefault() {} });
  assert.equal(root.querySelectorAll('.v2-quest-card').length, 3);
  assert.equal(root.querySelectorAll('.v2-quest-details[open]').length, 0);
  assert.equal(root.querySelector('[data-settings]').hidden, true);
  assert.equal(root.querySelector('[data-compact-settings]').hidden, true);
  const settingsButton = root.querySelector('#forest-quest-settings');
  assert.ok(settingsButton);
  assert.equal(settingsButton.getAttribute('aria-expanded'), 'false');
  const save = requests.filter(request => request.url.endsWith('/preferences'));
  assert.equal(save.length, 1);
  assert.equal(save[0].options.method, 'PUT');
  assert.equal(JSON.parse(save[0].options.body).transition_consent, true);
  assert.equal(JSON.parse(save[0].options.body).planned_meals, 1);
  assert.equal(JSON.parse(save[0].options.body).fluid_restriction, true, 'safe setup defaults must survive saving');
  assert.equal(requests.filter(request => request.url.endsWith('/today')).length, 2);
  assert.ok(requests.filter(request => request.url.endsWith('/today')).every(request => request.options.method === 'POST'));
  assert.equal(requests.some(request => /\/sessions\/|\/evidence\//.test(request.url)), false);
});

test('settings below all three quests toggle the existing form and retain unsaved edits', async () => {
  const { root } = await widget();
  const form = root.querySelector('[data-preferences]');
  form.unsavedDraft = 'keep this edit';
  let settingsButton = root.querySelector('#forest-quest-settings');
  await root.listeners.click({ target: settingsButton });
  assert.equal(root.querySelector('[data-settings]').hidden, false);
  assert.equal(root.querySelector('[data-compact-settings]').hidden, false);
  assert.doesNotMatch(visibleText(root), /생활습관을 돌아보는 활동이에요/);
  assert.match(visibleText(root), /계정 당근/);
  assert.equal(settingsButton.getAttribute('aria-expanded'), 'true');
  assert.deepEqual(root.querySelectorAll('[data-quick-mode]').map(button => button.textContent.trim()), ['운동 위주', '식단 위주']);
  assert.equal(root.querySelector('[data-custom-mode]').textContent.trim(), '나만의 챌린지');
  assert.equal(root.querySelector('[data-custom-preferences]').hidden, true, 'details stay hidden until custom is selected');
  await root.listeners.click({ target: root.querySelector('[data-custom-mode]') });
  assert.equal(root.querySelector('[data-custom-preferences]').hidden, false);
  settingsButton = root.querySelector('#forest-quest-settings');
  await root.listeners.click({ target: settingsButton });
  assert.equal(root.querySelector('[data-preferences]'), form);
  assert.equal(form.unsavedDraft, 'keep this edit');
  assert.equal(root.querySelector('[data-settings]').hidden, true);
  assert.equal(settingsButton.getAttribute('aria-expanded'), 'false');
});

test('record submission waits for authoritative completion and preserves the existing endpoint payload', async () => {
  let finishRecording;
  const { root, requests } = await widget({
    requestHook: url => url.endsWith('/assignments/1/sessions/1')
      ? new Promise(resolve => { finishRecording = resolve; }) : null,
  });
  root.querySelector('[data-quest-details="1"]').open = true;
  const form = root.querySelector('[data-session="1"]');
  form.values = { performed_at: '2026-09-08T14:30', quantity: '5', done: 'on' };
  const saving = root.listeners.submit({ target: form, preventDefault() {} });
  await settled();
  assert.equal(root.querySelector('[data-certify="1"]').textContent.trim(), '인증하기');
  assert.equal(form.querySelector('button').disabled, true);
  const writes = requests.filter(request => request.url.includes('/sessions/'));
  assert.equal(writes.length, 1);
  assert.equal(writes[0].options.method, 'PUT');
  assert.deepEqual(JSON.parse(writes[0].options.body), {
    performed_at: '2026-09-08T05:30:00.000Z', quantity: 5, done: true,
  });
  finishRecording({ ok: true, json: async () => ({ data: today({ completed: 1, items: [
    assignment(1, { status: 'completed', completed_sessions: 1, total_quantity: 5, sessions: [{ index: 1 }] }),
    assignment(2), assignment(3),
  ] }) }) });
  await saving;
  assert.equal(root.querySelector('[data-certify="1"]').textContent.trim(), '인증완료');
  assert.equal(root.querySelector('[data-certify="1"]').disabled, true);
  assert.equal(root.querySelector('[data-quest-details="1"]').open, true);
  assert.match(root.querySelector('[data-message]').textContent, /저장했어요/);
});

test('refresh preserves the chosen open quest while unrelated quests remain collapsed', async () => {
  const { root, requests } = await widget();
  root.querySelector('[data-quest-details="2"]').open = true;
  await root.listeners.click({ target: root.querySelector('[data-refresh]') });
  assert.equal(root.querySelector('[data-quest-details="1"]').open, false);
  assert.equal(root.querySelector('[data-quest-details="2"]').open, true);
  assert.equal(root.querySelector('[data-quest-details="3"]').open, false);
  assert.equal(requests.filter(request => request.url.endsWith('/today')).length, 2);
});

test('forest signed-out and connection failure states never become writable compact quests', async () => {
  for (const options of [
    { authenticated: false },
    { requestHook: url => url.includes('refresh') ? { ok: false, status: 503, json: async () => ({}) } : null },
  ]) {
    const { root, requests } = await widget(options);
    assert.equal(root.querySelectorAll('.v2-quest-card').length, 0);
    assert.equal(root.querySelectorAll('[data-preferences]').length, 0);
    assert.match(root.querySelector('[data-message]').textContent, /로그인|새로고침/);
    assert.equal(requests.some(request => request.url.endsWith('/today')), false);
  }
});
