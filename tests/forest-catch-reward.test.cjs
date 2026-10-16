const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

const source = readFileSync(path.join(__dirname, '../src/frontend/forest-game.js'), 'utf8');

function setup({ waitForSave, withToast = true } = {}) {
  const listeners = new Map();
  const toast = { textContent: '', hidden: true };
  const labels = new Map([
    ['#carrot-balance', { textContent: '30' }],
    ['#preview-carrot-balance', { textContent: '30' }],
  ]);
  if (withToast) labels.set('#forest-catch-toast', toast);
  const state = { carrots: 30, avatar: { cosmetics: {} } };
  const saves = [];
  const sounds = [];
  const timers = new Map(), scheduled = [], cancelled = [];
  let now = 0, nextTimer = 0;
  const advance = milliseconds => {
    now += milliseconds;
    for (const [id, timer] of [...timers]) {
      if (timer.at > now) continue;
      timers.delete(id); timer.callback();
    }
  };
  const begin = source.indexOf('  let currentWildEncounter = null;');
  const end = source.indexOf('  window.addEventListener("forest-placement-confirm"', begin);
  assert.ok(begin >= 0 && end > begin, 'the production encounter handlers must be present');
  const context = vm.createContext({
    window: {
      addEventListener: (type, callback) => listeners.set(type, callback),
      setTimeout(callback, delay) {
        const id = ++nextTimer;
        timers.set(id, { callback, at: now + delay }); scheduled.push({ id, delay });
        return id;
      },
      clearTimeout(id) { cancelled.push(id); timers.delete(id); },
    },
    $: (selector) => labels.get(selector) || null,
    state,
    adapter: { mode: 'demo' },
    setStatus() {},
    playSfx: (name, options) => sounds.push({ name, ...options }),
    persist: async (message) => {
      saves.push({ carrots: state.carrots, message });
      if (waitForSave) await waitForSave;
    },
  });
  vm.runInContext(source.slice(begin, end), context);
  return { listeners, labels, state, saves, sounds, toast, timers, scheduled, cancelled, advance,
    currentEncounter: () => vm.runInContext('currentWildEncounter', context) };
}

test('manual, click and pet catches persist rabbit +1 or mouse +0 with the exact same species message', async () => {
  for (const encounter of [
    { species: 'rabbit', message: '토끼가 당근 1개를 놓고 갔습니다.', reward: 1 },
    { species: 'mouse', message: '쥐를 잡았습니다.', reward: 0 },
  ]) for (const source of [undefined, 'click', 'pet']) {
    const { listeners, labels, state, saves, sounds } = setup();
    assert.equal(labels.has('#profile-carrots'), false);
    await listeners.get('forest-rat-caught')({
      detail: { eventId: 7, amount: 5, species: encounter.species, source },
    });
    const expected = 30 + encounter.reward;
    assert.equal(state.carrots, expected);
    assert.equal(labels.get('#carrot-balance').textContent, String(expected));
    assert.equal(labels.get('#preview-carrot-balance').textContent, String(expected));
    assert.deepEqual(saves, [{ carrots: expected, message: encounter.message }]);
    assert.equal(sounds[0].name, 'rat-caught');
    assert.equal(sounds[0].rate, source === 'pet' ? 1.08 : 1);
  }
});

test('a catch without a species keeps the active rabbit encounter reward message', async () => {
  const { listeners, saves } = setup();
  listeners.get('forest-rat-appeared')({ detail: { eventId: 8, species: 'rabbit' } });
  await listeners.get('forest-rat-caught')({ detail: { eventId: 8, amount: 5 } });
  assert.deepEqual(saves, [{ carrots: 31, message: '토끼가 당근 1개를 놓고 갔습니다.' }]);
});

test('the matching spawn species outranks a conflicting species supplied by the catch event', async () => {
  for (const species of ['rabbit', 'mouse']) {
    const { listeners, state, saves, currentEncounter } = setup();
    listeners.get('forest-rat-appeared')({ detail: { eventId: 'spawn-1', species } });
    await listeners.get('forest-rat-caught')({ detail: { eventId: 'spawn-1', species: species === 'rabbit' ? 'mouse' : 'rabbit', amount: 999, source: 'pet' } });
    assert.equal(state.carrots, species === 'rabbit' ? 31 : 30);
    assert.equal(saves[0].message, species === 'rabbit' ? '토끼가 당근 1개를 놓고 갔습니다.' : '쥐를 잡았습니다.');
    assert.equal(currentEncounter(), null);
  }
});

test('incoming amount is ignored completely, including missing, invalid, exaggerated, or getter values', async () => {
  for (const species of ['rabbit', 'mouse']) for (const amount of [undefined, 0, -10, 5, 999999, NaN, Infinity, '999']) {
    const { listeners, state } = setup();
    await listeners.get('forest-rat-caught')({ detail: { eventId: 7, species, amount } });
    assert.equal(state.carrots, species === 'rabbit' ? 31 : 30, `${species}/${String(amount)}`);
  }
  const { listeners, state } = setup();
  await listeners.get('forest-rat-caught')({ detail: {
    eventId: 8, species: 'rabbit', get amount() { throw new Error('untrusted amount must never be read'); },
  } });
  assert.equal(state.carrots, 31);
});

test('duplicate manual and pet catch events award and persist only once even before a pending save completes', async () => {
  let releaseSave;
  const waitForSave = new Promise(resolve => { releaseSave = resolve; });
  const { listeners, state, saves, sounds, toast, scheduled } = setup({ waitForSave });
  listeners.get('forest-rat-appeared')({ detail: { eventId: 17, species: 'rabbit' } });
  const catchAnimal = listeners.get('forest-rat-caught');
  const pending = [
    catchAnimal({ detail: { eventId: 17, species: 'rabbit', amount: 1 } }),
    catchAnimal({ detail: { eventId: 17, species: 'rabbit', amount: 100, source: 'pet' } }),
    catchAnimal({ detail: { eventId: 17, species: 'mouse', amount: 100 } }),
  ];
  assert.equal(state.carrots, 31);
  assert.equal(saves.length, 1); assert.equal(sounds.length, 1);
  assert.equal(toast.hidden, true, 'the visible notice follows the completed save');
  assert.equal(scheduled.length, 0);
  releaseSave(); await Promise.all(pending);
  assert.equal(toast.hidden, false); assert.equal(scheduled.length, 1);
  await catchAnimal({ detail: { eventId: 17, species: 'rabbit' } });
  assert.equal(state.carrots, 31); assert.equal(saves.length, 1);
  assert.equal(scheduled.length, 1, 'duplicate input must not redisplay or prolong the notice');
});

test('a late previous catch and its duplicate cannot erase a newer active spawn species', async () => {
  const { listeners, state, saves, currentEncounter } = setup();
  const appear = listeners.get('forest-rat-appeared'), caught = listeners.get('forest-rat-caught');
  appear({ detail: { eventId: 21, species: 'rabbit' } });
  appear({ detail: { eventId: 22, species: 'mouse' } });
  await caught({ detail: { eventId: 21, species: 'rabbit', amount: 100 } });
  assert.equal(state.carrots, 31);
  assert.equal(currentEncounter().eventId, 22); assert.equal(currentEncounter().species, 'mouse');
  await caught({ detail: { eventId: 21, species: 'rabbit' } });
  assert.equal(currentEncounter().eventId, 22);
  await caught({ detail: { eventId: 22, species: 'rabbit', amount: 100 } });
  assert.equal(state.carrots, 31, 'the matching mouse spawn still owns its zero reward');
  assert.deepEqual(saves.map(save => save.message), ['토끼가 당근 1개를 놓고 갔습니다.', '쥐를 잡았습니다.']);
  assert.equal(currentEncounter(), null);
});

test('a duplicate zero-reward mouse catch also saves only once, and later distinct rabbits still earn one each', async () => {
  const { listeners, state, saves } = setup(), caught = listeners.get('forest-rat-caught');
  await caught({ detail: { eventId: 'mouse-1', species: 'mouse' } });
  await caught({ detail: { eventId: 'mouse-1', species: 'rabbit', amount: 500 } });
  assert.equal(state.carrots, 30); assert.equal(saves.length, 1);
  for (const eventId of [0, 'rabbit-1', 'rabbit-2']) await caught({ detail: { eventId, species: 'rabbit' } });
  assert.equal(state.carrots, 33); assert.equal(saves.length, 4);
});

test('unidentified catches are ignored and cannot clear the active encounter', async () => {
  const { listeners, state, saves, sounds, currentEncounter } = setup();
  listeners.get('forest-rat-appeared')({ detail: { eventId: 30, species: 'rabbit' } });
  for (const event of [{}, { detail: {} }, { detail: { eventId: null, species: 'rabbit', amount: 500 } }]) {
    await listeners.get('forest-rat-caught')(event);
  }
  assert.equal(state.carrots, 30); assert.equal(saves.length, 0); assert.equal(sounds.length, 0);
  assert.equal(currentEncounter().eventId, 30);
});

test('reward handlers no longer reference the removed profile carrot counter', () => {
  assert.doesNotMatch(source, /#profile-carrots/);
});

test('both exact species notices are visible for four seconds after saving, then hide', async () => {
  for (const [species, message] of [['rabbit', '토끼가 당근 1개를 놓고 갔습니다.'], ['mouse', '쥐를 잡았습니다.']]) {
    const { listeners, toast, timers, scheduled, advance, saves } = setup();
    assert.equal(toast.hidden, true);
    await listeners.get('forest-rat-caught')({ detail: { eventId: 51, species, source: 'pet' } });
    assert.equal(saves[0].message, message);
    assert.equal(toast.textContent, message); assert.equal(toast.hidden, false);
    assert.deepEqual(scheduled.map(timer => timer.delay), [4000]); assert.equal(timers.size, 1);
    advance(3999); assert.equal(toast.hidden, false);
    advance(1); assert.equal(toast.hidden, true); assert.equal(timers.size, 0);
  }
});

test('dancing mouse warning reuses the visible notice without changing carrots', () => {
  const { listeners, state, toast, scheduled, advance } = setup();
  listeners.get('forest-rat-carrot-warning')({ detail: { eventId: 91 } });
  assert.equal(state.carrots, 30);
  assert.equal(toast.textContent, '쥐가 당근을 노리고 있습니다.');
  assert.equal(toast.hidden, false);
  assert.equal(scheduled.at(-1).delay, 4000);
  advance(4000);
  assert.equal(toast.hidden, true);
});

test('a new catch replaces the visible notice and cancels the previous hide timeout', async () => {
  const { listeners, toast, timers, scheduled, cancelled, advance } = setup();
  const caught = listeners.get('forest-rat-caught');
  await caught({ detail: { eventId: 61, species: 'rabbit' } });
  const firstTimeout = scheduled[0].id;
  advance(2000);
  await caught({ detail: { eventId: 62, species: 'mouse' } });
  assert.equal(toast.textContent, '쥐를 잡았습니다.'); assert.equal(toast.hidden, false);
  assert.ok(cancelled.includes(firstTimeout)); assert.equal(timers.has(firstTimeout), false);
  assert.equal(timers.size, 1);
  advance(2000); assert.equal(toast.hidden, false, 'the original four-second timeout cannot erase the newer message');
  advance(1999); assert.equal(toast.hidden, false);
  advance(1); assert.equal(toast.hidden, true);
});

test('duplicates neither extend an existing toast nor show it again after it has hidden', async () => {
  const { listeners, toast, scheduled, advance } = setup();
  const caught = listeners.get('forest-rat-caught');
  await caught({ detail: { eventId: 71, species: 'rabbit' } });
  advance(2500);
  await caught({ detail: { eventId: 71, species: 'mouse', source: 'pet' } });
  assert.equal(toast.textContent, '토끼가 당근 1개를 놓고 갔습니다.');
  assert.equal(scheduled.length, 1);
  advance(1500); assert.equal(toast.hidden, true);
  await caught({ detail: { eventId: 71, species: 'rabbit' } });
  assert.equal(toast.hidden, true); assert.equal(scheduled.length, 1);
});

test('a missing visual toast does not break catch persistence or screen-reader status handling', async () => {
  const { listeners, state, saves, scheduled } = setup({ withToast: false });
  await listeners.get('forest-rat-caught')({ detail: { eventId: 81, species: 'rabbit' } });
  assert.equal(state.carrots, 31);
  assert.deepEqual(saves, [{ carrots: 31, message: '토끼가 당근 1개를 놓고 갔습니다.' }]);
  assert.equal(scheduled.length, 0);
});
