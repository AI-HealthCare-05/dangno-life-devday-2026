// Full browser smoke with a synthetic API; never connects to real accounts.
import assert from 'node:assert/strict';
import { createReadStream } from 'node:fs';
import { mkdir, stat, writeFile } from 'node:fs/promises';
import http from 'node:http';
import path from 'node:path';
import { chromium } from 'playwright';

const root = process.cwd(), source = path.join(root, 'src/frontend');
const output = path.join(root, 'outputs/mobile/account-wallet');
await mkdir(output, { recursive: true });
let balance = 100, revision = 1, failNext = true;
const rewards = [], daily = {}, calls = [], errors = [];
const items = ['diet', 'activity', 'routine'].map((domain, index) => ({
  id: index + 1, slot: index + 1, status: 'assigned', verification_status: 'not_required',
  sessions: [], evidence: [], completed_sessions: 0, total_quantity: 0, intake_ml: 0,
  goal: { title: `${domain} 테스트`, code: `test-${domain}`, family_id: 'TEST', domain,
    difficulty: 'E', proof_type: 'T3', target_sessions: 1, required_uploads: 0,
    goal_unit: 'record', per_session_quantity: 1, sources: [], safety: '테스트용' },
}));
const wallet = () => ({ user_id: 7, carrot_balance: balance, wallet_revision: revision,
  wallet_updated_at: new Date(1700000000000 + revision).toISOString(), date: '2026-10-09', daily_actions: daily });
const plan = () => ({ ...wallet(), enrolled: true, day_id: 8, items, rewards, preferences: {},
  chest_issued: rewards.some(row => row.carrot_amount === 50), completed: items.filter(row => row.status === 'completed').length });
const types = { '.js': 'text/javascript', '.css': 'text/css', '.html': 'text/html', '.json': 'application/json',
  '.png': 'image/png', '.webp': 'image/webp', '.mp3': 'audio/mpeg', '.wav': 'audio/wav', '.ogg': 'audio/ogg', '.svg': 'image/svg+xml' };
const server = http.createServer(async (request, response) => {
  const url = new URL(request.url, 'http://localhost');
  const json = (value, status = 200) => { response.writeHead(status, { 'Content-Type': 'application/json' }); response.end(JSON.stringify(value)); };
  if (url.pathname.startsWith('/api/')) {
    calls.push(url.pathname);
    if (url.pathname.endsWith('/auth/token/refresh')) return json({ access_token: 'synthetic-session' });
    if (url.pathname.endsWith('/users/me')) return json({ data: { id: 7, name: '검증 계정' } });
    if (url.pathname.endsWith('/wallet')) return json({ data: wallet() });
    if (url.pathname.endsWith('/capabilities')) return json({ data: { enabled: true } });
    if (url.pathname.endsWith('/today')) return json({ data: plan() });
    const match = url.pathname.match(/assignments\/(\d+)\/sessions\/(\d+)/);
    if (match) {
      if (failNext) { failNext = false; return json({ detail: '의도한 테스트 저장 실패' }, 500); }
      const item = items.find(row => row.id === Number(match[1]));
      if (item.status !== 'completed') {
        item.status = 'completed'; item.completed_sessions = 1; item.sessions = [{ index: 1 }];
        balance += 10; revision++; rewards.push({ source_key: `v2-slot:8:${item.slot}`, carrot_amount: 10 });
        if (items.every(row => row.status === 'completed')) { balance += 50; revision++; rewards.push({ source_key: 'v2-day:7:2026-10-09', carrot_amount: 50 }); }
      }
      return json({ data: plan() });
    }
    return json({ data: {} });
  }
  const target = path.resolve(source, '.' + url.pathname.replace(/^\/static/, ''));
  if (!target.startsWith(source + path.sep)) { response.writeHead(403).end(); return; }
  try {
    if (!(await stat(target)).isFile()) throw new Error('not a file');
    response.writeHead(200, { 'Content-Type': types[path.extname(target)] || 'application/octet-stream' });
    createReadStream(target).pipe(response);
  } catch { response.writeHead(404).end(); }
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const base = `http://127.0.0.1:${server.address().port}`;
let browser;
try {
  browser = await chromium.launch({ headless: true, ...(process.env.MOBILE_TEST_BROWSER ? { executablePath: process.env.MOBILE_TEST_BROWSER } : {}) });
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, serviceWorkers: 'block' });
  await context.route('**/*', route => route.request().url().startsWith(base) ? route.continue() : route.abort());
  const page = await context.newPage();
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(base + '/static/forest.html', { waitUntil: 'load' });
  await page.waitForFunction(() => document.documentElement.classList.contains('forest-script-ready'), undefined, { timeout: 60000 });
  await page.waitForFunction(() => document.querySelector('[data-certify="1"]'));
  assert.equal(await page.locator('#carrot-balance').textContent(), '100');
  await page.evaluate(() => document.querySelector('[data-certify="1"]').click());
  await page.waitForFunction(() => document.querySelector('[data-message]')?.textContent.includes('완료하지 못했습니다'));
  assert.equal(await page.locator('#carrot-balance').textContent(), '100');
  assert.equal(await page.locator('#challenge-celebration').count(), 0);
  for (const [id, expected, message] of [[1, 110, '당근밭에 비료를 주었습니다'], [2, 120, '당근밭의 잡초를 뽑았습니다'], [3, 180, '당근 50개를 추가로']]) {
    await page.evaluate(id => document.querySelector(`[data-certify="${id}"]`).click(), id);
    await page.waitForFunction(value => document.querySelector('#carrot-balance')?.textContent === String(value), expected);
    assert.match(await page.locator('#challenge-celebration').textContent(), new RegExp(message));
    const dialog = await page.locator('.v2-celebration-card').boundingBox();
    assert.ok(dialog.x >= 0 && dialog.x + dialog.width <= 391);
    assert.ok(dialog.y >= 0 && dialog.y + dialog.height <= 845);
    await page.screenshot({ path: path.join(output, `completion-${id}.png`) });
    await page.locator('[data-celebration-close]').click();
  }
  await page.reload({ waitUntil: 'load' });
  await page.waitForFunction(() => document.documentElement.classList.contains('forest-script-ready'));
  assert.equal(await page.locator('#carrot-balance').textContent(), '180');
  assert.equal(await page.locator('#challenge-celebration').count(), 0);
  assert.deepEqual(errors, []);
  await writeFile(path.join(output, 'browser-check.json'), JSON.stringify({ passed: true, balance, errors, apiRequests: calls.length }, null, 2));
  console.log('Browser wallet check passed: failed save=100, diet=110, activity=120, all=180, reload=180; no page errors.');
} finally {
  await browser?.close();
  await new Promise(resolve => server.close(resolve));
}
