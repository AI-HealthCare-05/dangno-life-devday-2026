const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.join(__dirname, '../src/frontend');
const phaser = fs.readFileSync(path.join(root, 'forest-phaser.js'), 'utf8');

test('access gate supplies the verified display name before loading game scripts', async () => {
  let seededAtScriptLoad = null;
  const window = { GandangAuthSession: { resolve: async () => ({ profile: { name: '  계정 이름  ' } }) }, addEventListener() {} };
  const document = {
    documentElement: { classList: { contains: () => false, remove() {} } },
    querySelector: () => null, getElementById: () => null,
    querySelectorAll: () => [{ src: 'forest-game.js' }],
    createElement: () => ({}), head: { append(script) { seededAtScriptLoad = window.ForestAccountDisplayName; script.onload(); } },
    addEventListener() {},
  };
  vm.runInNewContext(fs.readFileSync(path.join(root, 'forest-access.js'), 'utf8'), { window, document, AbortController, setTimeout, clearTimeout });
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(seededAtScriptLoad, '계정 이름');
});

function sceneHarness() {
  const Phaser = { Scene: class {}, AUTO: 0, Scale: { NONE: 0 }, Game: class { constructor(config) { this.config = config; } } };
  const window = { Phaser, ForestAccountDisplayName: '현재 계정' };
  vm.runInNewContext(phaser, { window, Phaser, document: { getElementById: () => ({}) },
    localStorage: { getItem: () => JSON.stringify({ avatar: { name: '저장된 게스트', x: 300, y: 350 } }) } });
  return new window.carrotForestPhaserGame.config.scene();
}

test('renderer starts with the account name and retains saved avatar coordinates', () => {
  const scene = sceneHarness();
  assert.equal(scene.avatar.name, '현재 계정');
  assert.equal(scene.avatar.x, 300); assert.equal(scene.avatar.y, 350);
});

test('home record player never flashes in the forest or renders a missing texture', () => {
  const scene = sceneHarness(), images = [];
  const actor = () => ({ setOrigin() { return this; }, setDisplaySize() { return this; },
    setDepth() { return this; }, setVisible(value) { this.visible = value; return this; } });
  let available = false;
  scene.textures = { exists: () => available };
  scene.add = { image(...args) { images.push(args); return actor(); }, text: actor, container: actor };
  scene.createHomeRecordPlayer();
  assert.equal(images.length, 0); assert.equal(scene.recordPlayerActor, null);
  available = true; scene.createHomeRecordPlayer();
  assert.equal(scene.recordPlayerActor.visible, false);
  scene.sceneName = 'home'; scene.createHomeRecordPlayer();
  assert.equal(scene.recordPlayerActor.visible, true);
  assert.equal(images[0][2], 'home-record-player');
  const art = fs.readFileSync(path.join(root, 'assets/home-record-player-cottage-v1.png'));
  assert.equal(art.toString('ascii', 1, 4), 'PNG', 'required source asset is included in mobile builds');
});
