const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const css = fs.readFileSync(path.join(__dirname, '../src/frontend/forest-game.css'), 'utf8');
const responsive = css.slice(css.indexOf('/* v157:'));
const declaration = selector => {
  const start = responsive.indexOf(`\n${selector}{`) + 1;
  assert.ok(start > 0, `missing viewport contract: ${selector}`);
  return responsive.slice(start + selector.length + 1, responsive.indexOf('}', start));
};

test('responsive shell allocates real toolbar height and keeps chat outside the game viewport', () => {
  assert.ok(responsive.startsWith('/* v157:'));
  assert.match(declaration('body'), /display:flex;flex-direction:column;height:100dvh/);
  assert.match(declaration('.studio-topbar'), /flex:0 0 auto;height:auto/);
  const shell = declaration('.studio-shell');
  assert.match(shell, /flex:1 1 0;min-width:0;min-height:0/);
  assert.match(shell, /height:auto/);
  assert.match(shell, /padding-bottom:calc\(60px \+ env\(safe-area-inset-bottom,0px\)\)/);
  assert.doesNotMatch(responsive.slice(0, responsive.indexOf('/* v175:')), /100dvh\s*-\s*\d+px|74vw|650px|1536px/);
  assert.match(declaration('.workspace,body.forest-ui-hidden .workspace'), /grid-template-columns:var\(--hud-left\) minmax\(0,1fr\) var\(--hud-left\)/);
});

test('canvas frame fills both measured axes without a native-width or fixed-aspect constraint', () => {
  const area = declaration('.canvas-workarea');
  assert.match(area, /flex:1 1 0;min-width:0;min-height:0/);
  assert.match(area, /align-items:stretch;justify-content:stretch/);
  const frame = declaration('.canvas-frame,.canvas-frame.is-zoomed');
  assert.match(frame, /width:100%;height:100%/);
  assert.match(frame, /max-width:none;max-height:none;aspect-ratio:auto/);
  assert.match(frame, /box-sizing:border-box;border:0;padding:0/);
  assert.match(declaration('#phaser-world canvas'), /width:100%!important;height:100%!important/);
  assert.match(declaration('#phaser-world canvas'), /aspect-ratio:auto/);
  assert.match(declaration('#forest-canvas'), /object-fit:cover/);
  assert.doesNotMatch(responsive, /aspect-ratio:3\/2|forest-native-width/);
});

test('fullscreen wins over legacy atmosphere fitting and keeps the restore-control ancestor unconstrained', () => {
  const stage = '#world-stage.world-stage:is(:fullscreen,.game-fullscreen)';
  assert.match(declaration(`${stage} .canvas-workarea`), /padding:0;align-items:stretch/);
  assert.match(declaration(`${stage} .canvas-frame`), /max-width:none;max-height:none;aspect-ratio:auto;border:0;padding:0/);
  assert.match(declaration(`${stage} .game-controls-overlay .control-cluster`), /width:100%;height:auto;min-height:0/);
  assert.doesNotMatch(responsive, /game-controls-overlay[^}]*display:none/);
});

test('mobile fills the first screen and leaves existing HUD panels reachable below it', () => {
  const tablet = responsive.slice(responsive.indexOf('@media(max-width:900px)'));
  const mobile = responsive.slice(responsive.indexOf('@media(max-width:520px)'));
  assert.match(tablet, /\.studio-shell\{overflow-x:hidden;overflow-y:auto/);
  assert.match(tablet, /display:flex;flex-wrap:wrap;align-content:flex-start;align-items:flex-start;height:100%/);
  assert.match(tablet, /order:0;flex:0 0 100%;width:100%;height:100%;min-height:0;max-height:none/);
  assert.match(tablet, /flex:0 0 calc\(\(100% - 9px\)\/2\)/);
  assert.match(mobile, /\.workspace>\.tool-rail,\.workspace>\.right-hud\{flex-basis:100%\}/);
  assert.doesNotMatch(tablet, /\.world-stage[^}]*height:(?:min\(|\d+(?:px|vw))/);
});

test('touch users have a native below-game panel shortcut without changing canvas gestures', () => {
  const html = fs.readFileSync(path.join(__dirname, '../src/frontend/forest.html'), 'utf8');
  assert.match(html, /class="mobile-panel-shortcut" href="#avatar-editor">옷장·창고 ↓<\/a>/);
  assert.match(declaration('.mobile-panel-shortcut'), /display:none;position:fixed/);
  assert.match(declaration('body.forest-ui-hidden .mobile-panel-shortcut'), /display:none/);
  assert.match(responsive.slice(responsive.indexOf('@media(max-width:900px)')), /\.mobile-panel-shortcut\{display:inline-flex\}/);
});
