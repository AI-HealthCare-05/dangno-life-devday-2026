const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const read = name => fs.readFileSync(path.join(__dirname, '../src/frontend', name), 'utf8');
const game = read('forest-game.js');
const phaser = read('forest-phaser.js');
const engine = read('lpc-avatar-engine.js');
const between = (source, from, to) => source.slice(source.indexOf(from), source.indexOf(to, source.indexOf(from)));

function feedFixture(pet = 'white_pup', carrots = 3) {
  const saves = [], events = [], statuses = [], balance = {};
  const state = { avatar: { cosmetics: { pet } }, carrots, placed: [{ code: 'chair_green', x: 1, y: 2 }] };
  const context = vm.createContext({ state, currentScene: 'world', $: () => balance,
    adapter: { save: async value => saves.push(JSON.parse(JSON.stringify(value))) },
    window: { dispatchEvent: event => events.push(event) },
    CustomEvent: class { constructor(type, options) { this.type = type; this.detail = options.detail; } },
    setStatus: value => statuses.push(value), playSfx() {},
    updateProfileUI() { throw Error('unnecessary profile update'); },
    renderAll() { throw Error('unnecessary full render'); },
  });
  vm.runInContext(between(game, '  async function persist(', '  function fillPixelRect(')
    + between(game, '  async function feedPet()', '  async function toggleRide()'), context);
  return { context, state, saves, events, statuses, balance };
}

test('feeding saves one carrot and count, updates only balance/pet, and keeps placed data', async () => {
  const f = feedFixture();
  const placed = JSON.stringify(f.state.placed);
  await f.context.feedPet();
  assert.equal(f.state.carrots, 2); assert.equal(f.balance.textContent, 2);
  assert.equal(f.state.petFedCount, 1); assert.equal(f.saves.length, 1);
  assert.equal(f.saves[0].petFedCount, 1); assert.equal(f.saves[0].carrots, 2);
  assert.equal(JSON.stringify(f.state.placed), placed);
  assert.deepEqual(f.events.map(event => event.type), ['forest-pet-fed']);
  assert.match(f.statuses[0], /당근 1개/);
});

test('missing pet/empty wallet cannot feed; repeated clicks never spend beyond balance', async () => {
  for (const [pet, carrots] of [['none', 3], ['', 3], ['white_pup', 0]]) {
    const f = feedFixture(pet, carrots); await f.context.feedPet();
    assert.equal(f.state.carrots, carrots); assert.equal(f.saves.length, 0); assert.equal(f.events.length, 0);
  }
  const f = feedFixture('white_pup', 2);
  await Promise.all([f.context.feedPet(), f.context.feedPet(), f.context.feedPet()]);
  assert.equal(f.state.carrots, 0); assert.equal(f.state.petFedCount, 2); assert.equal(f.saves.length, 2);
});

test('ordinary saves still synchronize the scene and profile', async () => {
  const f = feedFixture(); let profiles = 0;
  f.context.updateProfileUI = () => profiles++;
  await f.context.persist('saved');
  assert.equal(profiles, 1); assert.equal(f.saves.length, 1);
  assert.deepEqual(f.events.map(event => event.type), ['forest-state-updated']);
  assert.equal(f.events[0].detail.avatar, f.state.avatar);
  assert.equal(f.events[0].detail.placed, f.state.placed);
});

function sceneFixture() {
  const window = { Phaser: { Scene: class {}, Game: class { constructor(config) { this.config = config; } },
    Scale: { NONE: 0 }, AUTO: 1, CANVAS: 2 }, innerWidth: 400, innerHeight: 800,
    ForestObjects: { INDIVIDUAL_ASSETS: [] } };
  vm.runInNewContext(phaser, { window, Phaser: window.Phaser,
    document: { getElementById: () => ({}), documentElement: { classList: { contains: () => false } } },
    localStorage: { getItem: () => null }, performance: { now: () => 5000 } });
  return { scene: new window.carrotForestPhaserGame.config.scene(), window };
}

test('identical placed objects reuse actors; changed position and state rebuild them', () => {
  const { scene } = sceneFixture(); let created = 0, destroyed = 0;
  scene.tweens = { killTweensOf() {} };
  scene.createPlacedObjectActor = item => { created++; return { getData: name => name === 'item' ? item : null,
    destroy: () => destroyed++ }; };
  const placed = [{ code: 'chair_green', x: 100, y: 200, active: false }];
  scene.syncPlacedObjects(placed); const actor = scene.placedObjectActors[0];
  scene.syncPlacedObjects(JSON.parse(JSON.stringify(placed)));
  assert.equal(created, 1); assert.equal(destroyed, 0); assert.equal(scene.placedObjectActors[0], actor);
  placed[0].x++; scene.syncPlacedObjects(placed);
  placed[0].active = true; scene.syncPlacedObjects(placed);
  assert.equal(created, 3); assert.equal(destroyed, 2);
  scene.syncPlacedObjects([]); scene.syncPlacedObjects([]); assert.equal(destroyed, 3);
});

test('same composite frame skips draw/readback; revisited frame reuses bounded opaque coordinates', () => {
  const { scene, window } = sceneFixture(); let draws = 0, reads = 0, uploads = 0;
  window.CarrotAvatarCompositor = {};
  window.LpcAvatarEngine = { frameKey: (avatar, options) => JSON.stringify([avatar.cosmetics, options.direction,
    options.moving ? options.frame % 8 : 0, window.revision || 0]), draw: () => { draws++; return true; } };
  scene.avatar = { engine: 'lpc', cosmetics: {}, tuning: { worldScale: .43 } };
  scene.premiumAvatar = { setVisible(value) { this.visible = value; }, setScale(value) { this.scale = value; } };
  scene.compositeTexture = { getContext: () => ({ clearRect() {}, getImageData() { reads++; return { data: [] }; } }),
    refresh: () => uploads++ };
  scene.measureAvatarOpaqueBounds = () => ({ x: 1, y: 2, width: 3, height: 4 });
  scene.setPremiumFrame('down', false, 0); scene.setPremiumFrame('down', false, 500);
  assert.deepEqual([draws, reads, uploads], [1, 1, 1]);
  scene.avatar.tuning.worldScale = .5; scene.setPremiumFrame('down', false, 600);
  assert.equal(scene.premiumAvatar.scale, .5); assert.equal(draws, 1);
  scene.setPremiumFrame('left', true, 140); scene.setPremiumFrame('down', false, 700);
  assert.deepEqual([draws, reads, uploads], [3, 2, 3]);
  scene.avatar.cosmetics.hair = 'new'; scene.setPremiumFrame('down', false, 700);
  window.revision = 1; scene.setPremiumFrame('down', false, 700);
  assert.deepEqual([draws, reads, uploads], [5, 4, 5]);
  for (let revision = 2; revision < 100; revision++) {
    window.revision = revision; scene.setPremiumFrame('down', false, 700);
  }
  assert.equal(scene.avatarBoundsCache.size, 64);
  window.revision++;
  window.LpcAvatarEngine.draw = () => false;
  scene.setPremiumFrame('down', false, 700);
  assert.equal(scene.premiumAvatar.visible, false);
  assert.equal(scene.avatarFrameKey, null, 'failed drawing cannot pin an empty frame');
  window.LpcAvatarEngine.draw = () => true;
  scene.setPremiumFrame('down', false, 700);
  assert.equal(scene.premiumAvatar.visible, true);
});

test('engine keys follow actual cycle positions and invalidate when loaded assets change', async () => {
  const callbacks = []; const window = { dispatchEvent() {} };
  const context = vm.createContext({ window, fetch: async () => ({ ok: true, json: async () => ({ items: [] }) }),
    Image: class { addEventListener(type, cb) { if (type === 'load') callbacks.push(cb); } },
    requestAnimationFrame: cb => cb(), CustomEvent: class {}, console });
  vm.runInContext(engine, context);
  assert.equal(window.LpcAvatarEngine.frameKey({ cosmetics: {} }), null, 'unloaded manifest cannot pin a frame');
  await window.LpcAvatarEngine.ready();
  const avatar = { gender: 'male', cosmetics: {} }, options = { direction: 'down', frame: 0 };
  const key = window.LpcAvatarEngine.frameKey(avatar, options);
  assert.equal(window.LpcAvatarEngine.frameKey(avatar, { ...options, frame: 100 }), key);
  assert.notEqual(window.LpcAvatarEngine.frameKey(avatar, { ...options, direction: 'left' }), key);
  assert.notEqual(window.LpcAvatarEngine.frameKey(avatar, { ...options, moving: true, frame: 1 }),
    window.LpcAvatarEngine.frameKey(avatar, { ...options, moving: true, frame: 2 }));
  assert.notEqual(window.LpcAvatarEngine.frameKey(avatar, { ...options, pose: 'attack', progress: .1 }),
    window.LpcAvatarEngine.frameKey(avatar, { ...options, pose: 'attack', progress: .8 }));
  // Exercise the actual image-loading path rather than manually changing the revision.
  const injected = engine.replace('    frameKey,', '    frameKey, ensureImage,');
  vm.runInContext(injected, context); await window.LpcAvatarEngine.ready();
  const before = window.LpcAvatarEngine.frameKey(avatar, options);
  window.LpcAvatarEngine.ensureImage('fixture.png'); callbacks.pop()();
  await new Promise(resolve => setImmediate(resolve));
  assert.notEqual(window.LpcAvatarEngine.frameKey(avatar, options), before);
});
