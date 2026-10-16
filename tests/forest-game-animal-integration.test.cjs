const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../src/frontend/forest-game.js'), 'utf8');
const animals = require('../src/frontend/forest-animals.js');
const cowHelpers = source.slice(source.indexOf('  function fallbackCowEntry('), source.indexOf('  function drawPlacedObject('));

test('all cow inventory and Canvas rendering uses the downloaded body, never the old grass tile', () => {
  assert.doesNotMatch(source, /carrot-forest-reward-cow-v[12]|storage-reward-cow|cow-toggle/);
  assert.match(source, /rewardCowImage.src = "\/static\/assets\/animals\/lpc-cow-eat.png"/);
  assert.match(source, /data-animal="cow"/);
  assert.match(source, /ForestAnimals\.frameRect\(sample.key, sample.frame\)/);
  const drawSource = source.slice(source.indexOf('  function drawPlacedObject('), source.indexOf('  function drawPlacementGrid('));
  const drawn = [];
  const item = { code: 'reward_cow', active: true, x: 400, y: 320, rotation: 0 };
  const context = vm.createContext({
    context: { save() {}, restore() {}, translate() {}, rotate() {}, drawImage: (...args) => drawn.push(args) },
    interactiveObjectTypes: { reward_cow: 'cow' }, animatedObjectRows: {},
    rewardCowImage: { complete: true, naturalWidth: 512 }, cowStates: new WeakMap(),
    performance: { now: () => 1000 }, window: { ForestAnimals: animals, matchMedia: () => ({ matches: false }) },
  });
  vm.runInContext(cowHelpers + drawSource, context);
  context.drawPlacedObject(item);
  assert.deepEqual(drawn[0].slice(1, 5), [0, 128, 128, 128]);
  assert.deepEqual(drawn[0].slice(5), [-80, -110, 160, 160]);
});

test('touch reaction is finite, respects existing sound preferences, and does not alter saved cow state', () => {
  const react = source.slice(source.indexOf('  function reactToCow('), source.indexOf('  let lastAnimationAt'));
  const item = { code: 'reward_cow', active: false, x: 400, y: 320 };
  const before = JSON.stringify(item), sounds = [], events = [];
  const context = vm.createContext({
    state: { placed: [item] }, cowStates: new WeakMap(), document: { hidden: false }, currentScene: 'world', placementCode: null,
    performance: { now: () => 100 },
    sfxEngine: { muted: true, effectiveVolume: () => 0 },
    window: { ForestAnimals: { ...animals, playMoo: options => sounds.push(options) },
      matchMedia: () => ({ matches: false }), dispatchEvent: event => events.push(event) },
    CustomEvent: class { constructor(type, options) { this.type = type; this.detail = options.detail; } },
    setStatus() {}, renderCanvas() {},
  });
  vm.runInContext(cowHelpers + react, context);
  context.reactToCow(0, 'head');
  assert.equal(context.cowStates.get(item).lastAt, 100);
  assert.equal(context.cowStates.get(item).state.action, 'head');
  assert.equal(sounds[0].enabled, false);
  assert.equal(sounds[0].volume, 0);
  assert.equal(events[0].type, 'forest-cow-react');
  assert.equal(events[0].detail.reaction, 'head');
  assert.equal(JSON.stringify(item), before);
});

test('Q interaction strokes a cow without switching it into a perpetual active state', async () => {
  const toggle = source.slice(source.indexOf('  async function togglePlacedObject('), source.indexOf('  function nearbyInteraction('));
  const item = { code: 'reward_cow', active: false }, calls = [];
  const context = vm.createContext({ state: { placed: [item] }, interactiveObjectTypes: { reward_cow: 'cow' }, reactToCow: index => calls.push(index) });
  vm.runInContext(toggle, context);
  await context.togglePlacedObject(0);
  assert.deepEqual(calls, [0]);
  assert.equal(item.active, false);
  assert.equal(item.activatedAt, undefined);
});

test('rabbit encounter keeps the spawn species and does not call it a mouse on completion', async () => {
  const eventsSource = source.slice(source.indexOf('  let currentWildEncounter = null;'), source.indexOf('  window.addEventListener("forest-placement-confirm"'));
  const handlers = {}, messages = [];
  const context = vm.createContext({
    window: { addEventListener: (name, listener) => { handlers[name] = listener; } },
    state: { carrots: 10, avatar: { cosmetics: { pet: 'none' } } },
    adapter: { mode: 'demo' },
    setStatus: message => messages.push(message), persist: async message => messages.push(message),
    playSfx() {}, $: selector => selector === '#forest-catch-toast' ? null : ({}),
  });
  vm.runInContext(eventsSource, context);
  handlers['forest-rat-appeared']({ detail: { species: 'rabbit', eventId: 'test-encounter' } });
  await handlers['forest-rat-caught']({ detail: { eventId: 'test-encounter', amount: 500 } });
  assert.ok(messages.every(message => message.includes('토끼')));
  assert.equal(messages.at(-1), '토끼가 당근 1개를 놓고 갔습니다.');
  assert.equal(context.state.carrots, 11);
});

test('night BGM starts at 19:00 and remains optional without affecting indoor tracks', () => {
  const music = source.slice(source.indexOf('  function sceneMusicName('), source.indexOf('  function activeQuestIds('));
  let hour = 18, off = false;
  const context = vm.createContext({ currentScene: 'world', currentLocalHour: () => hour,
    localStorage: { getItem: () => off ? 'off' : 'on' }, ATMOSPHERE_KEY: 'atmosphere', state: { homeRecordPlaying: false }, homeRecordCatalog: {} });
  vm.runInContext(music, context);
  assert.equal(context.sceneMusicName(), 'forest');
  hour = 19;
  assert.equal(context.sceneMusicName(), 'night');
  assert.equal(context.sceneMusicName('home'), 'home');
  assert.equal(context.sceneMusicName('garden'), 'garden');
  off = true;
  assert.equal(context.sceneMusicName(), 'forest');
});

test('fallback nighttime pass darkens actors too and cuts light only around active fixtures', () => {
  const lighting = source.slice(source.indexOf('  let fallbackNightCanvas = null;'), source.indexOf('  function renderCanvas('));
  const holes = [], overlays = [];
  const mask = { clearRect() {}, fillRect() {}, beginPath() {}, fill() {},
    arc: (...args) => holes.push(args), createRadialGradient: () => ({ addColorStop() {} }) };
  const window = { carrotForestPhaserActive: false, ForestAtmosphere: { strength: () => .78 } };
  const context = vm.createContext({ window, currentScene: 'world', currentLocalHour: () => 19,
    localStorage: { getItem: () => 'on' }, ATMOSPHERE_KEY: 'atmosphere', WORLD_WIDTH: 768, WORLD_HEIGHT: 512,
    document: { createElement: () => ({ getContext: () => mask }) },
    context: { save() {}, restore() {}, drawImage: (...args) => overlays.push(args) },
    WORLD_FIXED_LANTERNS: [],
    state: { placed: [{ code: 'lantern', x: 400, y: 320, active: true }, { code: 'campfire', x: 500, y: 320, active: false }] },
  });
  vm.runInContext(lighting, context);
  context.drawFallbackNightLighting();
  assert.equal(overlays.length, 1);
  assert.equal(holes.length, 1);
  assert.equal(context.context.globalAlpha, .78);
  window.carrotForestPhaserActive = true;
  context.drawFallbackNightLighting();
  assert.equal(overlays.length, 1, 'Phaser owns its own single lighting pass');
  assert.match(source, /drawAvatar\(\);\s+drawSceneEffects\(\);\s+drawFallbackNightLighting\(\);/);
});
