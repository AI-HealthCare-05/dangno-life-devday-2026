const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../src/frontend/forest-hud.js'), 'utf8');

function createHud({ width = 1800, height = 1200, storedName = null, storageBlocked = false, nameEditor = false } = {}) {
  const elements = {}, events = [], classes = new Set(), storage = new Map(), windowListeners = {};
  const document = { activeElement: null };
  if (storedName !== null) storage.set('carrot-forest-name-v1', storedName);
  function createElement(tagName = 'DIV', parentElement = null) {
    const listeners = {}, attrs = {};
    return { tagName, parentElement, hidden: false, style: {}, value: '', textContent: '', disabled: false,
      isContentEditable: false, role: '',
      addEventListener(type, callback) { (listeners[type] ??= []).push(callback); },
      setAttribute(name, value) { attrs[name] = value; }, getAttribute(name) { return attrs[name]; },
      focus() { document.activeElement = this; }, select() { this.selected = true; },
      setCustomValidity(message) { this.validationMessage = message; }, reportValidity() { this.reported = true; },
      closest() {
        for (let node = this; node; node = node.parentElement) {
          if (['FORM', 'INPUT', 'TEXTAREA', 'SELECT'].includes(node.tagName) || node.isContentEditable || node.role === 'textbox') return node;
        }
        return null;
      },
      emit(type, values = {}) {
        const event = { type, target: this, defaultPrevented: false, propagationStopped: false,
          preventDefault() { this.defaultPrevented = true; }, stopPropagation() { this.propagationStopped = true; }, ...values };
        for (const callback of listeners[type] ?? []) callback(event);
        return event;
      },
      click() { if (!this.disabled) return this.emit('click'); },
    };
  }
  document.body = createElement('BODY');
  document.body.classList = { toggle(name, value) { if (value) classes.add(name); else classes.delete(name); } };
  document.activeElement = document.body;
  for (const id of ['zoom-in', 'zoom-out', 'ui-toggle', 'controls-toggle', 'objects-toggle', 'reset-position']) elements[id] = createElement('BUTTON', document.body);
  for (const id of ['zoom-level', 'controls-content', 'placed-list', 'phaser-world']) elements[id] = createElement('DIV', document.body);
  elements['mobile-panel-shortcut'] = createElement('A', document.body);
  elements['forest-main'] = { scrollTop: 0, getBoundingClientRect: () => ({ top: 66 }), scrollTo({ top }) { this.scrollTop = top; } };
  elements['avatar-editor'] = { getBoundingClientRect: () => ({ top: 800 - elements['forest-main'].scrollTop }) };
  if (nameEditor) {
    elements['forest-name-form'] = createElement('FORM', document.body);
    elements['forest-name-form'].hidden = true;
    elements['forest-name-input'] = createElement('INPUT', elements['forest-name-form']);
    elements['edit-forest-name'] = createElement('BUTTON', document.body);
    elements['cancel-forest-name'] = createElement('BUTTON', elements['forest-name-form']);
  }
  const area = { clientWidth: width, clientHeight: height }, frame = { style: {} };
  let refreshCount = 0, boundsRefreshCount = 0, resizeCallback, modalOpen = false;
  const window = {
    ForestCamera: { resizeViewport() { refreshCount += 1; } },
    carrotForestPhaserGame: { scale: { refresh() { boundsRefreshCount += 1; } } },
    dispatchEvent(event) { events.push(event); for (const callback of windowListeners[event.type] ?? []) callback(event); },
    addEventListener(type, callback) { (windowListeners[type] ??= []).push(callback); },
  };
  document.getElementById = id => elements[id] ?? null;
  document.querySelector = selector => {
    if (selector === '.canvas-workarea') return area;
    if (selector === '.canvas-frame') return frame;
    if (selector === '.mobile-panel-shortcut') return elements['mobile-panel-shortcut'];
    if (selector === 'dialog[open], [aria-modal="true"]:not([hidden])') return modalOpen ? { open: true } : null;
    return null;
  };
  vm.runInNewContext(source, { window, document,
    localStorage: { getItem(key) { if (storageBlocked) throw Error('blocked'); return storage.get(key) ?? null; },
      setItem(key, value) { if (storageBlocked) throw Error('blocked'); storage.set(key, value); } },
    CustomEvent: class { constructor(type, options) { this.type = type; this.detail = options?.detail; } },
    requestAnimationFrame: callback => callback(), ResizeObserver: class { constructor(callback) { resizeCallback = callback; } observe() {} },
  });
  return { hud: window.ForestHud, window, document, elements, area, frame, events, classes, storage, createElement,
    resize: () => resizeCallback(), refreshCount: () => refreshCount, boundsRefreshCount: () => boundsRefreshCount,
    scroll: () => { for (const callback of windowListeners.scroll ?? []) callback(); },
    setModalOpen: value => { modalOpen = value; },
    click: id => { elements[id].focus(); return elements[id].click(); },
    submit: () => elements['forest-name-form'].emit('submit'),
    key(key, values = {}) {
      const target = values.target ?? document.activeElement;
      const event = target.emit('keydown', { key, ...values });
      if (!event.propagationStopped) for (const callback of windowListeners.keydown ?? []) callback(event);
      return event;
    },
  };
}

test('the responsive frame fills both available axes with the rebased 100% default', () => {
  const app = createHud();
  assert.equal(app.frame.style.width, '1800px'); assert.equal(app.frame.style.height, '1200px');
  assert.equal(app.hud.zoom, 1); assert.equal(app.elements['zoom-level'].textContent, '100%');
  assert.equal(app.events.at(-1).type, 'forest-camera-zoom'); assert.equal(app.events.at(-1).detail.zoom, 1);
  assert.equal(app.refreshCount(), 1); app.resize();
  assert.equal(app.refreshCount(), 1, 'unchanged observer callbacks must not loop viewport resize');
  assert.equal(app.elements['forest-name-form'], undefined, 'the removed name editor is optional');
});

test('viewport fills wide, tall, and fullscreen areas with no former maximum or 3:2 letterbox', () => {
  for (const [width, height] of [
    [1400, 900], [1200, 1000], [2560, 1600], [3440, 1440],
    [760, 450], [390, 700],
  ]) {
    const app = createHud({ width, height });
    assert.equal(app.frame.style.width, `${width}px`);
    assert.equal(app.frame.style.height, `${height}px`);
    assert.ok(parseFloat(app.frame.style.width) <= width);
    assert.ok(parseFloat(app.frame.style.height) <= height);
    assert.equal(parseFloat(app.frame.style.width) / parseFloat(app.frame.style.height), width / height);
    app.hud.setZoom(2);
    app.area.clientWidth = width / 2; app.area.clientHeight = height / 2; app.resize();
    assert.equal(app.hud.zoom, 2);
    assert.ok(parseFloat(app.frame.style.width) <= width / 2);
    assert.ok(parseFloat(app.frame.style.height) <= height / 2);
  }
});

test('scrolling mobile panels refreshes pointer origin without resizing, zooming or changing outfits', () => {
  const app = createHud();
  app.scroll();
  assert.equal(app.boundsRefreshCount(), 1);
  assert.equal(app.refreshCount(), 1);
  assert.equal(app.hud.zoom, 1);
  assert.ok(source.includes('}, true);'), 'capture nested main scroll events');
  const phaser = fs.readFileSync(path.join(__dirname, '../src/frontend/forest-phaser.js'), 'utf8');
  assert.ok(phaser.includes('preventDefaultWheel: false'), 'canvas must not trap the wheel above below-screen panels');
});

test('touch panel shortcut scrolls only main and does not displace the topbar through fragment navigation', () => {
  const app = createHud();
  const event = app.elements['mobile-panel-shortcut'].click();
  assert.equal(event.defaultPrevented, true);
  assert.equal(app.elements['forest-main'].scrollTop, 734);
  assert.equal(app.elements['avatar-editor'].getBoundingClientRect().top, 66);
  app.elements['mobile-panel-shortcut'].click();
  assert.equal(app.elements['forest-main'].scrollTop, 734);
});

test('forest UI copies Suin final landing tokens and installed font stack without importing page styles', () => {
  const css = fs.readFileSync(path.join(__dirname, '../src/frontend/forest-game.css'), 'utf8');
  const suin = fs.readFileSync(path.join(__dirname, '../src/frontend/suin/styles.css'), 'utf8');
  const theme = css.slice(css.indexOf('/* Enlarged viewport and Suin'));
  assert.ok(theme.length > 100, 'a targeted theme block exists after legacy styles');
  const suinRoot = suin.match(/:root\{([^}]+)\}/)[1];
  const font = suinRoot.match(/font-family:([^;]+)/)[1];
  assert.ok(theme.includes(`font-family:${font}`));
  const landing = suin.match(/body\.intro-mode\{(--landing-paper:[^}]+)\}/)[1];
  for (const name of ['paper', 'surface', 'ink', 'muted', 'accent']) {
    const value = landing.match(new RegExp(`--landing-${name}:([^;]+)`))[1];
    assert.ok(theme.includes(`--landing-${name}:${value};`), `${name} matches the final Suin landing palette`);
  }
  assert.ok(theme.includes('--green:var(--landing-accent)'));
  assert.ok(theme.includes('--ink:var(--landing-ink)'));
  assert.ok(theme.includes('background:var(--bg);color:var(--ink)'));
  assert.doesNotMatch(css, /@import[^;]*suin/);
});

test('enlarged frame keeps balanced panel tracks and challenge title and refresh remain unbroken', () => {
  const css = fs.readFileSync(path.join(__dirname, '../src/frontend/forest-game.css'), 'utf8');
  assert.ok(css.includes('--forest-native-width:1536px'));
  assert.ok(css.includes('grid-template-columns:var(--hud-left) minmax(0,1fr) var(--hud-left)'));
  const workarea = [...css.matchAll(/\.canvas-workarea\{([^}]+)\}/g)].at(-1)[1];
  assert.ok(workarea.includes('min-width:0;min-height:0'));
  assert.ok(workarea.includes('overflow:hidden'));
  const heading = css.match(/\.right-hud \[data-challenge-v2\] \.v2-heading\{([^}]+)\}/)[1];
  assert.ok(heading.includes('flex-wrap:wrap'));
  assert.ok(heading.includes('min-width:0'));
  for (const selector of ['.v2-heading>h3', '.v2-heading>[data-refresh]']) {
    const start = css.indexOf(`.right-hud [data-challenge-v2] ${selector}{`);
    assert.ok(start > 0);
    assert.ok(css.slice(start, css.indexOf('}', start)).includes('white-space:nowrap'));
  }
  assert.ok(css.includes('.v2-heading>[data-refresh]{flex:0 0 auto'));
});

test('small screens fill independent dimensions while preserving camera magnification', () => {
  const app = createHud({ width: 400, height: 200 });
  assert.equal(app.frame.style.width, '400px'); assert.equal(app.frame.style.height, '200px');
  assert.equal(app.elements['zoom-level'].textContent, '100%');
  app.area.clientWidth = 600; app.area.clientHeight = 500; app.resize();
  assert.equal(app.frame.style.width, '600px'); assert.equal(app.frame.style.height, '500px');
  app.area.clientWidth = 0; app.resize();
  assert.equal(app.frame.style.width, '600px', 'temporarily hidden areas must not erase the viewport');
  app.area.clientWidth = 100; app.resize();
  assert.equal(app.frame.style.width, '100px');
  assert.equal(app.elements['zoom-in'].disabled, false); assert.equal(app.elements['zoom-out'].disabled, true);
});

test('camera zoom rebases the old 50–200% range to 100–400% without resizing the frame', () => {
  const app = createHud(), emittedZooms = [];
  app.window.addEventListener('forest-camera-zoom', event => {
    assert.equal(event.detail.zoom, app.hud.zoom, 'state is current when the scene receives the event');
    emittedZooms.push(event.detail.zoom);
  });
  for (let i = 0; i < 7; i++) app.click('zoom-in');
  assert.equal(app.hud.zoom, 4); assert.equal(app.elements['zoom-in'].disabled, true);
  assert.equal(app.elements['zoom-level'].textContent, '400%');
  for (let i = 0; i < 7; i++) app.click('zoom-out');
  assert.equal(app.hud.zoom, 1); assert.equal(app.elements['zoom-out'].disabled, true);
  assert.equal(app.elements['zoom-level'].textContent, '100%');
  assert.deepEqual(emittedZooms, [1.5, 2, 2.5, 3, 3.5, 4, 3.5, 3, 2.5, 2, 1.5, 1]);
  assert.equal(app.frame.style.width, '1800px'); assert.equal(app.frame.style.height, '1200px');
  assert.equal(app.refreshCount(), 1);
});

test('public zoom APIs clamp to supported steps, ignore invalid values, and reset to new 100%', () => {
  const app = createHud({ width: 100 });
  assert.equal(app.hud.setZoom(9), 4); assert.equal(app.hud.setZoom(1.6), 1.5);
  assert.equal(app.hud.setZoom(-1), 1); assert.equal(app.hud.setZoom(NaN), 1);
  assert.equal(app.hud.setZoom(Infinity), 1); assert.equal(app.hud.resetZoom(), 1);
  const count = app.events.length; app.hud.resetZoom();
  assert.equal(app.events.length, count, 'redundant resets must not dispatch duplicate camera events');
  assert.equal(app.frame.style.width, '100px'); assert.equal(app.elements['zoom-level'].textContent, '100%');
});

test('UI and panels restore preferences without resizing the frame or changing camera zoom', () => {
  const app = createHud({ width: 600 }); app.hud.setZoom(2);
  assert.equal(app.elements['controls-toggle'].textContent, '버튼 숨기기(8)');
  assert.equal(app.elements['reset-position'].textContent, '초기화(9)');
  assert.equal(app.elements['ui-toggle'].textContent, 'UI 숨기기(0)');
  app.click('controls-toggle');
  assert.equal(app.elements['controls-content'].hidden, true);
  assert.equal(app.elements['controls-toggle'].textContent, '버튼 보이기(8)');
  assert.equal(app.elements['controls-toggle'].getAttribute('aria-expanded'), 'false');
  assert.equal(app.events.at(-1).type, 'forest-controls-hidden');
  app.click('objects-toggle'); assert.equal(app.elements['placed-list'].hidden, true);
  assert.equal(app.elements['objects-toggle'].textContent, '오브젝트 보이기');
  app.click('ui-toggle'); app.resize();
  assert.equal(app.classes.has('forest-ui-hidden'), true);
  assert.equal(app.elements['ui-toggle'].textContent, 'UI 보이기(0)');
  assert.equal(app.elements['ui-toggle'].getAttribute('aria-pressed'), 'true');
  assert.equal(app.events.filter(event => event.type === 'forest-controls-hidden').length, 2);
  app.click('ui-toggle'); app.resize();
  assert.equal(app.classes.has('forest-ui-hidden'), false);
  assert.equal(app.elements['controls-content'].hidden, true, 'restoring UI preserves panel preference');
  app.click('controls-toggle'); app.click('objects-toggle');
  assert.equal(app.elements['controls-content'].hidden, false); assert.equal(app.elements['placed-list'].hidden, false);
  assert.equal(app.frame.style.width, '600px'); assert.equal(app.frame.style.height, '1200px');
  assert.equal(app.hud.zoom, 2); assert.equal(app.refreshCount(), 1);
});

test('8 and 0 toggle controls and UI; 9 delegates page refresh without mutating zoom before reload', () => {
  const app = createHud(); let reloads = 0;
  // The game owns location.reload(); HUD routes the key to exactly that same button.
  app.elements['reset-position'].addEventListener('click', () => { reloads += 1; });
  app.hud.setZoom(2); app.elements['ui-toggle'].focus();
  assert.equal(app.key('8').defaultPrevented, true); assert.equal(app.elements['controls-content'].hidden, true);
  assert.equal(app.events.filter(event => event.type === 'forest-controls-hidden').length, 1);
  assert.equal(app.key('9').defaultPrevented, true); assert.equal(reloads, 1); assert.equal(app.hud.zoom, 2);
  assert.equal(app.key('0').defaultPrevented, true); assert.equal(app.classes.has('forest-ui-hidden'), true);
  app.key('0'); assert.equal(app.classes.has('forest-ui-hidden'), false);
  app.key('8'); assert.equal(app.elements['controls-content'].hidden, false);
  app.hud.setZoom(1); app.click('reset-position'); assert.equal(reloads, 2); assert.equal(app.hud.zoom, 1);
  assert.equal(createHud().hud.zoom, 1, 'a fresh page still starts at the default camera magnification');
});

test('HTML exposes three font choices and places one translucent control pad in the lower-left game frame', () => {
  const html = fs.readFileSync(path.join(__dirname, '../src/frontend/forest.html'), 'utf8');
  const css = fs.readFileSync(path.join(__dirname, '../src/frontend/forest-game.css'), 'utf8');
  const select = html.match(/<select id="font-size-select"[^>]*>([\s\S]*?)<\/select>/)[1];
  assert.equal((select.match(/<option/g) || []).length, 3);
  for (const level of ['small', 'default', 'large']) {
    assert.ok(select.includes(`value="${level}"`));
    assert.ok(css.includes(`body[data-font-size="${level}"]{--forest-ui-scale:`));
  }
  assert.ok(html.includes('<label class="font-size-control" for="font-size-select">'));
  assert.ok(select.includes('value="default" selected'));
  assert.ok(!html.includes('id="large-text-toggle"'));
  assert.ok(css.includes('.v2-safety,.right-hud [data-challenge-v2] small'));
  assert.ok(css.includes('font-size:calc(11px * var(--forest-ui-scale));line-height:1.55'));
  const frame = html.indexOf('<div class="canvas-frame">');
  const overlay = html.indexOf('<div class="game-controls-overlay arcade-deck"');
  const right = html.indexOf('<div class="right-hud">');
  assert.ok(frame < overlay && overlay < right);
  assert.equal((html.match(/id="controls-content"/g) || []).length, 1);
  assert.ok(!html.slice(right).includes('id="controls-content"'));
  assert.ok(css.includes('background:rgba(245,244,239,.58)'));
  assert.ok(css.includes('.game-controls-overlay{position:absolute;z-index:24;left:10px;bottom:10px;'));
  assert.ok(css.includes('box-shadow:inset 0 1px rgba(255,255,255,.3);pointer-events:auto'));
  assert.ok(css.includes('text-align:center;white-space:normal;word-break:keep-all'));
  assert.ok(!css.includes('body.forest-ui-hidden .game-controls-overlay{display:none!important}'));
  assert.ok(css.includes('body.forest-ui-hidden .game-controls-overlay #ui-toggle{grid-column:3;'));
  assert.ok(css.includes('overflow:hidden;border-radius:16px;border:1px solid var(--line)'));
  assert.ok(css.includes('.right-hud .inspector-tabs{overflow:hidden;border-radius:15px 15px 0 0;'));
  assert.ok(html.indexOf('forest-animals.js') < html.indexOf('forest-phaser.js'));
  assert.ok(html.includes('id="avatar-nameplate" class="map-label avatar-nameplate"'));
  assert.ok(css.includes('.animal-thumbnail-canvas{display:block!important;width:78px!important;height:78px!important;'));
  assert.ok(!css.includes('carrot-forest-reward-cow-v2.png'));
});

test('shortcuts respect editors, forms, dialogs, IME, modifiers, repeats, and prevented events', () => {
  const app = createHud(); let resets = 0;
  app.elements['reset-position'].addEventListener('click', () => { resets += 1; });
  const contexts = ['INPUT', 'TEXTAREA', 'SELECT', 'FORM'].map(tag => app.createElement(tag));
  const editable = app.createElement('DIV'); editable.isContentEditable = true;
  contexts.push(editable, app.createElement('SPAN', editable), app.createElement('BUTTON', app.createElement('FORM')));
  const textbox = app.createElement('DIV'); textbox.role = 'textbox'; contexts.push(textbox);
  for (const target of contexts) {
    target.focus();
    for (const key of ['8', '9', '0']) assert.equal(app.key(key).defaultPrevented, false);
    assert.equal(app.key('0', { target: app.document.body }).defaultPrevented, false, 'active editor also blocks synthetic body events');
  }
  app.document.body.focus(); app.setModalOpen(true);
  for (const key of ['8', '9', '0']) assert.equal(app.key(key).defaultPrevented, false);
  app.setModalOpen(false);
  for (const key of ['8', '9', '0']) {
    for (const flag of ['repeat', 'isComposing', 'altKey', 'ctrlKey', 'metaKey', 'shiftKey']) assert.equal(app.key(key, { [flag]: true }).defaultPrevented, false);
    app.key(key, { defaultPrevented: true });
  }
  for (const key of ['Escape', 'Enter', ' ', 'c', 'C', '7']) assert.equal(app.key(key).defaultPrevented, false);
  assert.equal(app.elements['controls-content'].hidden, false);
  assert.equal(app.classes.has('forest-ui-hidden'), false); assert.equal(resets, 0);
});

test('8, 9 and 0 are one equal-size responsive row and hiding UI retains its restore button', () => {
  const html = fs.readFileSync(path.join(__dirname, '../src/frontend/forest.html'), 'utf8');
  const css = fs.readFileSync(path.join(__dirname, '../src/frontend/forest-game.css'), 'utf8');
  const heading = html.match(/<div class="hud-panel-heading"[^>]*>([\s\S]*?)<\/div>/)[1];
  assert.deepEqual([...heading.matchAll(/id="([^"]+)"/g)].map(match => match[1]), ['controls-toggle', 'reset-position', 'ui-toggle']);
  assert.equal((html.match(/id="ui-toggle"/g) || []).length, 1);
  const viewportTools = html.slice(html.indexOf('<div class="viewport-tools"'), html.indexOf('id="forest-time-toast"'));
  assert.ok(!viewportTools.includes('id="ui-toggle"'));
  assert.ok(css.includes('.game-controls-overlay .hud-panel-heading{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));width:100%;'));
  const buttonRule = css.match(/\.game-controls-overlay \.hud-panel-heading \.toolbar-button\{([^}]+)\}/)[1];
  assert.ok(buttonRule.includes('min-width:0;width:100%;height:36px;min-height:36px;'));
  assert.ok(buttonRule.includes('word-break:keep-all'));
  assert.ok(!css.includes('body.forest-ui-hidden .game-controls-overlay{display:none'));
  for (const id of ['controls-content', 'controls-toggle', 'reset-position']) {
    assert.ok(css.includes(`body.forest-ui-hidden .game-controls-overlay #${id}`));
  }
  assert.ok(css.includes('body.forest-ui-hidden .game-controls-overlay #ui-toggle{grid-column:3;'));
  const app = createHud();
  app.elements['controls-toggle'].focus();
  app.key('0');
  assert.equal(app.classes.has('forest-ui-hidden'), true);
  assert.equal(app.elements['ui-toggle'].disabled, false);
  assert.equal(app.elements['ui-toggle'].textContent, 'UI 보이기(0)');
  app.click('ui-toggle');
  assert.equal(app.classes.has('forest-ui-hidden'), false);
  assert.equal(app.elements['ui-toggle'].textContent, 'UI 숨기기(0)');
});

test('native attack returns to the same pad shape and label treatment as the other actions', () => {
  const html = fs.readFileSync(path.join(__dirname, '../src/frontend/forest.html'), 'utf8');
  const css = fs.readFileSync(path.join(__dirname, '../src/frontend/forest-game.css'), 'utf8');
  assert.ok(html.includes('data-action="attack" aria-label="공격, 단축키 Z"'));
  assert.match(html, /data-action="attack"[^>]*>공격<\/button>/);
  assert.match(html, /data-action="interact"[^>]*>상호작용<\/button>/);
  assert.doesNotMatch(html, /attack-spark/);
  assert.doesNotMatch(css, /\.game-controls-overlay \.touch-controls button\.action-attack/);
  assert.doesNotMatch(css, /ffe0a1|efae54|attack-spark/);
  assert.match(css, /\.action-attack\.is-monster-ready\{[^}]*background:#e9ad35/);
  assert.match(fs.readFileSync(path.join(__dirname, '../src/frontend/forest-game.js'), 'utf8'), /forest-monster-presence/);
});

test('monster presence highlights the relocated in-game attack button', () => {
  const css = fs.readFileSync(path.join(__dirname, '../src/frontend/forest-game.css'), 'utf8');
  const game = fs.readFileSync(path.join(__dirname, '../src/frontend/forest-game.js'), 'utf8');
  const phaser = fs.readFileSync(path.join(__dirname, '../src/frontend/forest-phaser.js'), 'utf8');
  assert.match(css, /\.touch-controls \.action-attack\.is-monster-ready\{[^}]*background:#e9ad35!important/);
  assert.doesNotMatch(css, /\.right-hud \.touch-controls \.action-attack\.is-monster-ready/);
  assert.match(game, /renderMonsterAttackState\(window\.ForestMonsterPresence === true\)/);
  assert.match(phaser, /window\.ForestMonsterPresence = true/);
});

test('daily reward is a large shared-panel action that reuses the existing chest ceremony without duplicate V2 carrots', () => {
  const html = fs.readFileSync(path.join(__dirname, '../src/frontend/forest.html'), 'utf8');
  const css = fs.readFileSync(path.join(__dirname, '../src/frontend/forest-game.css'), 'utf8');
  const game = fs.readFileSync(path.join(__dirname, '../src/frontend/forest-game.js'), 'utf8');
  const tabsAt = html.indexOf('class="inspector-tabs"');
  const rewardAt = html.indexOf('id="reward-button"');
  const questsAt = html.indexOf('id="quests-panel"');
  assert.ok(tabsAt < rewardAt && rewardAt < questsAt, 'the reward stays visible above both challenge panels');
  assert.equal((html.match(/id="reward-button"/g) || []).length, 1);
  assert.match(html, /id="reward-button"[^>]*daily-reward-button[^>]*>일일 보상 받기</);
  assert.match(css, /\.daily-reward-panel \.daily-reward-button\{[^}]*min-height:54px;[^}]*font-size:calc\(18px/);
  assert.match(game, /const ready = Boolean\(v2Plan\.chest_issued\)/);
  assert.match(game, /await playRewardCelebration\(null\)/);
  const v2Claim = game.slice(game.indexOf('if (v2Plan) {', game.indexOf('$("#reward-button")')), game.indexOf('if (groupCompleted()', game.indexOf('$("#reward-button")')));
  assert.doesNotMatch(v2Claim, /state\.carrots \+= 50/);
});

test('forest listens to personal water cup progress and styles cup controls in the right HUD', () => {
  const css = fs.readFileSync(path.join(__dirname, '../src/frontend/forest-game.css'), 'utf8');
  const game = fs.readFileSync(path.join(__dirname, '../src/frontend/forest-game.js'), 'utf8');
  const challenge = fs.readFileSync(path.join(__dirname, '../src/frontend/challenge-v2.js'), 'utf8');
  assert.match(challenge, /forest-water-cup-progress/);
  assert.match(game, /window\.addEventListener\("forest-water-cup-progress"/);
  assert.match(game, /playSfx\("water"/);
  assert.match(game, /pose: "harvest", duration: 900/);
  assert.match(game, /물컵 \$\{checked\}\/\$\{total\}개를 체크했어요/);
  assert.match(css, /\.right-hud \[data-challenge-v2\] \.v2-water-cups\{[^}]*grid-template-columns:repeat\(4,minmax\(0,1fr\)\)/);
  assert.match(css, /\.right-hud \[data-challenge-v2\] \.v2-water-cups \.v2-water-icon\{[^}]*width:19px;[^}]*height:19px/);
});

test('native Enter and Space activation do not double-toggle a focused button', () => {
  const app = createHud(); app.elements['ui-toggle'].focus();
  for (const key of ['Enter', ' ']) {
    assert.equal(app.key(key).defaultPrevented, false);
    app.document.activeElement.click(); // Browser default activation follows the unhandled key.
  }
  assert.equal(app.classes.has('forest-ui-hidden'), false);
  assert.equal(app.events.filter(event => event.type === 'forest-controls-hidden').length, 1);
  app.elements['ui-toggle'].disabled = true; assert.equal(app.key('0').defaultPrevented, false);
});

test('forest names stay bounded, normalized, and persisted without the removed name editor', () => {
  const app = createHud(); assert.equal(app.hud.forestName, '우리의 작은 숲');
  assert.equal(app.hud.setForestName('  함께\n  자라는 숲  '), true); assert.equal(app.hud.forestName, '함께 자라는 숲');
  assert.equal(app.storage.get('carrot-forest-name-v1'), '함께 자라는 숲');
  assert.equal(app.events.at(-1).type, 'forest-name-updated'); assert.equal(app.events.at(-1).detail.name, '함께 자라는 숲');
  assert.equal(createHud({ storedName: app.hud.forestName }).hud.forestName, '함께 자라는 숲');
  app.hud.setForestName('🌳'.repeat(30)); assert.equal(Array.from(app.hud.forestName).length, 24);
  assert.equal(app.hud.setForestName('\t \n'), false);
  const blocked = createHud({ storageBlocked: true });
  assert.equal(blocked.hud.setForestName('새 숲'), true); assert.equal(blocked.hud.forestName, '새 숲');
});

test('optional legacy name forms retain accessible save, cancellation, and Escape behavior', () => {
  const app = createHud({ storedName: '우리 팀 숲', nameEditor: true }); app.click('edit-forest-name');
  assert.equal(app.elements['forest-name-input'].value, '우리 팀 숲');
  assert.equal(app.document.activeElement, app.elements['forest-name-input']); assert.equal(app.elements['forest-name-input'].selected, true);
  app.elements['forest-name-input'].value = '\t \n'; app.submit();
  assert.equal(app.elements['forest-name-form'].hidden, false); assert.ok(app.elements['forest-name-input'].validationMessage);
  app.elements['forest-name-input'].value = '함께 자라는 숲'; app.submit();
  assert.equal(app.hud.forestName, '함께 자라는 숲'); assert.equal(app.elements['forest-name-form'].hidden, true);
  assert.equal(app.document.activeElement, app.elements['edit-forest-name']);
  app.click('edit-forest-name'); app.elements['forest-name-input'].value = '임시 이름'; app.click('cancel-forest-name');
  assert.equal(app.hud.forestName, '함께 자라는 숲'); assert.equal(app.elements['forest-name-form'].hidden, true);
  app.click('edit-forest-name'); const escape = app.elements['forest-name-form'].emit('keydown', { key: 'Escape' });
  assert.equal(escape.defaultPrevented, true); assert.equal(escape.propagationStopped, true);
  assert.equal(app.elements['forest-name-form'].hidden, true); assert.equal(app.hud.forestName, '함께 자라는 숲');
  app.click('edit-forest-name'); app.click('ui-toggle'); assert.equal(app.elements['forest-name-form'].hidden, true);
});
