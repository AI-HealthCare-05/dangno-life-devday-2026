// Real CSS/DOM regression: synthetic account-free page, no game saves or APIs.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');
const root = path.join(__dirname, '../src/frontend');
const html = fs.readFileSync(path.join(root, 'forest.html'), 'utf8').replace(/<script\b[^>]*>[\s\S]*?<\/script>/g, '');
const hud = fs.readFileSync(path.join(root, 'forest-ingame-hud.js'), 'utf8');
const game = fs.readFileSync(path.join(root, 'forest-game.js'), 'utf8');
const start = game.indexOf('  function renderPlacementUI() {');
const ui = game.slice(start, game.indexOf('  function cancelPlacement(', start));

test('placement controls stay on screen, retain listeners, and disappear on cancel', async () => {
  const browser = await chromium.launch({ headless: true, ...(process.env.CHROME_BIN ? { executablePath: process.env.CHROME_BIN } : {}) });
  try {
    const page = await browser.newPage();
    await page.route('**/*', route => {
      const url = new URL(route.request().url());
      const file = path.resolve(root, url.pathname.replace(/^\/static\//, ''));
      if (url.hostname !== 'forest-qa.test' || !file.startsWith(root + path.sep) || !file.endsWith('.css') || !fs.existsSync(file)) return route.abort();
      return route.fulfill({ path: file });
    });
    for (const [width, height] of [[320, 640], [360, 740], [411, 808], [808, 411], [1440, 900]]) {
      await page.setViewportSize({ width, height });
      await page.setContent(html.replace('<head>', '<head><base href="http://forest-qa.test/">'));
      await page.evaluate(() => {
        document.documentElement.classList.add('forest-style-ready', 'forest-script-ready');
        window.placementClicks = 0;
        document.getElementById('confirm-placement').addEventListener('click', () => window.placementClicks++);
      });
      await page.evaluate(hud);
      await page.evaluate('(() => {\n' + ui + `
        window.setPlacement = (active, positioned) => {
          placementCode = active ? 'bench' : null; placementDraft = positioned ? {} : null;
          renderPlacementUI();
        };
        var placementCode = null, placementDraft = null;
        const $ = selector => document.querySelector(selector);
        const itemCatalog = { bench: { name: '벤치' } };
        $('#cancel-placement').addEventListener('click', () => window.setPlacement(false, false));
        window.setPlacement(false, false);
      })()`);
      assert.equal(await page.locator('#placement-controls').isVisible(), false);
      await page.evaluate(() => window.setPlacement(true, false));
      assert.equal(await page.locator('#placement-controls').isVisible(), true);
      assert.equal(await page.locator('#confirm-placement').isDisabled(), true);
      assert.equal(await page.locator('#controls-content').isVisible(), false, 'movement pad cannot cover placement actions');
      await page.evaluate(() => window.setPlacement(true, true));
      const boxes = await page.evaluate(() => ['#rotate-placement', '#confirm-placement', '#cancel-placement', '.forest-game-tabs'].map(selector => {
        const node = document.querySelector(selector), r = node.getBoundingClientRect();
        return { selector, x: r.x, y: r.y, right: r.right, bottom: r.bottom, width: r.width, height: r.height };
      }));
      for (const r of boxes) assert.ok(r.width > 0 && r.height >= 42 && r.x >= 0 && r.y >= 0 && r.right <= width && r.bottom <= height, `${width}×${height}: ${JSON.stringify(r)}`);
      assert.ok(boxes[1].bottom < boxes[3].y, 'confirm stays above bottom tabs');
      await page.locator('#confirm-placement').click();
      assert.equal(await page.evaluate(() => window.placementClicks), 1, 'original button listener survived relocation');
      await page.locator('#cancel-placement').click();
      assert.equal(await page.locator('#placement-controls').isVisible(), false);
      assert.equal(await page.locator('#confirm-placement').isDisabled(), true);
      assert.equal(await page.locator('#controls-content').isVisible(), true, 'movement pad returns after cancel');
    }
  } finally { await browser.close(); }
});
