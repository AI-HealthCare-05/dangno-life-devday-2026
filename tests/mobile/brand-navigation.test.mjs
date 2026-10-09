import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

test('the brand logo replays the retro intro from both service pages', async () => {
  for (const page of ['index', 'intro-retro']) {
    const html = await readFile(new URL(`../../src/frontend/${page}.html`, import.meta.url), 'utf8');
    assert.match(html, /id="brand-home" href="\/static\/intro-retro\.html\?intro=replay"/);
  }
  for (const script of ['app', 'intro-retro-app']) {
    const js = await readFile(new URL(`../../src/frontend/${script}.js`, import.meta.url), 'utf8');
    assert.doesNotMatch(js, /\$\("#brand-home"\)\.addEventListener\("click"/);
  }
});
