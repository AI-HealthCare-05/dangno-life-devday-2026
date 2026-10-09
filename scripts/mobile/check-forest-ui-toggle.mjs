import assert from 'node:assert/strict';
import { chromium } from 'playwright';
import { mkdir } from 'node:fs/promises';
const origin = process.env.FOREST_TEST_ORIGIN || 'http://127.0.0.1:8000';
const browser = await chromium.launch({ headless: true, executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe' });
function fullViewport(box, width, height, label) {
  for (const [key, expected] of Object.entries({x:0,y:0,width,height})) {
    assert.ok(Math.abs(box[key] - expected) <= 1, `${label}.${key}: expected ${expected}, got ${box[key]}`);
  }
}
try {
  await mkdir('outputs/mobile/forest', {recursive:true});
  for (const {width,height,native} of [{width:390,height:844,native:true}, {width:720,height:1256,native:true}, {width:1280,height:800,native:false}]) {
    const page = await browser.newPage({viewport:{width,height}});
    const errors=[];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/api/**', route => route.fulfill({status:503,contentType:'application/json',body:'{}'}));
    if (native) await page.route('**/static/forest.html?demo=1', async route => {
      const response=await route.fetch();
      await route.fulfill({response,body:(await response.text()).replace('<html lang="ko">','<html lang="ko" class="gandang-native">')});
    });
    await page.goto(`${origin}/static/forest.html?demo=1`);
    await page.waitForFunction(() => window.carrotForestPhaserGame?.scene.scenes[0]?.premiumAvatar, {timeout:60000});
    for (const hidden of [true,false,true,false]) {
      await page.locator('#ui-toggle').click();
      assert.equal(await page.locator('body').evaluate(el=>el.classList.contains('forest-ui-hidden')),hidden);
      await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
      const bounds=await page.evaluate(()=>{
        const rect=element=>{const {x,y,width,height}=element.getBoundingClientRect();return {x,y,width,height};};
        return {
          frame:rect(document.querySelector('.canvas-frame')),
          stage:rect(document.querySelector('.world-stage')),
          canvas:rect(carrotForestPhaserGame.canvas),
          railDisplay:getComputedStyle(document.querySelector('.workspace > .tool-rail')).display,
          overflow:document.documentElement.scrollWidth>innerWidth||document.documentElement.scrollHeight>innerHeight,
        };
      });
      await page.screenshot({path:`outputs/mobile/forest/ui-${hidden?'hidden':'restored'}-${width}.png`});
      for (const name of ['frame','stage','canvas']) fullViewport(bounds[name],width,height,name);
      assert.equal(bounds.railDisplay,'none','Legacy tool rail stays out of the full-screen layout');
      assert.equal(bounds.overflow,false,'UI toggle does not overflow the viewport');
      assert.equal(await page.locator('#ui-toggle').isVisible(),true,'Restore control remains reachable');
      assert.equal(await page.locator('#ui-toggle').getAttribute('aria-pressed'),String(hidden));
      assert.equal(await page.locator('.forest-game-tabs').isVisible(),!hidden);
      assert.equal(await page.locator('#forest-joystick').isVisible(),!hidden);
      assert.deepEqual(await page.evaluate(()=>window.ForestJoystickInput),{x:0,y:0});
    }
    await page.keyboard.press('0');
    fullViewport(await page.locator('.canvas-frame').boundingBox(),width,height,'Keyboard hide');
    await page.keyboard.press('0');
    fullViewport(await page.locator('.canvas-frame').boundingBox(),width,height,'Keyboard restore');
    assert.deepEqual(errors,[]);
    console.log(`PASS ${width}x${height}: repeated hide/restore and keyboard toggle keep the map full-screen, controls recover`);
    await page.close();
  }
} finally {await browser.close();}
