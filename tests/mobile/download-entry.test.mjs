import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const source = fs.readFileSync(new URL('../../src/frontend/mobile-download-entry.js', import.meta.url), 'utf8');
test('native app hides the web download route while web users retain the server download page', () => {
  for (const native of [true, false]) {
    const item = { hidden: false };
    let callback, destination;
    const button = { closest: () => item, addEventListener: (_, handler) => { callback = handler; } };
    vm.runInNewContext(source, {
      document: { querySelectorAll: () => [button] },
      window: { Capacitor: { isNativePlatform: () => native }, location: { assign: url => { destination = url; } } },
    });
    assert.equal(item.hidden, native);
    if (native) assert.equal(callback, undefined);
    else { callback(); assert.equal(destination, '/mobile-downloads'); }
  }
});
