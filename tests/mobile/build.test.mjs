import assert from 'node:assert/strict';
import { mkdtemp, mkdir, readFile, rm, writeFile, access } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { buildMobile, rewriteForMobile } from '../../scripts/mobile/build.mjs';

test('maps server page routes while preserving API suffixes, queries and hashes', () => {
  const input = 'href="/forest?demo=1#x"; const profile = `/service?account=profile`; api("/forest/avatar"); api("/api/v1/forest");';
  const output = rewriteForMobile(input);
  assert.match(output, /href="\/static\/forest.html\?demo=1#x"/);
  assert.ok(output.includes('`/static/index.html?account=profile`'));
  assert.ok(output.includes('api("/forest/avatar")'));
  assert.ok(output.includes('api("/api/v1/forest")'));
});

test('disables web service workers in native copies without altering source APIs', () => {
  assert.ok(rewriteForMobile('if ("serviceWorker" in navigator) { register(); }').startsWith('if (false '));
  assert.equal(rewriteForMobile('fetch("/api/v1/health")'), 'fetch("/api/v1/health")');
});

test('packages static assets and route aliases; excludes native projects and private files', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'gandang-mobile-'));
  try {
    const source = path.join(root, 'src/frontend');
    await mkdir(path.join(source, 'assets'), { recursive: true });
    await mkdir(path.join(source, 'native/android'), { recursive: true });
    await mkdir(path.join(root, 'models/artifacts'), { recursive: true });
    const html = '<html><head></head><body><a href="/forest">Forest</a></body></html>';
    await writeFile(path.join(source, 'index.html'), html);
    await writeFile(path.join(source, 'forest.html'), html);
    await writeFile(path.join(source, 'favicon.ico'), 'icon');
    await writeFile(path.join(source, 'forest.webmanifest'), '{"start_url":"/forest"}');
    await writeFile(path.join(source, 'assets/image.png'), Buffer.from([0, 1, 2]));
    await writeFile(path.join(source, 'forest-sw.js'), 'old cache');
    await writeFile(path.join(source, 'forest-art-review-v1.html'), html);
    await writeFile(path.join(source, 'native/android/private.txt'), 'not a web asset');
    await writeFile(path.join(source, '.env'), 'not a web asset');
    await writeFile(path.join(root, 'models/artifacts/model.joblib'), 'not a web asset');
    const { output } = await buildMobile(root);
    assert.equal(await readFile(path.join(source, 'index.html'), 'utf8'), html);
    assert.match(await readFile(path.join(output, 'index.html'), 'utf8'), /\/static\/forest.html/);
    assert.deepEqual(await readFile(path.join(output, 'static/assets/image.png')), Buffer.from([0, 1, 2]));
    assert.equal(JSON.parse(await readFile(path.join(output, 'manifest.webmanifest'), 'utf8')).start_url, '/static/forest.html');
    for (const p of ['static/native', 'static/.env', 'models', 'static/forest-sw.js', 'static/forest-art-review-v1.html']) {
      await assert.rejects(access(path.join(output, p)));
    }
    await writeFile(path.join(output, 'stale.txt'), 'stale');
    await buildMobile(root);
    await assert.rejects(access(path.join(output, 'stale.txt')));
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test('native bundle preserves a contained viewport for fixed game and navigation UI', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'gandang-viewport-'));
  try {
    const source = path.join(root, 'src/frontend');
    await mkdir(path.join(source, 'mobile'), { recursive: true });
    const html = '<html><head><meta name="viewport" content="width=device-width, initial-scale=1"></head><body></body></html>';
    for (const page of ['index.html', 'intro-retro.html', 'forest.html']) await writeFile(path.join(source, page), html);
    await writeFile(path.join(source, 'mobile/runtime.mjs'), 'window.mobileReady = true;');
    await writeFile(path.join(source, 'mobile/mobile.css'), 'body { margin: 0; }');
    await writeFile(path.join(source, 'favicon.ico'), 'icon');
    await writeFile(path.join(source, 'forest.webmanifest'), '{}');
    const { output } = await buildMobile(root);
    for (const page of ['index.html', 'static/index.html', 'static/intro-retro.html', 'static/forest.html']) {
      const bundle = await readFile(path.join(output, page), 'utf8');
      assert.match(bundle, /name="viewport" content="width=device-width, initial-scale=1"/);
      assert.doesNotMatch(bundle, /viewport-fit=cover/);
      assert.match(bundle, /src="\/mobile\/runtime.js"/);
    }
    assert.equal(await readFile(path.join(source, 'index.html'), 'utf8'), html);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test('rejects a missing head before removing an existing bundle', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'gandang-mobile-'));
  try {
    await mkdir(path.join(root, 'src/frontend'), { recursive: true });
    await mkdir(path.join(root, 'dist/mobile'), { recursive: true });
    await writeFile(path.join(root, 'src/frontend/index.html'), '<html></html>');
    await writeFile(path.join(root, 'dist/mobile/keep.txt'), 'keep');
    await assert.rejects(buildMobile(root), /head/);
    assert.equal(await readFile(path.join(root, 'dist/mobile/keep.txt'), 'utf8'), 'keep');
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
