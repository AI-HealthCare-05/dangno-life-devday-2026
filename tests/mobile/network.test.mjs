
import test from 'node:test';
import assert from 'node:assert/strict';
import { createApiFetch } from '../../src/frontend/mobile/network.mjs';
import { rewriteForMobile } from '../../scripts/mobile/build.mjs';

test('API requests use the configured HTTPS server with refresh cookies', async () => {
  let call;
  const expected = new Response('{}');
  const fetch = createApiFetch(async (...args) => { call = args; return expected; }, 'https://localhost');
  assert.equal(await fetch('/api/v1/auth/token/refresh', { method: 'POST', credentials: 'same-origin' }), expected);
  assert.equal(call[0], 'https://www.dang-no.life/api/v1/auth/token/refresh');
  assert.equal(call[1].credentials, 'include');
  assert.equal(call[1].method, 'POST');
});

test('multipart body, authorization and abort signals are preserved', async () => {
  const body = new FormData(); body.append('file', new Blob(['image']), 'image.jpg');
  const signal = new AbortController().signal;
  const headers = { Authorization: 'Bearer test-only' };
  const iosFetch = createApiFetch(async (url, options) => {
    assert.equal(url, 'https://www.dang-no.life/api/v1/photo?confirmed=true');
    assert.equal(options.body, body); assert.equal(options.signal, signal);
    assert.equal(options.headers, headers);
  }, 'capacitor://localhost');
  await iosFetch('/api/v1/photo?confirmed=true', { method: 'POST', body, headers, signal });
});

test('assets and unrelated hosts pass through without added cookies or retries', async () => {
  let calls = 0;
  const fetch = createApiFetch(async (url, options) => {
    calls++; assert.equal(options, undefined); return new Response('', { status: 503 });
  }, 'https://localhost');
  for (const input of ['/static/image.png', 'https://example.org/api/v1/users', 'https://localhost.evil/api/v1/users']) {
    assert.equal((await fetch(input)).status, 503);
  }
  assert.equal(calls, 3);
});

test('Request objects preserve method and body on rewriting', async () => {
  const input = new Request('https://localhost/api/v1/login', { method: 'POST', body: 'payload', headers: { 'X-Test': 'yes' } });
  const fetch = createApiFetch(async (request, options) => {
    assert.equal(request.url, 'https://www.dang-no.life/api/v1/login');
    assert.equal(request.method, 'POST'); assert.equal(await request.text(), 'payload');
    assert.equal(request.headers.get('X-Test'), 'yes'); assert.equal(options.credentials, 'include');
  }, 'https://localhost');
  await fetch(input);
});

test('bundled prediction previews cannot activate just because origin is localhost', () => {
  const source = 'const isDemoEnvironment = () => ["localhost", "127.0.0.1", "::1"].includes(window.location.hostname);';
  assert.match(rewriteForMobile(source), /=> false/);
});
