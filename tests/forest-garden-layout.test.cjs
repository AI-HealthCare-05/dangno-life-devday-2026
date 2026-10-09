const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

const frontend = path.join(__dirname, '../src/frontend');
const read = filename => fs.readFileSync(path.join(frontend, filename), 'utf8');
const garden = require('../src/frontend/forest-garden.js');
const gameSource = read('forest-game.js');

function canvasContext() {
  const calls = { images: [], labels: [], rectangles: [], scales: [], saves: 0, restores: 0 };
  const context = {
    save() { calls.saves += 1; },
    restore() { calls.restores += 1; },
    fillRect(...args) { calls.rectangles.push(args); },
    fillText(...args) { calls.labels.push(args); },
    drawImage(...args) { calls.images.push(args); },
    scale(...args) { calls.scales.push(args); },
  };
  return { context, calls };
}

function section(source, start, end) {
  const first = source.indexOf(start), last = source.indexOf(end, first + start.length);
  assert.ok(first >= 0 && last > first, `source section exists: ${start}`);
  return source.slice(first, last);
}

function browserGarden() {
  const canvases = [];
  const document = { createElement(tag) {
    assert.equal(tag, 'canvas');
    const { context, calls } = canvasContext();
    const canvas = { width: 0, height: 0, calls, getContext: () => context };
    context.getImageData = () => ({ data: new Uint8ClampedArray(canvas.width * canvas.height * 4).fill(255) });
    canvases.push(canvas);
    return canvas;
  } };
  const window = { document };
  vm.runInNewContext(read('forest-garden.js'), { window });
  return { garden: window.ForestGarden, canvases };
}

test('the garden has six ordered weekly rows, five separate carrots per row, and exactly thirty positions', () => {
  assert.deepEqual([garden.layout.width, garden.layout.height], [768, 512]);
  assert.equal(garden.layout.rows.length, 6);
  assert.deepEqual(garden.layout.rows.map(row => row.week), [1, 2, 3, 4, 5, 6]);
  assert.deepEqual(garden.layout.rows.map(row => row.label), ['1주차', '2주차', '3주차', '4주차', '5주차', '6주차']);
  assert.equal(new Set(garden.layout.rows.map(row => row.y)).size, 6);
  const carrots = garden.layout.rows.flatMap(row => {
    assert.equal(row.carrots.length, 5, `${row.label} contains five carrots`);
    assert.equal(new Set(row.carrots.map(carrot => carrot.x)).size, 5);
    assert.ok(row.carrots.every(carrot => carrot.y === row.y), 'each week is one horizontal row');
    assert.equal(row.sign.y, row.y, 'the wooden sign aligns with its own row');
    return row.carrots;
  });
  assert.equal(carrots.length, 30);
  assert.equal(new Set(carrots.map(carrot => `${carrot.x},${carrot.y}`)).size, 30);
  assert.ok(garden.layout.rows.every((row, index, rows) => !index || row.y > rows[index - 1].y));
});

test('all thirty carrots and six wooden signs stay inside the field and clear the open entrance', () => {
  const entrance = { left: 330, top: 370, right: 445, bottom: 458 };
  const assertClear = (x, y, width, height, label) => {
    const bounds = { left: x - width / 2, right: x + width / 2, top: y - height, bottom: y };
    assert.ok(bounds.left >= 105 && bounds.right <= 675 && bounds.top >= 80 && bounds.bottom < 370, label);
    assert.ok(bounds.right <= entrance.left || bounds.left >= entrance.right || bounds.bottom <= entrance.top || bounds.top >= entrance.bottom,
      `${label} cannot cover the (384,410) spawn or (384,430) exit`);
  };
  for (const row of garden.layout.rows) {
    for (const carrot of row.carrots) assertClear(carrot.x, carrot.y, carrot.width, carrot.height, `${row.label} carrot`);
    const sign = row.sign;
    assertClear(sign.x, sign.y, sign.width, sign.height + sign.postHeight, `${row.label} sign`);
  }
});

test('one Canvas draw renders thirty cropped carrot sprites and six legible wooden weekly signs', () => {
  const { context, calls } = canvasContext();
  const carrotImage = { complete: true, naturalWidth: 1024, naturalHeight: 1024 };
  const bounds = { x: 440, y: 350, width: 100, height: 180 };
  assert.equal(garden.draw(context, carrotImage, { bounds }), 30);
  assert.equal(calls.images.length, 30);
  assert.deepEqual(calls.labels.map(call => call[0]), ['1주차', '2주차', '3주차', '4주차', '5주차', '6주차']);
  assert.ok(calls.rectangles.length >= 12, 'each sign includes a wooden plate and supporting post');
  assert.equal(calls.saves, calls.restores, 'shared drawing must preserve the caller Canvas state');
  for (const draw of calls.images) {
    assert.equal(draw[0], carrotImage);
    assert.deepEqual(draw.slice(1, 5), [bounds.x, bounds.y, bounds.width, bounds.height], 'transparent margins are cropped, not stretched over the field');
    assert.ok(draw[5] >= 105 && draw[6] >= 80 && draw[5] + draw[7] <= 675 && draw[6] + draw[8] < 370);
    assert.ok(Math.abs(draw[7] / draw[8] - bounds.width / bounds.height) < 1e-10, 'carrot aspect ratio is preserved');
  }
});

test('unavailable carrot art does not throw or hide the six week labels', () => {
  for (const carrotImage of [null, { complete: false, naturalWidth: 1024 }, { complete: true, naturalWidth: 0 }]) {
    const { context, calls } = canvasContext();
    assert.equal(garden.draw(context, carrotImage), 0);
    assert.equal(calls.images.length, 0);
    assert.deepEqual(calls.labels.map(call => call[0]), ['1주차', '2주차', '3주차', '4주차', '5주차', '6주차']);
  }
});

test('alpha bounds trim transparent padding and safely handle fully transparent sprite images', () => {
  const pixels = new Uint8ClampedArray(12 * 10 * 4);
  const setAlpha = (x, y, value) => { pixels[(y * 12 + x) * 4 + 3] = value; };
  setAlpha(4, 2, 255);
  setAlpha(7, 8, 255);
  setAlpha(0, 0, 1);
  assert.deepEqual(garden.alphaBounds(pixels, 12, 10), { x: 4, y: 2, width: 4, height: 7 });
  assert.equal(garden.alphaBounds(new Uint8ClampedArray(12 * 10 * 4), 12, 10), null);
  assert.equal(garden.alphaBounds(null, 0, 0), null);
});

test('the dense Phaser layer and Canvas fallback draw the same thirty carrots at the same world coordinates', () => {
  const browser = browserGarden();
  const carrotImage = { complete: true, naturalWidth: 20, naturalHeight: 40 };
  const layer = browser.garden.createLayerCanvas(carrotImage, { resolution: 4 });
  assert.deepEqual([layer.width, layer.height], [3072, 2048]);
  assert.deepEqual(layer.calls.scales, [[4, 4]]);
  assert.equal(layer.calls.images.length, 30);
  assert.equal(layer.calls.labels.length, 6);
  const { context, calls } = canvasContext();
  browser.garden.draw(context, carrotImage);
  assert.deepEqual(layer.calls.images, calls.images, 'only backing density differs, never crop positions or dimensions');
  assert.deepEqual(layer.calls.labels, calls.labels);
  assert.deepEqual(layer.calls.rectangles, calls.rectangles);
});

test('Canvas map rendering invokes the shared garden only inside the garden after its background', () => {
  const carrotImage = { complete: true, naturalWidth: 20, naturalHeight: 40 };
  const backgrounds = Object.fromEntries(['garden', 'home', 'world'].map(name => [name, { name, complete: true, naturalWidth: 768 }]));
  const calls = [], context = { drawImage: image => calls.push(['background', image.name]) };
  const env = vm.createContext({
    currentScene: 'garden', sceneImages: backgrounds, context, gardenCarrotImage: carrotImage, WORLD_WIDTH: 768, WORLD_HEIGHT: 512,
    window: { ForestGarden: { draw(ctx, image) {
      assert.equal(ctx, context); assert.equal(image, carrotImage); calls.push(['shared-garden']);
    } } },
    drawHomeRecordPlayer() {}, drawPlacedObjects() {},
  });
  vm.runInContext(section(gameSource, '  function drawMap(', '  function drawHomeRecordPlayer('), env);
  env.drawMap();
  assert.deepEqual(calls, [['background', 'garden'], ['shared-garden']]);
  for (const scene of ['home', 'world']) {
    calls.length = 0; env.currentScene = scene; env.drawMap();
    assert.deepEqual(calls, [['background', scene]], 'weekly signs cannot leak into the house or outer forest');
  }
  assert.match(gameSource, /sceneImages\.garden\.src = window\.ForestGarden\.assets\.background\.url/);
  assert.match(gameSource, /gardenCarrotImage\.src = window\.ForestGarden\.assets\.carrot\.url/);
});

test('Phaser loads shared assets, displays the shared layer only in the garden and leaves its entrance walkable', () => {
  const layerCalls = [], created = [], loaded = [];
  const carrotImage = { complete: true, naturalWidth: 20, naturalHeight: 40 };
  const layerCanvas = { width: 3072, height: 2048 };
  const Phaser = { Scene: class {}, AUTO: 0, Scale: { NONE: 0 }, Game: class { constructor(config) { this.config = config; } } };
  const window = {
    Phaser, ForestGarden: { ...garden, createLayerCanvas(source, options) {
      layerCalls.push([source, options.resolution]); return layerCanvas;
    } },
    ForestRiverDuckArt: { assets: [] }, ForestAnimals: { assets: [] }, ForestObjects: { INDIVIDUAL_ASSETS: [] },
  };
  vm.runInNewContext(read('forest-phaser.js'), {
    window, Phaser, document: { documentElement: { classList: { contains: () => false } }, getElementById: () => ({}) }, localStorage: { getItem: () => null }, performance: { now: () => 0 },
  });
  const scene = new window.carrotForestPhaserGame.config.scene();
  scene.load = { image: (...args) => loaded.push(args), spritesheet() {} };
  scene.preload();
  for (const asset of Object.values(garden.assets)) assert.ok(loaded.some(([key, url]) => key === asset.key && url === asset.url));
  const textures = new Map([[garden.assets.carrot.key, carrotImage]]);
  scene.textures = {
    exists: key => textures.has(key), get: key => ({ getSourceImage: () => textures.get(key) }),
    remove: key => textures.delete(key), addCanvas: (key, canvas) => textures.set(key, canvas),
  };
  scene.add = { image(x, y, texture) {
    const actor = {
      x, y, texture, setDisplaySize(width, height) { this.width = width; this.height = height; return this; },
      setDepth(depth) { this.depth = depth; return this; }, setVisible(visible) { this.visible = visible; return this; },
    };
    created.push(actor); return actor;
  } };
  scene.createGardenLayer();
  assert.deepEqual(layerCalls, [[carrotImage, 4]]);
  assert.equal(created.length, 1);
  assert.equal(textures.get(scene.gardenLayer.texture), layerCanvas, 'Phaser texture is the shared Canvas output');
  assert.deepEqual([scene.gardenLayer.x, scene.gardenLayer.y, scene.gardenLayer.width, scene.gardenLayer.height, scene.gardenLayer.depth], [384, 256, 768, 512, 1]);
  assert.equal(scene.gardenLayer.visible, false);
  scene.background = { setTexture() { return this; }, setDisplaySize() { return this; } };
  scene.updateWorldAtmosphere = () => {};
  for (const sceneName of ['garden', 'home', 'world', 'garden']) {
    scene.setScene(sceneName);
    assert.equal(scene.gardenLayer.visible, sceneName === 'garden');
  }
  for (const y of [370, 390, 410, 430, 450]) assert.equal(scene.isBlocked(384, y), false, `entrance path at y=${y} stays open`);
  const fallback = vm.createContext({ currentScene: 'garden', WORLD_WIDTH: 768, WORLD_HEIGHT: 512 });
  vm.runInContext(section(gameSource, '  function blocked(', '  function placementCellValid('), fallback);
  for (const y of [370, 390, 410, 430, 450]) assert.equal(fallback.blocked(384, y), false);
});

test('the empty background and independent carrot are versioned consistently in both renderers and the offline cache', () => {
  const phaserSource = read('forest-phaser.js'), html = read('forest.html'), serviceWorker = read('forest-sw.js');
  assert.match(garden.assets.background.url, /\/carrot-forest-garden-v3\.png\?v=/);
  assert.match(garden.assets.carrot.url, /\/garden-carrot-v168\.png\?v=/);
  for (const asset of Object.values(garden.assets)) {
    const filename = asset.url.split('?')[0].replace(/^\/static\//, '');
    assert.ok(fs.existsSync(path.join(frontend, filename)), `published asset exists: ${filename}`);
    assert.ok(serviceWorker.includes(asset.url), `offline cache keeps the exact version: ${asset.url}`);
  }
  for (const source of [gameSource, phaserSource, serviceWorker]) assert.doesNotMatch(source, /carrot-forest-garden-v2\.png/);
  const gardenScript = html.match(/<script\b[^>]*src="([^"\s]*forest-garden\.js\?[^"\s]*)"/);
  assert.ok(gardenScript, 'shared garden module is included in the page shell');
  assert.ok(serviceWorker.includes(gardenScript[1]), 'offline shell uses the exact same garden module URL');
  assert.ok(html.indexOf(gardenScript[1]) < html.indexOf('/static/forest-phaser.js'));
  assert.ok(html.indexOf(gardenScript[1]) < html.indexOf('/static/forest-game.js'));
});

test('thirty display carrots neither cap earned rewards nor allow duplicate harvesting', async () => {
  const state = { carrots: 100, challengeCarrotClaims: {
    walk: { amount: 17, harvested: false }, meal: { amount: 21, harvested: false }, water: { amount: 8, harvested: true },
  } };
  const messages = [], events = [], rendered = [];
  const panel = { classList: { add() {}, remove() {} } };
  const env = vm.createContext({
    state, $: () => panel, setStatus: message => messages.push(message), playSfx() {},
    renderAll: () => rendered.push(state.carrots), persist: async message => messages.push(message),
    window: { dispatchEvent: event => events.push(event), setTimeout: callback => callback() },
    CustomEvent: class { constructor(type, options) { this.type = type; this.detail = options.detail; } },
  });
  vm.runInContext(section(gameSource, '  function pendingChallengeCarrots(', '  function accrueChallengeCarrots(')
    + section(gameSource, '  async function harvestChallengeCarrots(', '  function outfitCardMarkup('), env);
  assert.equal(env.pendingChallengeCarrots(), 38, 'reward accounting is independent of the thirty visual slots');
  await env.harvestChallengeCarrots();
  assert.equal(state.carrots, 138);
  assert.ok(Object.values(state.challengeCarrotClaims).every(claim => claim.harvested));
  assert.equal(env.pendingChallengeCarrots(), 0);
  await env.harvestChallengeCarrots();
  assert.equal(state.carrots, 138, 'already harvested rewards cannot be claimed twice');
  assert.deepEqual(rendered, [138]);
  assert.equal(events.length, 1);
  assert.equal(events[0].type, 'forest-avatar-action');
});


test('world fallback preserves the loaded field art and placed objects without a legacy vehicle overlay', () => {
  const calls = [];
  const image = { complete: true, naturalWidth: 768 };
  const env = vm.createContext({
    currentScene: 'world', sceneImages: { world: image },
    context: { drawImage: (...args) => calls.push(['image', ...args]) },
    WORLD_WIDTH: 768, WORLD_HEIGHT: 512, MAP_WIDTH: 24, MAP_HEIGHT: 16, TILE: 32,
    animationFrame: 0, window: {},
    fillPixelRect: (...args) => calls.push(['pixel', ...args]),
    drawPlacedObjects: () => calls.push(['placed']),
    drawPond() {}, drawHouse() {}, drawCarrotPlot() {}, drawSharedTree() {}, drawTree() {}, drawFlower() {},
  });
  vm.runInContext(section(gameSource, '  function drawMap(', '  function drawHomeRecordPlayer('), env);
  env.drawMap();
  assert.deepEqual(calls, [['image', image, 0, 0, 768, 512], ['placed']], 'loaded background is not painted over by an unowned decoration');
  calls.length = 0; image.complete = false; env.drawMap();
  assert.ok(calls.some(call => call[0] === 'pixel'), 'slow background still renders the fallback field');
  assert.equal(calls.filter(call => call[0] === 'placed').length, 1);
  assert.ok(!calls.some(call => call[0] === 'pixel' && ['#c84e30', '#f58e38', '#1f3434'].includes(call.at(-1))), 'slow loading cannot revive the orange vehicle');
});
