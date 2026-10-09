import assert from 'node:assert/strict';
import test from 'node:test';
import { validateApiOrigin } from '../../src/frontend/mobile/network.mjs';

test('local API permits only loopback HTTP or clean HTTPS origins', () => {
  assert.equal(validateApiOrigin('http://127.0.0.1:8000'), 'http://127.0.0.1:8000');
  assert.equal(validateApiOrigin('https://dang-no.life/'), 'https://dang-no.life');
  for (const url of ['http://192.168.1.2:8000', 'http://example.org', 'https://user:pass@example.org',
    'https://example.org/api', 'https://example.org/?token=test', 'file:///private']) {
    assert.throws(() => validateApiOrigin(url));
  }
});
