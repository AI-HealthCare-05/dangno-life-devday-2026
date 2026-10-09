const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const code = fs.readFileSync(path.join(__dirname, '../src/frontend/forest-game.js'), 'utf8');
const between = (from, to) => code.slice(code.indexOf(from), code.indexOf(to, code.indexOf(from)));

function fixture() {
  let revision = 0, ready = true;
  const draws = [], copies = [], images = [], queued = [], calls = [];
  const visible = { closest: () => null, getClientRects: () => [1] };
  const roots = new Map();
  const context = vm.createContext({
    window: { LpcAvatarEngine: { isReady: () => ready,
      frameKey: (avatar, options) => JSON.stringify([revision, avatar.gender, avatar.cosmetics, options.pose, options.frame]),
      draw: (ctx, avatar, options, bounds) => { draws.push({ avatar, options, bounds }); return true; } },
      requestAnimationFrame: callback => queued.push(callback) },
    document: { hidden: false, createElement: () => {
      const image = { width: 0, height: 0, getContext: () => ({ imageSmoothingEnabled: true }) };
      images.push(image); return image;
    } },
    $: selector => roots.get(selector),
    renderCanvas: () => calls.push('canvas'),
    drawWardrobeLookThumbnails: () => calls.push('looks'),
    drawMemberFaceThumbnails: () => calls.push('members'),
    drawStorageObjectThumbnails: () => calls.push('storage'),
    drawAnimatedObjectThumbnails: () => calls.push('animated'),
    drawAnimalThumbnails: () => calls.push('animals'),
    renderCatalogThumbnailCanvases: () => calls.push('catalog'),
    renderAvatarPreview: () => calls.push('preview'),
  });
  vm.runInContext(between('  const avatarPreviewCache =', '  const petSpriteImages ='), context);
  const target = { canvas: { width: 96, height: 96 }, drawImage: image => copies.push(image) };
  roots.set('#avatar-studio', { open: false });
  return { context, target, draws, copies, images, queued, calls, visible, roots,
    revise: () => revision++, unavailable: () => ready = false };
}

test('identical outfit draws reuse image across list canvases and changes invalidate it', () => {
  const f = fixture();
  const avatar = { gender: 'male', cosmetics: { hairColor: 'black' } };
  const options = { pose: 'idle', frame: 0 }, bounds = { x: 5, y: 4, width: 86, height: 88 };
  f.context.drawCachedAvatarPreview(f.target, avatar, options, bounds);
  f.context.drawCachedAvatarPreview(f.target, JSON.parse(JSON.stringify(avatar)), options, bounds);
  assert.equal(f.draws.length, 1); assert.equal(f.copies.length, 2);
  for (const change of [() => avatar.cosmetics.hairColor = 'red', () => avatar.gender = 'female',
    () => f.revise(), () => options.previewMobility = true, () => bounds.x++, () => f.target.canvas.width++]) {
    change(); f.context.drawCachedAvatarPreview(f.target, avatar, options, bounds);
  }
  assert.equal(f.draws.length, 7);
  f.unavailable(); assert.equal(f.context.drawCachedAvatarPreview(f.target, avatar, options, bounds), false);
  assert.equal(f.draws.length, 7);
});

test('cache stays within four MiB, releases evicted canvases, and uses least recent entries', () => {
  const f = fixture(); const options = { frame: 0 }, bounds = {};
  const a = { cosmetics: { skin: 'a' } }, b = { cosmetics: { skin: 'b' } };
  f.target.canvas.width = f.target.canvas.height = 600;
  f.context.drawCachedAvatarPreview(f.target, a, options, bounds);
  f.context.drawCachedAvatarPreview(f.target, b, options, bounds);
  f.context.drawCachedAvatarPreview(f.target, a, options, bounds);
  f.context.drawCachedAvatarPreview(f.target, { cosmetics: { skin: 'c' } }, options, bounds);
  assert.equal(f.images[0].width, 600); assert.equal(f.images[1].width, 0);
  assert.ok(vm.runInContext('avatarPreviewCacheBytes <= AVATAR_PREVIEW_CACHE_BYTES', f.context));
  assert.equal(vm.runInContext('avatarPreviewCache.size', f.context), 2);
});

test('asset bursts queue one refresh and leave closed inventory/studio untouched', () => {
  const f = fixture();
  f.context.queueVisibleForestPreviews(); f.context.queueVisibleForestPreviews();
  assert.equal(f.queued.length, 1); f.queued.shift()();
  assert.deepEqual(f.calls, ['canvas', 'looks', 'members']);
  f.calls.length = 0;
  f.roots.set('#inventory-dialog-grid', f.visible); f.roots.set('#avatar-studio', { open: true });
  f.context.queueVisibleForestPreviews(); f.queued.shift()();
  assert.deepEqual(f.calls, ['canvas', 'looks', 'members', 'storage', 'animated', 'animals', 'catalog', 'preview']);
  f.calls.length = 0; f.context.document.hidden = true;
  f.context.queueVisibleForestPreviews(); f.queued.shift()(); assert.deepEqual(f.calls, []);
});

test('hidden parents and closed dialogs cannot trigger outfit composition', () => {
  const f = fixture(); let queries = 0;
  const root = { closest: () => ({}), getClientRects: () => [1], querySelectorAll: () => { queries++; return []; } };
  f.context.state = { outfitHistory: [] };
  vm.runInContext(between('  function drawWardrobeLookThumbnails(', '  async function applyOutfitLook('), f.context);
  f.context.drawWardrobeLookThumbnails(root); assert.equal(queries, 0);
  root.closest = () => null; root.getClientRects = () => [];
  f.context.drawWardrobeLookThumbnails(root); assert.equal(queries, 0);
  root.getClientRects = () => [1]; f.context.drawWardrobeLookThumbnails(root); assert.equal(queries, 1);
});

test('scene transitions preserve placement reset and music without rebuilding inventory', () => {
  const calls = [], selected = { dataset: { placement: 'true' }, setAttribute: (...args) => calls.push(args) };
  const state = { avatar: { sitting: true, mounted: true }, fishing: true };
  const c = vm.createContext({ state, currentScene: 'world', placementCode: 'chair', placementDraft: {},
    $: () => ({ querySelectorAll: () => [selected] }),
    renderPlacementUI: () => calls.push('placement'), emitPlacementUpdate: () => calls.push('event'),
    renderGardenHarvest: () => calls.push('harvest'), sceneMusicName: scene => scene,
    musicEngine: { switchTo: name => { calls.push(name); return Promise.resolve(); } },
    canvas: { focus: () => calls.push('focus') }, setStatus() {},
    renderInventory() { throw Error('scene must not rebuild inventory'); },
  });
  vm.runInContext(between('  function switchScene(', '  function blocked('), c);
  c.switchScene('home');
  assert.deepEqual([state.avatar.x, state.avatar.y], [384, 410]);
  assert.equal(state.avatar.sitting, false); assert.equal(state.avatar.mounted, false);
  assert.equal(state.fishing, false); assert.equal(c.placementCode, null); assert.equal(c.placementDraft, null);
  assert.equal(selected.dataset.placement, 'false');
  assert.ok(calls.includes('home')); assert.ok(calls.includes('harvest'));
});

test('preview ticks animate the pet without recomposing static catalog or idle avatar', () => {
  assert.doesNotMatch(between('  function animateWorld(', '  function distanceTo('), /renderCatalogThumbnailCanvases/);
  const preview = between('  function renderAvatarPreview(', '  function drawPreviewAccessoryOverlay(');
  assert.match(preview, /avatarPreviewPose === "idle" \? 0 : avatarPreviewFrame/);
  assert.match(preview, /elapsed: avatarPreviewFrame \* 150/);
});

test('initialization starts independent asset loads together but reveals only after all complete', async () => {
  const pending = [], calls = [];
  const load = name => { calls.push(name); return new Promise(resolve => pending.push(resolve)); };
  const c = vm.createContext({ URLSearchParams, localDemoOrigin: false, state: null,
    window: { location: { search: '' }, LpcAvatarEngine: { ready: () => load('avatar') },
      ForestObjects: { loadIndividualAssets: () => load('furniture') },
      ForestRiverDuckArt: { loadImages: () => load('ducks') },
      ForestProfile: { watch: () => calls.push('profile') }, requestAnimationFrame() {} },
    renderAll: () => calls.push('render'), setStatus() {}, applyAccountNickname() {}, animateWorld() {},
  });
  const from = code.indexOf('async (loaded) => {', code.indexOf('adapter.load().then('));
  const to = code.indexOf(').catch((error)', from);
  vm.runInContext('globalThis.initialize = ' + code.slice(from, to), c);
  const task = c.initialize({ homeRecordPlaying: false });
  assert.deepEqual(calls, ['avatar', 'furniture', 'ducks']);
  pending[0](); pending[1](); await Promise.resolve();
  assert.equal(calls.includes('render'), false);
  pending[2](); await task;
  assert.deepEqual(calls, ['avatar', 'furniture', 'ducks', 'render', 'profile']);
});
