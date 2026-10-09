import assert from 'node:assert/strict';
import { chromium } from 'playwright';
import { mkdir } from 'node:fs/promises';
const browser = await chromium.launch({ headless: true,
  executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe' });
try {
  await mkdir('outputs/mobile/forest', { recursive: true });
  for (const width of [390, 720]) {
    const page = await browser.newPage({ viewport: { width, height: 1000 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/api/**', route => route.fulfill({ status: 503,
      contentType: 'application/json', body: '{"detail":"isolated UI test"}' }));
    await page.route('**/static/forest.html?demo=1', async route => {
      const response = await route.fetch();
      await route.fulfill({ response, body: (await response.text()).replace('<html lang="ko">', '<html lang="ko" class="gandang-native">') });
    });
    await page.goto('http://127.0.0.1:8000/static/forest.html?demo=1');
    assert.equal(await page.locator('#forest-canvas').evaluate(el => getComputedStyle(el).objectFit), 'cover', 'First-entry fallback fills the screen');
    const home = page.locator('.forest-service-home');
    assert.equal(await home.getAttribute('href'), '/static/intro-retro.html');
    const settingsBox = await page.locator('.forest-game-settings').boundingBox();
    const homeBox = await home.boundingBox();
    assert.ok(homeBox.x >= settingsBox.x + settingsBox.width, 'Service home is right of settings');
    assert.ok(homeBox.x + homeBox.width <= width, 'Service home fits the viewport');
    const forestUrl = page.url();
    await page.locator('#open-profile').click();
    await page.waitForTimeout(200);
    assert.equal(page.url(), forestUrl, 'Clicking user name keeps the forest page');
    assert.equal(await page.locator('#open-profile').getAttribute('aria-label'), '사용자 이름');
    await page.waitForFunction(() => window.carrotForestPhaserGame?.scene.scenes[0]?.premiumAvatar, { timeout: 60000 });
    const initialCamera = await page.evaluate(() => {
      const camera = carrotForestPhaserGame.scene.scenes[0].cameras.main;
      return { width: camera.width, height: camera.height, zoom: camera.zoom };
    });
    assert.ok(768 * initialCamera.zoom >= initialCamera.width && 512 * initialCamera.zoom >= initialCamera.height, 'Initial Phaser camera covers both axes before zoom input');
    await page.waitForFunction(() => {
      const texture = carrotForestPhaserGame.scene.scenes[0].compositeTexture;
      return texture?.getContext().getImageData(0,0,224,288).data.some((value,index)=> index%4===3 && value>0);
    }, { timeout: 60000 });
    await page.keyboard.down('ArrowRight');
    await page.waitForTimeout(500);
    await page.keyboard.up('ArrowRight');
    const pad = await page.locator('#forest-joystick').boundingBox();
    assert.ok(pad && pad.width >= 100);
    await page.mouse.move(pad.x + pad.width / 2, pad.y + pad.height / 2);
    await page.mouse.down();
    await page.mouse.move(pad.x + pad.width / 2 + 50, pad.y + pad.height / 2 - 25);
    const analog = await page.evaluate(() => window.ForestJoystickInput);
    assert.ok(analog.x > 0 && analog.y < 0, 'Diagonal analog movement');
    assert.ok(Math.abs(Math.hypot(analog.x, analog.y) - 1) < 0.000001, 'Fixed speed direction');
    await page.mouse.move(pad.x + pad.width / 2 + 12, pad.y + pad.height / 2);
    const smallTilt = await page.evaluate(() => window.ForestJoystickInput);
    assert.ok(Math.abs(Math.hypot(smallTilt.x, smallTilt.y) - 1) < 0.000001, 'Small tilt keeps the same speed');
    await page.mouse.up();
    const run = page.locator('.joystick-actions [data-action="run"]');
    const runningBefore = await page.evaluate(() => window.carrotForestRunning === true);
    await run.click();
    assert.equal(await page.evaluate(() => window.carrotForestRunning === true), !runningBefore);
    assert.equal(await run.getAttribute('aria-pressed'), String(!runningBefore));
    await run.click();
    assert.equal(await page.evaluate(() => window.carrotForestRunning === true), runningBefore);
    const controls = await page.evaluate(() => {
      const buttons = [...document.querySelectorAll('.joystick-actions button')].map(el => el.getBoundingClientRect());
      const knob = document.querySelector('.joystick-knob').getBoundingClientRect();
      return knob.width > 0 && new Set(buttons.map(r => `${r.x},${r.y}`)).size === 5;
    });
    assert.ok(controls, 'Visible joystick thumb and five separate action buttons');
    await page.locator('.forest-game-settings summary').click();
    assert.equal(await page.evaluate(() => carrotForestPhaserGame.scene.scenes[0].isWorldInputBlocked()), true);
    await page.locator('#music-toggle').click();
    await page.waitForFunction(() => document.querySelector('#music-toggle').getAttribute('aria-pressed') === 'true');
    await page.locator('#music-toggle').click();
    assert.equal(await page.locator('#music-toggle').getAttribute('aria-pressed'), 'false');
    await page.locator('#volume-toggle').click();
    assert.equal(await page.locator('#volume-toggle').getAttribute('aria-expanded'), 'true');
    await page.locator('#music-volume').evaluate(el => { el.value = '40'; el.dispatchEvent(new Event('input', { bubbles: true })); });
    assert.equal(Number.parseFloat(await page.locator('#music-volume-value').inputValue()), 40);
    await page.locator('#sfx-volume').evaluate(el => { el.value = '60'; el.dispatchEvent(new Event('input', { bubbles: true })); });
    assert.equal(Number.parseFloat(await page.locator('#sfx-volume-value').inputValue()), 60);
    for (const id of ['music-mute', 'sfx-mute', 'atmosphere-toggle']) {
      const button = page.locator(`#${id}`);
      const before = await button.getAttribute('aria-pressed');
      await button.click();
      assert.notEqual(await button.getAttribute('aria-pressed'), before);
      await button.click();
    }
    await page.locator('#font-size-select').selectOption('large');
    assert.equal(await page.locator('body').getAttribute('data-font-size'), 'large');
    await page.locator('#font-size-select').selectOption('default');
    await page.locator('.forest-game-settings summary').click();
    for (const [tab, dialog, close] of [['0','#avatar-studio','#avatar-studio-close'], ['1','#inventory-dialog','#inventory-dialog-close'], ['2','#forest-hud-drawer','.forest-drawer-close'], ['3','#forest-hud-drawer','.forest-drawer-close']]) {
      await page.locator(`[data-hud-tab="${tab}"]`).click();
      assert.equal(await page.locator(dialog).evaluate(el => el.open), true);
      if (tab === '0') {
        const savedBefore = await page.evaluate(() => localStorage.getItem('gandang-carrot-forest-demo-v1'));
        await page.evaluate(() => {
          const original = LpcAvatarEngine.draw;
          LpcAvatarEngine.draw = function(context, avatar, ...args) {
            if (context.canvas.id === 'avatar-preview-canvas') window.testPreviewCosmetics = { ...avatar.cosmetics };
            return original.call(this, context, avatar, ...args);
          };
        });
        await page.locator('#avatar-randomize').click();
        assert.equal(await page.evaluate(() => window.testPreviewCosmetics.lpcEyes), 'none');
        await page.locator('#avatar-reset-face').click();
        const face = await page.evaluate(() => window.testPreviewCosmetics);
        assert.equal(face.lpcExpression, 'neutral');
        assert.equal(face.lpcEyes, 'none');
        assert.equal(face.lpcWrinkles, 'none');
        await page.locator('#avatar-restore-outfit').click();
        const restored = await page.evaluate(() => window.testPreviewCosmetics);
        for (const [key, value] of Object.entries(JSON.parse(savedBefore).avatar.cosmetics)) {
          assert.equal(restored[key], value, `Restores worn outfit: ${key}`);
        }
        await page.locator('#avatar-open-presets').click();
        assert.equal(await page.locator('#avatar-studio').evaluate(el => el.open), false);
        assert.equal(await page.locator('#inventory-dialog').evaluate(el => el.open), true);
        assert.ok(await page.locator('#inventory-dialog-grid [data-outfit-look]').count() >= 6);
        assert.equal(await page.evaluate(() => localStorage.getItem('gandang-carrot-forest-demo-v1')), savedBefore, 'Opening presets and editing face preserves saved data');
        await page.locator('#inventory-dialog-close').click();
        await page.locator('[data-hud-tab="0"]').click();
      }
      if (tab === '2' || tab === '3') assert.equal(await page.locator(tab === '2' ? '#quests-panel' : '#team-inspector').evaluate(el => el.hidden), false);
      await page.locator(close).click();
    }
    await page.locator('[data-hud-tab="4"]').click();
    assert.equal(await page.locator('#chat-panel').evaluate(el => el.hidden), false);
    await page.locator('#chat-close').click();
    const full = await page.locator('.canvas-frame').evaluate(el => ({ width: el.clientWidth, height: el.clientHeight, viewportWidth: innerWidth, viewportHeight: innerHeight }));
    assert.equal(full.width, full.viewportWidth);
    assert.equal(full.height, full.viewportHeight);
    assert.deepEqual(await page.evaluate(() => window.ForestJoystickInput), { x: 0, y: 0 });
    await page.mouse.down();
    await page.evaluate(() => window.dispatchEvent(new Event('blur')));
    assert.deepEqual(await page.evaluate(() => window.ForestJoystickInput), { x: 0, y: 0 });
    await page.mouse.up();
    const result = await page.evaluate(() => ({
      renderer: carrotForestPhaserGame.renderer.type,
      overflow: document.documentElement.scrollWidth > innerWidth,
      canvas: [carrotForestPhaserGame.canvas.width, carrotForestPhaserGame.canvas.height],
      toolbarFits: [...document.querySelector('.topbar-actions').children].every(el => {
        const rect = el.getBoundingClientRect();
        return !rect.width || (rect.left >= 0 && rect.right <= innerWidth);
      }),
    }));
    assert.equal(result.renderer, 1, 'Native forest uses Canvas');
    assert.equal(result.overflow, false, `${width}px horizontal overflow`);
    assert.ok(result.toolbarFits, `${width}px visible toolbar controls`);
    assert.deepEqual(errors, []);
    await page.screenshot({ path: `outputs/mobile/forest/canvas-${width}.png` });
    console.log(`PASS ${width}px: Canvas map/avatar/movement, no JS errors or horizontal overflow`);
    await page.close();
  }
} finally { await browser.close(); }
