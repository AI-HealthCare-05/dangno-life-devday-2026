const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

const source = readFileSync(path.join(__dirname, '../src/frontend/forest-game.js'), 'utf8');
const FONT_KEY = 'gandang-carrot-forest-font-size-v1';

function slice(start, end) {
  const begin = source.indexOf(start), finish = source.indexOf(end, begin);
  assert.ok(begin >= 0 && finish > begin, `source section exists: ${start}`);
  return source.slice(begin, finish);
}

function setup({ storedFont, legacyLarge = false, blockedRead = false, blockedWrite = false } = {}) {
  const storage = new Map([['gandang-carrot-forest-demo-v1', '{"avatar":{"x":456,"y":399},"carrots":777}']]);
  if (storedFont !== undefined) storage.set(FONT_KEY, storedFont);
  const elements = new Map(), classes = new Set(legacyLarge ? ['large-text'] : []), listeners = new Map();
  let fits = 0, reloads = 0;
  function element() {
    const handlers = new Map();
    return {
      hidden: false, style: {}, textContent: '', value: '',
      set innerHTML(_) { throw new Error('UI must not interpret text as HTML'); },
      addEventListener(type, callback) { handlers.set(type, callback); },
      emit(type, values = {}) { handlers.get(type)?.({ currentTarget: this, ...values }); },
    };
  }
  for (const id of ['#font-size-select', '#reset-position', '#avatar-nameplate', '.home-label', '.garden-label']) elements.set(id, element());
  const state = {
    avatar: { x: 456, y: 399, name: '숲 친구', tuning: { worldScale: .43 } },
    carrots: 777, placed: [{ code: 'lantern', x: 450, y: 300 }], outfitHistory: ['saved-look'],
  };
  const body = { dataset: {}, classList: { contains: name => classes.has(name), remove: name => classes.delete(name) } };
  const window = {
    ForestHud: { fitGame: () => fits++, setZoom() { throw new Error('font preferences must not alter camera zoom'); } },
    location: { reload: () => reloads++ },
    addEventListener: (type, callback) => listeners.set(type, callback),
  };
  const context = vm.createContext({
    canvas: { getBoundingClientRect: () => ({width:768,height:512}) }, window, document: { body }, state, currentScene: 'world', WORLD_WIDTH: 768, WORLD_HEIGHT: 512,
    WISDOM_SPRING_SIGN: { x: 108, y: 424 },
    $: id => elements.get(id) || null,
    localStorage: {
      getItem(key) { if (blockedRead) throw new Error('blocked'); return storage.get(key) ?? null; },
      setItem(key, value) { if (blockedWrite) throw new Error('blocked'); storage.set(key, value); },
      removeItem() { throw new Error('saved data must not be deleted'); }, clear() { throw new Error('saved data must not be cleared'); },
    },
  });
  vm.runInContext(slice('  const FONT_SIZE_KEY =', '  const atmosphereButton =') +
    slice('  $("#reset-position").addEventListener', '  $("#world-dialog-close").addEventListener') +
    slice('  function fallbackViewport()', '  let fallbackNightCanvas ='), context);
  return {
    window, state, body, classes, storage, context, elements, fits: () => fits, reloads: () => reloads,
    get: id => elements.get(id),
    chooseFont(value) { const select = elements.get('#font-size-select'); select.value = value; select.emit('change'); },
    project: () => listeners.get('forest-camera-view')(),
  };
}

test('three font levels persist every selection and restore across fresh page loads without changing game state', () => {
  const app = setup(), original = JSON.stringify(app.state);
  assert.equal(app.body.dataset.fontSize, 'default');
  assert.equal(app.get('#font-size-select').value, 'default');
  assert.equal(app.fits(), 1);
  for (const [index, size] of ['small', 'default', 'large', 'small'].entries()) {
    app.chooseFont(size);
    assert.equal(app.body.dataset.fontSize, size);
    assert.equal(app.get('#font-size-select').value, size);
    assert.equal(app.storage.get(FONT_KEY), size);
    assert.equal(app.fits(), index + 2);
    assert.equal(setup({ storedFont: app.storage.get(FONT_KEY) }).body.dataset.fontSize, size);
    assert.equal(JSON.stringify(app.state), original);
  }
});

test('font preferences migrate the old large-text class, normalize invalid values and tolerate blocked storage', () => {
  const legacy = setup({ legacyLarge: true });
  assert.equal(legacy.body.dataset.fontSize, 'large');
  assert.equal(legacy.classes.has('large-text'), false);
  assert.equal(legacy.storage.get(FONT_KEY), 'large');
  assert.equal(setup({ storedFont: 'small', legacyLarge: true }).body.dataset.fontSize, 'small');
  const invalid = setup({ storedFont: 'huge' });
  assert.equal(invalid.body.dataset.fontSize, 'default');
  invalid.chooseFont('arbitrary-css');
  assert.equal(invalid.storage.get(FONT_KEY), 'default');
  for (const flags of [{ blockedRead: true }, { blockedWrite: true }, { blockedRead: true, blockedWrite: true }]) {
    const app = setup(flags);
    assert.equal(app.body.dataset.fontSize, 'default');
    app.chooseFont('large');
    assert.equal(app.body.dataset.fontSize, 'large');
    assert.equal(app.get('#font-size-select').value, 'large');
  }
});

test('initialization button reloads exactly once and leaves coordinates, outfits, objects, progress and storage untouched', () => {
  const app = setup({ storedFont: 'large' });
  const gameBefore = JSON.stringify(app.state), storedBefore = JSON.stringify([...app.storage]);
  app.get('#reset-position').emit('click');
  assert.equal(app.reloads(), 1);
  assert.equal(JSON.stringify(app.state), gameBefore);
  assert.equal(JSON.stringify([...app.storage]), storedBefore);
  assert.equal(app.fits(), 1, 'refresh must not run the former in-place position or camera reset');
});

test('nickname uses the camera head projection as plain text and follows each camera view event', () => {
  const app = setup();
  let anchor = { x: .3, y: .4, name: '<img src=x onerror=alert(1)>' };
  const calls = [];
  app.window.ForestCamera = {
    avatarAnchor: () => anchor,
    worldToScreen(x, y) { calls.push([x, y]); return { x: x / 768, y: y / 512 }; },
  };
  app.project();
  const nickname = app.get('#avatar-nameplate');
  assert.equal(nickname.textContent, '<img src=x onerror=alert(1)>');
  assert.equal(nickname.style.left, '30%'); assert.equal(nickname.style.top, '40%');
  assert.equal(nickname.hidden, false);
  assert.deepEqual(calls, [[205, 62], [610, 62]]);
  anchor = { x: .75, y: .5, name: '바뀐 닉네임' }; app.project();
  assert.equal(nickname.textContent, '바뀐 닉네임');
  assert.equal(nickname.style.left, '75%'); assert.equal(nickname.style.top, '50%');
  for (const scene of ['home', 'garden']) {
    app.context.currentScene = scene; app.project();
    assert.equal(app.get('.home-label').hidden, true);
    assert.equal(app.get('.garden-label').hidden, true);
    assert.equal(nickname.hidden, false, 'the nickname remains available indoors');
  }
});

test('nickname safely hides offscreen or empty labels and has a no-camera and missing-node fallback', () => {
  const app = setup(), nickname = app.get('#avatar-nameplate');
  app.project();
  assert.equal(nickname.style.left, `${456 / 768 * 100}%`);
  assert.equal(nickname.style.top, `${(399 - 74) / 512 * 100}%`);
  assert.equal(nickname.textContent, app.state.avatar.name);
  let anchor;
  app.window.ForestCamera = { worldToScreen: () => ({ x: .5, y: .5 }), avatarAnchor: () => anchor };
  for (const point of [{ x: -.001, y: .5 }, { x: 1.001, y: .5 }, { x: .5, y: -.001 }, { x: .5, y: 1.001 }]) {
    anchor = { ...point, name: '이름' }; app.project(); assert.equal(nickname.hidden, true);
  }
  anchor = { x: .5, y: .5, name: '' }; app.state.avatar.name = ''; app.project();
  assert.equal(nickname.hidden, true);
  app.elements.delete('#avatar-nameplate');
  assert.doesNotThrow(() => app.project());
});
