const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

const source = readFileSync(path.join(__dirname, '../src/frontend/forest-phaser.js'), 'utf8');

// Mirrors the bundled Phaser 3.90 Camera's center-origin transforms and bounds
// math. The canvas is physical pixels; every actor remains in 768x512 units.
class Camera {
  constructor(width, height) {
    Object.assign(this, { x: 0, y: 0, width, height, zoom: 1, scrollX: 0, scrollY: 0, handlers: new Map() });
    this.matrix = { transformPoint: (x, y) => ({
      x: (x - this.width / 2) * this.zoom + this.width / 2 + this.x,
      y: (y - this.height / 2) * this.zoom + this.height / 2 + this.y,
    }) };
  }
  setBounds(x, y, width, height) { this.bounds = { x, y, width, height }; return this; }
  setSize(width, height) { Object.assign(this, { width, height }); return this; }
  startFollow(target, roundPixels, lerpX, lerpY, offsetX, offsetY) {
    Object.assign(this, { target, roundPixels, lerpX, lerpY });
    return this.setFollowOffset(offsetX, offsetY);
  }
  setFollowOffset(x, y) { this.offset = { x, y }; return this; }
  setZoom(zoom) { this.zoom = zoom; return this; }
  on(type, callback) { this.handlers.set(type, callback); return this; }
  off(type) { this.handlers.delete(type); return this; }
  centerOn(x, y) {
    const visibleWidth = this.width / this.zoom, visibleHeight = this.height / this.zoom;
    const minX = this.bounds.x + (visibleWidth - this.width) / 2;
    const minY = this.bounds.y + (visibleHeight - this.height) / 2;
    this.scrollX = Math.max(minX, Math.min(minX + this.bounds.width - visibleWidth, x - this.width / 2));
    this.scrollY = Math.max(minY, Math.min(minY + this.bounds.height - visibleHeight, y - this.height / 2));
    return this;
  }
  preRender() {
    this.centerOn(this.target.x - this.offset.x, this.target.y - this.offset.y);
    this.handlers.get('followupdate')?.();
  }
  getWorldPoint(x, y) {
    return {
      x: (x - this.x - this.width / 2) / this.zoom + this.width / 2 + this.scrollX,
      y: (y - this.y - this.height / 2) / this.zoom + this.height / 2 + this.scrollY,
    };
  }
}

function setup({ devicePixelRatio = 1, zoom = 1, clientWidth = 768, clientHeight = 512, parentClientWidth, parentClientHeight } = {}) {
  const events = [], listeners = new Map();
  const host = { clientWidth, clientHeight, left: 17, top: 23,
    parentElement: { clientWidth: parentClientWidth, clientHeight: parentClientHeight },
  };
  const Phaser = {
    Scene: class {}, AUTO: 0, Scale: { NONE: 0, FIT: 1, CENTER_BOTH: 1 },
    Game: class { constructor(config) { this.config = config; } },
  };
  const window = {
    Phaser, devicePixelRatio, ForestHud: { zoom }, matchMedia: () => ({ matches: false }),
    dispatchEvent: event => events.push(event),
    addEventListener: (type, callback) => listeners.set(type, callback),
    removeEventListener: type => listeners.delete(type),
  };
  const context = vm.createContext({
    window, Phaser, localStorage: { getItem: () => null }, performance: { now: () => 0 },
    document: { documentElement: { classList: { contains: () => false } }, getElementById: () => host, activeElement: { tagName: 'DIV' } },
    CustomEvent: class { constructor(type, options) { this.type = type; this.detail = options?.detail; } },
  });
  vm.runInContext(source, context);
  const game = window.carrotForestPhaserGame;
  const config = game.config;
  const scene = new config.scene();
  const camera = new Camera(config.width, config.height);
  const canvas = {
    width: config.width, height: config.height, style: {},
    get clientWidth() { return host.clientWidth; },
    get clientHeight() { return host.clientHeight; },
    getBoundingClientRect() { return { left: host.left, top: host.top, width: host.clientWidth, height: host.clientHeight }; },
  };
  // Phaser NONE resizes the physical canvas, preserves the configured display
  // zoom, then refreshes the DOM bounds used by InputManager.transformX/Y.
  const scale = {
    width: config.width, height: config.height, zoom: config.scale.zoom,
    calls: [], displayScale: {},
    setZoom(value) { this.calls.push(['setZoom', value]); this.zoom = value; return this.refresh(); },
    resize(width, height) {
      this.calls.push(['resize', width, height]);
      const previousWidth = this.width, previousHeight = this.height;
      Object.assign(this, { width, height });
      Object.assign(canvas, { width, height });
      canvas.style.width = `${width * this.zoom}px`;
      canvas.style.height = `${height * this.zoom}px`;
      // CameraManager only automatically resizes a previous full-game view.
      if (camera.width === previousWidth && camera.height === previousHeight) camera.setSize(width, height);
      return this.refresh();
    },
    refresh() {
      this.calls.push(['refresh']);
      this.canvasBounds = canvas.getBoundingClientRect();
      this.displayScale = { x: canvas.width / this.canvasBounds.width, y: canvas.height / this.canvasBounds.height };
      return this;
    },
    transformX(x) { return (x - this.canvasBounds.left) * this.displayScale.x; },
    transformY(y) { return (y - this.canvasBounds.top) * this.displayScale.y; },
  };
  game.canvas = canvas;
  game.scale = scale;
  scene.game = game;
  scene.scale = scale;
  scene.cameras = { main: camera };
  scene.player = { x: scene.avatar.x, y: scene.avatar.y };
  scale.refresh();
  scene.configureWorldCamera();
  scene.attachWindowEvents();
  return { scene, camera, config, window, events, listeners, host, game, canvas, scale };
}

function near(actual, expected) { assert.ok(Math.abs(actual - expected) < 1e-9, `${actual} should equal ${expected}`); }

function attackButton(scene) {
  const display = () => ({
    setVisible(value) { this.visible = value; return this; },
    setPosition(x, y) { Object.assign(this, { x, y }); return this; },
    setScale(x, y = x) { Object.assign(this, { scaleX: x, scaleY: y }); return this; },
  });
  scene.ratAttackButton = Object.assign(display(), {
    input: { hitArea: { x: 0, y: 0, width: 112, height: 38 } },
    setText(text) { this.text = text; return this; },
  });
  scene.ratAttackPlate = display();
  for (const method of ['clear', 'fillStyle', 'fillRoundedRect', 'fillPoints', 'fillTriangle', 'lineStyle', 'strokeRoundedRect']) {
    scene.ratAttackPlate[method] = function () { return this; };
  }
  Object.assign(scene, { ratActor: { x: 374, y: 286 }, ratActive: true, ratHovered: true, ratEventId: 7 });
  return scene.ratAttackButton;
}

function assertAttackFits(scene, camera, margin = 12) {
  const button = scene.ratAttackButton, plate = scene.ratAttackPlate;
  const topLeft = camera.getWorldPoint(camera.x || 0, camera.y || 0);
  const bottomRight = camera.getWorldPoint((camera.x || 0) + camera.width, (camera.y || 0) + camera.height);
  assert.equal(button.visible, true); assert.equal(plate.visible, true);
  assert.ok(button.x - 61 * button.scaleX >= topLeft.x + margin - 1e-9, 'left halo stays in the current view');
  assert.ok(button.x + 61 * button.scaleX <= bottomRight.x - margin + 1e-9, 'right halo stays in the current view');
  assert.ok(button.y - 24 * button.scaleY >= topLeft.y + margin - 1e-9, 'top halo stays in the current view');
  assert.ok(button.y + 28 * button.scaleY <= bottomRight.y - margin + 1e-9, 'downward pointer stays in the current view');
  assert.deepEqual([button.x, button.y, button.scaleX, button.scaleY], [plate.x, plate.y, plate.scaleX, plate.scaleY]);
  assert.deepEqual(button.input.hitArea, { x: 0, y: 0, width: 112, height: 38 }, 'the local clickable rectangle is never rewritten');
}

test('400 percent hover attack controls include the halo and pointer inside every current camera edge', () => {
  const { scene, camera, window } = setup({ clientWidth: 390, clientHeight: 260, zoom: 4 });
  Object.assign(scene.player, { x: 400, y: 350 }); camera.preRender();
  const button = attackButton(scene), hitArea = button.input.hitArea;
  const corners = [camera.getWorldPoint(0, 0), camera.getWorldPoint(camera.width, camera.height)];
  near(corners[1].x - corners[0].x, 192);
  for (const [x, y] of [[374, 286], [490, 350], [305, 350], [400, 512], [0, 0], [768, 512]]) {
    Object.assign(scene.ratActor, { x, y });
    scene.pointerAttackEventId = scene.ratEventId;
    scene.ratAttackHovered = true;
    for (const reduced of [false, true]) {
      window.matchMedia = () => ({ matches: reduced });
      scene.updateRatAttackButton(); assertAttackFits(scene, camera);
      assert.equal(button.scaleX, 1); assert.equal(button.input.hitArea, hitArea);
      assert.equal(button.text, '접근 중…', 'an offscreen tracked animal does not hide the active control');
    }
  }
});

test('portrait 400 percent scales both attack layers to an 83-world-unit view and restores scale after zooming out', () => {
  const { scene, camera } = setup({ clientWidth: 390, clientHeight: 600, zoom: 4 });
  Object.assign(scene.player, { x: 400, y: 350 }); camera.preRender();
  const button = attackButton(scene), hitArea = button.input.hitArea;
  scene.updateRatAttackButton(); assertAttackFits(scene, camera);
  near(camera.width / camera.zoom, 83.2);
  near(button.scaleX, (83.2 - 24) / 122);
  scene.setCameraZoom(1);
  scene.updateRatAttackButton(); assertAttackFits(scene, camera);
  assert.equal(button.scaleX, 1); assert.equal(button.scaleY, 1);
  assert.equal(button.input.hitArea, hitArea);
});

test('hover attack viewport conversion includes a nonzero camera origin rather than assuming canvas origin', () => {
  const { scene, camera } = setup({ clientWidth: 390, clientHeight: 600, zoom: 4 });
  Object.assign(scene.player, { x: 400, y: 350 }); camera.preRender();
  Object.assign(camera, { x: 75, y: 31 });
  const calls = [], getWorldPoint = camera.getWorldPoint.bind(camera);
  camera.getWorldPoint = (x, y) => { calls.push([x, y]); return getWorldPoint(x, y); };
  attackButton(scene); scene.updateRatAttackButton();
  assert.deepEqual(calls, [[75, 31], [75 + camera.width, 31 + camera.height]]);
  assertAttackFits(scene, camera);
  near(scene.ratAttackButton.scaleX, (83.2 - 24) / 122);
});

test('invalid hover attack cameras retain world fallback and clear any previous portrait scale', () => {
  const { scene, camera } = setup({ clientWidth: 390, clientHeight: 600, zoom: 4 });
  const button = attackButton(scene);
  scene.updateRatAttackButton(); assert.ok(button.scaleX < 1);
  for (const invalid of [undefined, {}, { width: NaN, height: 10, getWorldPoint() {} },
    { width: 10, height: 0, getWorldPoint() {} },
    { width: 10, height: 10, getWorldPoint: () => ({ x: NaN, y: 0 }) },
    { width: 10, height: 10, getWorldPoint: () => ({ x: 1, y: 1 }) }]) {
    scene.cameras.main = invalid;
    Object.assign(scene.ratActor, { x: 0, y: 0 }); scene.updateRatAttackButton();
    assert.deepEqual([button.x, button.y, button.scaleX, button.scaleY], [60, 24, 1, 1]);
    Object.assign(scene.ratActor, { x: 768, y: 350 }); scene.updateRatAttackButton();
    assert.deepEqual([button.x, button.y], [708, 278]);
  }
  scene.cameras.main = camera;
  Object.assign(camera, { width: 2, height: 2, zoom: 1 });
  scene.updateRatAttackButton(); assertAttackFits(scene, camera, .5);
  assert.ok(Number.isFinite(button.scaleX) && button.scaleX > 0, 'tiny valid views shrink the gutter without a non-fitting minimum scale');
});

test('the hover attack gutter absorbs one mounted movement frame before camera follow renders', () => {
  for (const [clientWidth, clientHeight] of [[390, 260], [390, 600]]) {
    const { scene, camera } = setup({ clientWidth, clientHeight, zoom: 4 });
    attackButton(scene);
    for (const [dx, dy] of [[-7.4, 0], [7.4, 0], [0, -7.4], [0, 7.4]]) {
      Object.assign(scene.player, { x: 400, y: 350 }); camera.preRender();
      Object.assign(scene.ratActor, { x: dx < 0 ? 768 : 0, y: dy < 0 ? 512 : 0 });
      scene.updateRatAttackButton(); assertAttackFits(scene, camera);
      scene.player.x += dx; scene.player.y += dy; camera.preRender();
      assertAttackFits(scene, camera, 3);
    }
  }
});

test('new 100 percent shows the old 50 percent world at 3:2 without changing saved coordinates or sprite scale', () => {
  for (const [devicePixelRatio, backing] of [[1, 2], [1.25, 2], [2, 2], [3, 2], [4, 2]]) {
    const { config, scene, camera } = setup({ devicePixelRatio });
    assert.equal(config.width, 768 * backing);
    assert.equal(config.height, 512 * backing);
    assert.equal(config.width / config.height, 3 / 2);
    assert.equal(scene.avatar.x, 384);
    assert.equal(scene.avatar.y, 352);
    assert.equal(scene.avatar.tuning.worldScale, .43);
    assert.equal(scene.cameraZoom, 1);
    assert.equal(scene.worldCameraZoom, 1);
    assert.equal(camera.zoom, backing);
    // v156 used a 3072x2048 backing and a 4x camera at the former 50%.
    assert.equal(camera.width / camera.zoom, 3072 / 4);
    assert.equal(camera.height / camera.zoom, 2048 / 4);
    assert.equal(config.scale.mode, 0);
    assert.equal(config.scale.zoom, 1 / backing);
    assert.equal(config.pixelArt, true);
    assert.equal(config.render.antialias, false);
    assert.equal(config.render.roundPixels, true);
  }
});

test('a display-none host boots with its laid-out parent aspect and refreshes the actual canvas bounds after becoming ready', () => {
  for (const [parentClientWidth, parentClientHeight] of [[1200, 900], [1920, 800], [390, 844], [3840, 2160]]) {
    const { config, host, camera, scale, window } = setup({ clientWidth: 0, clientHeight: 0, parentClientWidth, parentClientHeight });
    const density = Math.min(2, 4096 / Math.max(parentClientWidth, parentClientHeight));
    assert.equal(config.width, Math.round(parentClientWidth * density), 'hidden host must not fall back to the authored world width');
    assert.equal(config.height, Math.round(parentClientHeight * density), 'hidden host must not fall back to the authored world height');
    near(camera.zoom, Math.max(config.width / 768, config.height / 512));
    Object.assign(host, { clientWidth: parentClientWidth, clientHeight: parentClientHeight });
    // Revealing the absolutely positioned host does not resize its frame; the
    // ready path must explicitly refresh even when backing dimensions match.
    window.ForestCamera.resizeViewport();
    near(scale.displayScale.x, camera.width / parentClientWidth);
    near(scale.displayScale.y, camera.height / parentClientHeight);
    const projected = window.ForestCamera.worldToScreen(384, 352);
    const inverse = camera.getWorldPoint(
      scale.transformX(host.left + projected.x * parentClientWidth),
      scale.transformY(host.top + projected.y * parentClientHeight),
    );
    near(inverse.x, 384); near(inverse.y, 352);
  }
  const { config } = setup({ clientWidth: 960, clientHeight: 640, parentClientWidth: 1920, parentClientHeight: 1080 });
  assert.equal(config.width, 1920, 'a visible host takes precedence over its parent fallback');
  assert.equal(config.height, 1280);
});

test('scene boot reveals the Phaser host before resizing and before advertising readiness', () => {
  assert.match(source, /document\.documentElement\.classList\.add\("phaser-world-ready"\);\s*this\.resizeViewport\(\);\s*window\.carrotForestPhaserActive\s*=\s*true;/,
    'the ready-class visibility change cannot rely on the unchanged parent ResizeObserver to refresh input bounds');
});

test('100 through 400 percent changes only camera magnification and centers the stable avatar body', () => {
  const { scene, camera, config, events, listeners, window } = setup();
  const saved = JSON.stringify(scene.avatar), backingWidth = config.width;
  for (const zoom of [1, 1.5, 2, 2.5, 3, 3.5, 4]) {
    listeners.get('forest-camera-zoom')({ detail: { zoom } });
    assert.equal(scene.cameraZoom, zoom);
    assert.equal(scene.worldCameraZoom, zoom);
    assert.equal(camera.zoom, zoom * 2);
    assert.equal(config.width, backingWidth);
    assert.equal(JSON.stringify(scene.avatar), saved);
    if (zoom >= 1.5) {
      const center = window.ForestCamera.worldToScreen(scene.player.x, scene.player.y - scene.cameraFocusOffsetY());
      near(center.x, .5);
      near(center.y, .5);
    }
  }
  assert.equal(events.some(event => event.type === 'forest-phaser-position'), false);
  assert.equal(camera.target, scene.player);
  assert.equal(camera.roundPixels, false, 'a fractional player center must not be rounded during camera following');
});

test('world bounds fill every square, ultrawide, portrait and fullscreen corner at all zoom levels', () => {
  for (const [clientWidth, clientHeight] of [[768, 512], [960, 960], [1920, 800], [390, 844], [3840, 2160], [7680, 4320]]) {
    const { scene, camera } = setup({ clientWidth, clientHeight });
    for (const zoom of [1, 1.5, 2, 2.5, 3, 3.5, 4]) {
      scene.setCameraZoom(zoom);
      for (const [x, y] of [[28, 42], [740, 42], [28, 480], [740, 480], [384, 352]]) {
        Object.assign(scene.player, { x, y });
        camera.preRender();
        const topLeft = camera.getWorldPoint(0, 0), bottomRight = camera.getWorldPoint(camera.width, camera.height);
        assert.ok(topLeft.x >= -1e-9 && topLeft.y >= -1e-9, `${clientWidth}x${clientHeight} must not expose its top/left edge`);
        assert.ok(bottomRight.x <= 768 + 1e-9 && bottomRight.y <= 512 + 1e-9, `${clientWidth}x${clientHeight} must not expose its bottom/right edge`);
        if (zoom === 1 && clientWidth / clientHeight === 1.5) {
          near(topLeft.x, 0); near(topLeft.y, 0);
          near(bottomRight.x, 768); near(bottomRight.y, 512);
        }
      }
    }
  }
});

test('responsive backing covers the host uniformly with a two-pixel density and a 4096-pixel edge cap', () => {
  for (const [clientWidth, clientHeight] of [[768, 512], [960, 960], [1920, 800], [390, 844], [3840, 1600], [7680, 4320]]) {
    const { config, scene, camera, scale, window } = setup({ clientWidth, clientHeight });
    const density = Math.min(2, 4096 / Math.max(clientWidth, clientHeight));
    assert.equal(config.width, Math.round(clientWidth * density));
    assert.equal(config.height, Math.round(clientHeight * density));
    assert.ok(Math.max(config.width, config.height) <= 4096);
    near(scale.zoom, 1 / density);
    const cover = Math.max(camera.width / 768, camera.height / 512);
    near(camera.zoom, cover);
    near(scene.worldCameraZoom, 1);
    // Cover fills one authored axis exactly and crops only the surplus axis.
    assert.ok(Math.abs(camera.width / camera.zoom - 768) < 1e-9 || Math.abs(camera.height / camera.zoom - 512) < 1e-9);
    const origin = window.ForestCamera.worldToScreen(350, 250);
    const right = window.ForestCamera.worldToScreen(360, 250);
    const down = window.ForestCamera.worldToScreen(350, 260);
    const xPixels = (right.x - origin.x) * clientWidth;
    const yPixels = (down.y - origin.y) * clientHeight;
    // Integer backing dimensions can differ from the ideal aspect by at most
    // one backing pixel; prohibit any meaningful independent-axis stretch.
    assert.ok(Math.abs(xPixels - yPixels) <= Math.max(xPixels, yPixels) / Math.min(camera.width, camera.height) + 1e-9);
  }
});

test('maximizing, rotating and leaving fullscreen resize only the viewport and immediately refresh pointer coordinates', () => {
  const { scene, camera, window, host, canvas, scale, events } = setup({ zoom: 2 });
  const savedAvatar = JSON.stringify(scene.avatar), playerPosition = { ...scene.player };
  for (const [clientWidth, clientHeight] of [[1440, 900], [3440, 1440], [3840, 2160], [390, 844], [960, 960], [7680, 4320], [768, 512]]) {
    Object.assign(host, { clientWidth, clientHeight });
    window.ForestCamera.resizeViewport();
    const density = Math.min(2, 4096 / Math.max(clientWidth, clientHeight));
    assert.equal(camera.width, Math.round(clientWidth * density));
    assert.equal(camera.height, Math.round(clientHeight * density));
    assert.equal(canvas.width, camera.width);
    assert.equal(canvas.height, camera.height);
    near(scale.zoom, 1 / density);
    near(scale.displayScale.x, camera.width / clientWidth);
    near(scale.displayScale.y, camera.height / clientHeight);
    near(camera.zoom, 2 * Math.max(camera.width / 768, camera.height / 512));
    assert.equal(scene.cameraZoom, 2, 'resizing must preserve the selected HUD zoom');
    assert.equal(JSON.stringify(scene.avatar), savedAvatar);
    assert.deepEqual(scene.player, playerPosition);
    assert.equal(camera.target, scene.player);
    const body = window.ForestCamera.worldToScreen(scene.player.x, scene.player.y - scene.cameraFocusOffsetY());
    near(body.x, .5); near(body.y, .5);
    for (const point of [{ x: 0, y: 0 }, { x: 384, y: 352 }, { x: 650, y: 410 }]) {
      const projected = window.ForestCamera.worldToScreen(point.x, point.y);
      const pointerX = scale.transformX(host.left + projected.x * clientWidth);
      const pointerY = scale.transformY(host.top + projected.y * clientHeight);
      const inverse = camera.getWorldPoint(pointerX, pointerY);
      near(inverse.x, point.x); near(inverse.y, point.y);
    }
    const view = events.at(-1);
    assert.equal(view.type, 'forest-camera-view');
    assert.equal(view.detail.viewportWidth, camera.width);
    assert.equal(view.detail.viewportHeight, camera.height);
    const count = events.length;
    window.ForestCamera.resizeViewport();
    assert.equal(events.length, count, 'an unchanged resize must not repeat DOM layout notifications');
  }
  assert.equal(scale.calls.filter(([name]) => name === 'resize').length, 7);
  assert.equal(events.some(event => event.type === 'forest-phaser-position'), false);
});

test('capped fullscreen sizes refresh display density even when the physical backing dimensions are unchanged', () => {
  const { host, camera, scale, window, scene } = setup({ clientWidth: 3840, clientHeight: 2160 });
  const dimensions = [camera.width, camera.height];
  const worldZoom = camera.zoom;
  Object.assign(host, { clientWidth: 7680, clientHeight: 4320 });
  window.ForestCamera.resizeViewport();
  assert.deepEqual([camera.width, camera.height], dimensions, 'same-aspect fullscreen must retain the capped backing budget');
  near(scale.zoom, 7680 / 4096);
  near(scale.displayScale.x, 4096 / 7680);
  near(scale.displayScale.y, 2304 / 4320);
  near(camera.zoom, worldZoom);
  assert.equal(scene.cameraZoom, 1);
});

test('position-only layout changes refresh the pointer origin and a non-default camera viewport is restored explicitly', () => {
  const { host, camera, scale, window } = setup();
  Object.assign(host, { left: 211, top: 109 });
  window.ForestCamera.resizeViewport();
  near(scale.transformX(211 + 384), 768);
  near(scale.transformY(109 + 256), 512);
  assert.equal(scale.calls.filter(([name]) => name === 'resize').length, 0, 'a layout offset alone must not reallocate the canvas');
  camera.setSize(100, 100);
  window.ForestCamera.resizeViewport();
  assert.equal(camera.width, 1536, 'restore the whole game view even when CameraManager cannot infer an automatic resize');
  assert.equal(camera.height, 1024);
  near(camera.width / camera.zoom, 768);
  near(camera.height / camera.zoom, 512);
});

test('DOM projection and pointer inverse agree immediately after zoom and avatar follow updates', () => {
  const { scene, camera, window, events } = setup();
  for (const zoom of [1, 2, 4]) {
    scene.setCameraZoom(zoom);
    for (const point of [{ x: 0, y: 0 }, { x: 384, y: 352 }, { x: 650, y: 410 }]) {
      const screen = window.ForestCamera.worldToScreen(point.x, point.y);
      const inverse = camera.getWorldPoint(screen.x * camera.width, screen.y * camera.height);
      near(inverse.x, point.x); near(inverse.y, point.y);
    }
  }
  const count = events.length;
  camera.preRender();
  assert.equal(events.length, count, 'an unchanged view does not repeat DOM layout notifications');
  scene.player.x += 7.125;
  camera.preRender();
  assert.equal(events.length, count + 1);
  const update = events.at(-1);
  assert.equal(update.type, 'forest-camera-view');
  assert.equal(update.detail.displayZoom, 4);
  assert.equal(update.detail.worldZoom, 4);
  assert.equal(update.detail.viewportWidth, 1536);
  assert.deepEqual({ ...update.detail.avatar }, { ...window.ForestCamera.avatarAnchor() });
});

test('nickname projection stays sharp in DOM and updates when only the edge-bound avatar or name changes', () => {
  const { scene, camera, window, events } = setup({ zoom: 1 });
  const first = window.ForestCamera.avatarAnchor();
  assert.equal(first.name, scene.avatar.name);
  assert.equal(first.scene, 'world');
  assert.ok(first.y < window.ForestCamera.worldToScreen(scene.player.x, scene.player.y).y);
  const scroll = [camera.scrollX, camera.scrollY], count = events.length;
  scene.player.x += 8; camera.preRender();
  assert.deepEqual([camera.scrollX, camera.scrollY], scroll, 'minimum zoom keeps the whole world in frame');
  assert.equal(events.length, count + 1, 'avatar label must move even when camera scroll cannot');
  assert.ok(events.at(-1).detail.avatar.x > first.x);
  scene.avatar.name = '바뀐 닉네임'; camera.preRender();
  assert.equal(events.at(-1).detail.avatar.name, '바뀐 닉네임');
  assert.doesNotMatch(source, /this\.nameplate\s*=/, 'nickname must not also be drawn into the pixel canvas');
});

test('nickname uses actual LPC opaque bounds instead of the transparent composite margin', () => {
  const { scene } = setup({ zoom: 2, clientWidth: 1399.5, clientHeight: 933 });
  const pixels = new Uint8ClampedArray(224 * 288 * 4);
  for (let y = 111; y <= 249; y++) for (let x = 75; x <= 148; x++) pixels[(y * 224 + x) * 4 + 3] = 255;
  pixels[3] = 1; pixels[(20 * 224 + 100) * 4 + 3] = 31;
  const bounds = scene.measureAvatarOpaqueBounds(pixels, 224, 288);
  assert.deepEqual({ ...bounds }, { left: 75, top: 111, right: 148, bottom: 249 });
  assert.equal(scene.measureAvatarOpaqueBounds(new Uint8ClampedArray(224 * 288 * 4), 224, 288), null);
  scene.avatarOpaqueBounds = bounds;
  scene.premiumAvatar = { y: 0, height: 288, originY: .87, scaleY: .43 };
  const headWorldY = scene.player.y + (111 - 288 * .87) * .43;
  const hairTop = scene.worldToScreen(scene.player.x, headWorldY);
  const anchor = scene.avatarAnchor();
  near((hairTop.y - anchor.y) * 933, 8);
  const obsoleteTop = scene.worldToScreen(scene.player.x, scene.player.y - 288 * .87 * .43 - 7);
  assert.ok((anchor.y - obsoleteTop.y) * 933 > 180, 'regression: remove the roughly 180px floating gap seen in the large viewport');
});

test('nickname stays eight CSS pixels above visible hair across zoom, resized frames, scale, and jumping', () => {
  const { scene, camera, events, host, window } = setup();
  scene.avatarOpaqueBounds = { left: 75, top: 111, right: 148, bottom: 249 };
  scene.premiumAvatar = { y: 0, height: 288, originY: .87, scaleY: .43 };
  for (const cssHeight of [220, 512, 933, 1024]) for (const zoom of [1, 2, 4]) for (const scale of [.32, .43, .58]) {
    host.clientHeight = cssHeight;
    window.ForestCamera.resizeViewport();
    scene.premiumAvatar.scaleY = scale;
    scene.setCameraZoom(zoom);
    for (const jumpY of [0, -16]) {
      scene.premiumAvatar.y = jumpY;
      const headY = scene.player.y + jumpY + (111 - 288 * .87) * scale;
      const hair = scene.worldToScreen(scene.player.x, headY);
      near((hair.y - scene.avatarAnchor().y) * cssHeight, 8);
    }
  }
  const count = events.length;
  scene.avatarOpaqueBounds.top = 108; camera.preRender();
  assert.equal(events.length, count + 1, 'a changed hair bound updates the DOM even without camera movement');
  const y = events.at(-1).detail.avatar.y;
  host.clientHeight = 768; window.ForestCamera.resizeViewport();
  assert.notEqual(events.at(-1).detail.avatar.y, y, 'responsive resizing recomputes the CSS-pixel gap');
});

test('the rendered LPC frame supplies fresh opaque bounds and empty intermediate loads retain the last valid bounds', () => {
  const { scene, window } = setup();
  let pixels = new Uint8ClampedArray(224 * 288 * 4);
  pixels[(109 * 224 + 112) * 4 + 3] = 255;
  pixels[(249 * 224 + 112) * 4 + 3] = 255;
  const context = { clearRect() {}, getImageData() { return { data: pixels }; } };
  scene.compositeTexture = { getContext: () => context, refresh() {} };
  scene.premiumAvatar = { setVisible() { return this; }, setScale(value) { this.scaleY = value; return this; } };
  window.CarrotAvatarCompositor = {};
  window.LpcAvatarEngine = { draw: () => true };
  scene.setPremiumFrame('down', false, 0);
  assert.equal(scene.avatarOpaqueBounds.top, 109);
  assert.equal(scene.premiumAvatar.scaleY, .43);
  pixels = new Uint8ClampedArray(224 * 288 * 4);
  scene.setPremiumFrame('down', false, 140);
  assert.equal(scene.avatarOpaqueBounds.top, 109, 'temporary empty redraws must not fling the label up to texture y=0');
});

test('HUD boot zoom, clamps, resets, and event cleanup use one camera contract', () => {
  const { scene, camera, listeners, window } = setup({ zoom: 1.5 });
  assert.equal(scene.cameraZoom, 1.5);
  for (const [value, expected] of [[-1, 1], [.5, 1], [12, 4], [NaN, 1], [undefined, 1], [1, 1]]) {
    listeners.get('forest-camera-zoom')({ detail: { zoom: value } });
    assert.equal(scene.cameraZoom, expected);
  }
  scene.detachWindowEvents();
  assert.equal(listeners.has('forest-camera-zoom'), false);
  assert.equal(listeners.size, 0, 'all owned window handlers must be removed on scene teardown');
  assert.equal(camera.handlers.has('followupdate'), false);
  assert.equal(window.ForestCamera, undefined);
  assert.doesNotMatch(source, /keyboard\.on\("keydown-C"/);
  assert.doesNotMatch(source, /event\.key !== "0"/);
});
