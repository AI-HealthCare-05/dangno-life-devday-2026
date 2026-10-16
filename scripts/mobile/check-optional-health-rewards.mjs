// Browser + real reward API, with a synthetic user and isolated memory database.
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdir, writeFile } from 'node:fs/promises';
import net from 'node:net';
import path from 'node:path';
import { chromium } from 'playwright';

const root = process.cwd();
const out = path.join(root, 'outputs/mobile/optional-health-rewards');
await mkdir(out, { recursive: true });
const socket = net.createServer();
await new Promise(resolve => socket.listen(0, '127.0.0.1', resolve));
const port = socket.address().port;
await new Promise(resolve => socket.close(resolve));
const base = `http://127.0.0.1:${port}`;
const python = path.join(root, 'outputs/python/official-sqlite-3.13.15/python.exe');
const bootstrap = `import site,sys,os;site.addsitedir('.venv/Lib/site-packages');sys.path.insert(0,os.getcwd());import uvicorn;uvicorn.run('tests.fixtures.optional_health_reward_app:app',host='127.0.0.1',port=${port},log_level='warning')`;
const child = spawn(python, ['-c', bootstrap], { cwd: root, windowsHide: true,
  env: { ...process.env, ENV: 'local', DEMO_MODE: 'false', DATABASE_URL: 'sqlite://:memory:',
    SECRET_KEY: 'browser-optional-reward-test-only', OPENAI_API_KEY: '', PYTHONIOENCODING: 'utf-8' } });
let log = ''; child.stdout.on('data', data => { log += data; }); child.stderr.on('data', data => { log += data; });
let browser;
const errors = [];
try {
  let ready = false;
  for (let index = 0; index < 120; index++) {
    try { if ((await fetch(`${base}/fixture`)).ok) { ready = true; break; } } catch {}
    if (child.exitCode != null) break;
    await new Promise(resolve => setTimeout(resolve, 150));
  }
  assert.ok(ready, log || 'Isolated API did not start');
  browser = await chromium.launch({ headless: true,
    ...(process.env.MOBILE_TEST_BROWSER ? { executablePath: process.env.MOBILE_TEST_BROWSER } : {}) });
  const page = await browser.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1 });
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/*', route => route.request().url().startsWith(base) ? route.continue() : route.abort());
  async function open() {
    await page.goto(base, { waitUntil: 'networkidle' });
    await page.evaluate(async () => {
      document.body.className = '';
      document.querySelectorAll('.screen').forEach(el => el.classList.toggle('active', el.dataset.step === '4'));
      window.fixtureApi = async (url, options) => {
        const response = await fetch('/api/v1' + url, { ...options,
          headers: options?.body ? { 'Content-Type': 'application/json' } : {} });
        const result = await response.json();
        if (!response.ok) throw Object.assign(new Error(JSON.stringify(result.detail)), { status: response.status });
        return result.data;
      };
      const owner = await (await fetch('/fixture')).json();
      window.fixtureOwner = owner.user_id;
      await HealthInputRewards.refreshStatus({ api: fixtureApi, ownerId: owner.user_id });
    });
  }
  await open();
  const waist = page.locator('#waist');
  assert.equal(await waist.inputValue(), '');
  await waist.scrollIntoViewIfNeeded();
  const carrotAsset = await page.request.get(`${base}/static/assets/optional-health-carrot-shared.png`);
  assert.equal(carrotAsset.status(), 200);
  assert.equal(carrotAsset.headers()['content-type'], 'image/png');
  const { createHash } = await import('node:crypto');
  assert.equal(createHash('sha256').update(await carrotAsset.body()).digest('hex'),
    '905cf40fd2c9390e12d4aed8a5a2c7d7a45aba237460bdb00f689717f5d72214');
  await page.evaluate(async () => {
    const img = new Image(); img.src = '/static/assets/optional-health-carrot-shared.png';
    await img.decode();
  });
  await page.screenshot({ path: path.join(out, 'empty-horizontal-carrot.png') });
  await waist.locator('..').screenshot({ path: path.join(out, 'shared-carrot-input.png') });
  await waist.locator('..').locator('button').click();
  const dialog = page.locator('.optional-reward-hint');
  await dialog.waitFor({ state: 'visible' });
  assert.match(await dialog.innerText(), /더 많은 건강정보를 입력하고, 더 높은 예측 결과를 받아보세요\. 당근의 숲에서 사용할 수 있는 당근 100개는 덤!/);
  const hintBox = await dialog.boundingBox();
  assert.ok(hintBox.x >= 0 && hintBox.y >= 0 && hintBox.x + hintBox.width <= 390 && hintBox.y + hintBox.height <= 844);
  await page.screenshot({ path: path.join(out, 'first-carrot-hint.png') });
  await dialog.getByRole('button').click();
  await waist.fill('90');
  await page.waitForFunction(() => getComputedStyle(document.getElementById('waist')).backgroundColor === 'rgb(255, 223, 174)');
  assert.equal(await waist.evaluate(el => getComputedStyle(el).backgroundColor), 'rgb(255, 223, 174)');
  await page.locator('#health-form').screenshot({ path: path.join(out, 'optional-field-orange.png') });
  await page.evaluate(() => {
    document.getElementById('health-metrics-panel').hidden = true;
    document.getElementById('health-vitals-panel').hidden = false;
  });
  await page.locator('#systolic').locator('..').locator('button').click();
  assert.equal(await page.locator('dialog[open]').count(), 0);
  await page.locator('#systolic').fill('120');
  await page.locator('#diastolic').fill('80');
  assert.match(await page.locator('.optional-reward-preview').innerText(), /3개 입력.*300개/);
  const saved = await page.evaluate(async () => {
    const record = await fixtureApi('/health-checkups', { method: 'POST', body: JSON.stringify({
      checkup_date: '2026-10-15', height_cm: Number(document.getElementById('height').value),
      weight_kg: Number(document.getElementById('weight').value),
      waist_cm: Number(document.getElementById('waist').value),
      systolic_bp: Number(document.getElementById('systolic').value),
      diastolic_bp: Number(document.getElementById('diastolic').value),
      smoking_status: 'never', regular_exercise: false, current_drinker: false,
      exercise_days_per_week: 0, exercise_minutes: 0,
    }) });
    const current = await fixtureApi('/current-screening-inputs', { method: 'POST', body: JSON.stringify({
      health_checkup_id: record.checkup_id, input_as_of_date: '2026-10-15', alcohol_frequency: 1,
    }) });
    document.querySelectorAll('.screen').forEach(el => el.classList.toggle('active', el.dataset.step === '5'));
    window.scrollTo(0, 0);
    const result = await HealthInputRewards.claim({ api: fixtureApi, ownerId: fixtureOwner,
      checkupId: record.checkup_id, inputId: current.current_screening_input_id });
    return { record, current, result };
  });
  assert.equal(saved.result.earned_carrots, 300);
  assert.equal(saved.result.carrot_balance, 400);
  const summary = page.locator('#optional-health-reward-summary');
  await summary.scrollIntoViewIfNeeded();
  assert.match(await summary.innerText(), /당근 300개를 획득/);
  assert.equal(await summary.locator('li').count(), 3);
  const summaryBox = await summary.boundingBox();
  assert.ok(summaryBox.x >= 0 && summaryBox.x + summaryBox.width <= 390);
  const titleBox = await summary.locator('h3').boundingBox();
  assert.ok(titleBox.y >= 0 && titleBox.y + titleBox.height <= 844);
  await page.screenshot({ path: path.join(out, 'analysis-earned-300.png') });
  await summary.locator('summary').click();
  await page.screenshot({ path: path.join(out, 'analysis-earned-details.png') });
  await open();
  const repeated = await page.evaluate(async saved => {
    document.querySelectorAll('.screen').forEach(el => el.classList.toggle('active', el.dataset.step === '5'));
    return await HealthInputRewards.claim({ api: fixtureApi, ownerId: fixtureOwner,
      checkupId: saved.record.checkup_id, inputId: saved.current.current_screening_input_id });
  }, saved);
  assert.equal(repeated.earned_carrots, 0);
  assert.equal(repeated.checkup_reward_carrots, 300);
  assert.equal(repeated.carrot_balance, 400);
  assert.deepEqual(errors, []);
  await writeFile(path.join(out, 'browser-check.json'), JSON.stringify({ passed: true,
    earnedCarrots: 300, balance: 400, afterReloadEarned: 0, afterReloadBalance: 400, errors }, null, 2));
  console.log('Browser + real isolated API passed: 3 fields = 300, wallet = 400 including welcome; reload = 0 additional.');
} finally {
  await browser?.close();
  child.kill();
}
