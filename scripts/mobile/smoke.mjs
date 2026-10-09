import assert from 'node:assert/strict';
import { createReadStream } from 'node:fs';
import { mkdir, stat } from 'node:fs/promises';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const root = fileURLToPath(new URL('../../', import.meta.url));
const bundle = path.join(root, 'dist/mobile');
const output = path.join(root, 'outputs/mobile/smoke');
const types = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.webmanifest': 'application/manifest+json', '.svg': 'image/svg+xml', '.png': 'image/png', '.webp': 'image/webp', '.ico': 'image/x-icon', '.woff2': 'font/woff2', '.mp3': 'audio/mpeg', '.ogg': 'audio/ogg', '.wav': 'audio/wav' };
await stat(path.join(bundle, 'index.html'));
await mkdir(output, { recursive: true });
const server = http.createServer(async (request, response) => {
  const url = new URL(request.url, 'http://localhost');
  // This is a packaging test, never a connection to the production backend.
  if (url.pathname.startsWith('/api/')) {
    response.writeHead(503, { 'Content-Type': 'application/json' });
    response.end(JSON.stringify({ detail: 'Packaging test: backend not connected' }));
    return;
  }
  const target = path.resolve(bundle, '.' + decodeURIComponent(url.pathname === '/' ? '/index.html' : url.pathname));
  if (!target.startsWith(bundle + path.sep)) { response.writeHead(403).end(); return; }
  try {
    if (!(await stat(target)).isFile()) throw new Error('Not a file');
    response.writeHead(200, { 'Content-Type': types[path.extname(target)] || 'application/octet-stream' });
    createReadStream(target).pipe(response);
  } catch { response.writeHead(404).end(); }
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const base = `http://127.0.0.1:${server.address().port}`;
let browser;
try {
  browser = await chromium.launch({
    headless: true,
    ...(process.env.MOBILE_TEST_BROWSER ? { executablePath: process.env.MOBILE_TEST_BROWSER } : {}),
  });
  for (const [name, url, expected] of [
    ['intro', '/', '/static/intro-retro.html'],
    ['login', '/?auth=login', '/'],
    ['forest', '/static/forest.html?demo=1', '/static/forest.html'],
    ['profile', '/static/suin/index.html?auth=login', '/static/suin/index.html'],
  ]) {
    const context = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1, isMobile: true, hasTouch: true });
    await context.route('**/*', async route => {
      if (!route.request().url().startsWith(base)) return route.abort();
      return route.continue();
    });
    const page = await context.newPage();
    const missing = [], errors = [];
    page.on('response', response => { if (response.status() === 404) missing.push(response.url()); });
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(base + url, { waitUntil: 'load' });
    await page.waitForTimeout(1000);
    assert.equal(new URL(page.url()).pathname, expected, `${name}: wrong local route`);
    assert.equal(await page.locator('body').isVisible(), true);
    await page.screenshot({ path: path.join(output, `${name}.png`) });
    if (name === 'intro') {
      await page.locator('#sidebar-login').click();
      await page.waitForURL(url => url.pathname === '/' && url.searchParams.get('auth') === 'login');
      await page.locator('#login-form').waitFor({ state: 'visible' });
      assert.equal(await page.locator('#login-email').isVisible(), true);
    }
    assert.deepEqual(missing, [], `${name}: missing bundled files`);
    assert.deepEqual(errors, [], `${name}: JavaScript errors`);
    assert.equal(await page.evaluate(async () => 'serviceWorker' in navigator ? (await navigator.serviceWorker.getRegistrations()).length : 0), 0);
    console.log(`PASS ${name}: local page, assets, scripts, no web service worker`);
    await context.close();
  }

  // Exercise the native JavaScript path with a fake bridge; no production requests.
  const native = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const requests = [];
  await native.route('**/*', async route => {
    const url = route.request().url();
    if (url.startsWith('https://www.dang-no.life/api/')) {
      requests.push({ url, method: route.request().method() });
      return route.fulfill({ status: 503, contentType: 'application/json', body: '{"detail":"Offline test"}' });
    }
    if (!url.startsWith(base)) return route.abort();
    return route.continue();
  });
  await native.addInitScript(() => {
    window.androidBridge = {};
    window.testListeners = {};
    window.testCameraCalls = 0;
    window.testMinimized = false;
    window.Capacitor = {
      PluginHeaders: [
        { name: 'App', methods: [{ name: 'addListener', rtype: 'callback' }, { name: 'minimizeApp', rtype: 'promise' }] },
        { name: 'Camera', methods: [{ name: 'getPhoto', rtype: 'promise' }] },
      ],
      nativeCallback(plugin, method, options, callback) { window.testListeners[options.eventName] = callback; return 'test-listener'; },
      async nativePromise(plugin, method) {
        if (method === 'minimizeApp') { window.testMinimized = true; return {}; }
        if (method === 'getPhoto') {
          window.testCameraCalls++;
          if (window.testCancelCamera) throw new Error('User cancelled photos app');
          const canvas = document.createElement('canvas'); canvas.width = 20; canvas.height = 20;
          canvas.getContext('2d').fillRect(0, 0, 20, 20);
          return { webPath: canvas.toDataURL('image/png') };
        }
        throw new Error('Unexpected plugin call');
      },
    };
  });
  const page = await native.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(base + '/?auth=login', { waitUntil: 'load' });
  assert.equal(await page.evaluate(() => document.documentElement.classList.contains('gandang-native')), true);
  assert.equal(await page.evaluate(() => isDemoEnvironment()), false);
  await page.evaluate(() => document.querySelector('#v3-photo-file').click());
  await page.waitForFunction(() => document.querySelector('#v3-photo-file').files.length === 1);
  await page.waitForFunction(() => !document.querySelector('#v3-photo-preview').hidden);
  assert.equal(await page.evaluate(() => document.querySelector('#v3-photo-file').files[0].type), 'image/png');
  assert.equal(requests.some(request => request.url.includes('photo-verifications')), false, 'choosing a photo must not upload it');
  await page.evaluate(() => { window.testCancelCamera = true; document.querySelector('#v3-photo-file').click(); });
  await page.waitForFunction(() => window.testCameraCalls === 2);
  assert.equal(await page.evaluate(() => document.querySelector('#v3-photo-file').files.length), 1);
  await page.evaluate(() => {
    const dialog = document.createElement('dialog'); dialog.id = 'back-test'; document.body.append(dialog); dialog.showModal();
    window.testListeners.backButton({ canGoBack: false });
  });
  assert.equal(await page.locator('#back-test').evaluate(node => node.open), false);
  await page.evaluate(() => window.testListeners.backButton({ canGoBack: false }));
  await page.waitForFunction(() => window.testMinimized);
  const response = await page.evaluate(async () => (await fetch('/api/v1/predictions/today')).status);
  assert.equal(response, 503, 'model failures must remain failures');
  assert.ok(requests.some(request => request.url === 'https://www.dang-no.life/api/v1/predictions/today'));
  assert.deepEqual(errors, []);
  await page.screenshot({ path: path.join(output, 'native-login.png') });
  await native.close();
  console.log('PASS native bridge mock: server routing, photo preview/cancel, no implicit upload, dialog/back, explicit model failure');

} finally {
  await browser?.close();
  await new Promise(resolve => server.close(resolve));
}
