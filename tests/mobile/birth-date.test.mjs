import assert from 'node:assert/strict';
import test from 'node:test';
import { normalizeBirthDate } from '../../src/frontend/mobile/birth-date.mjs';

test('accepts numeric and Korean-style birth dates as API ISO dates', () => {
  assert.equal(normalizeBirthDate('19711009'), '1971-10-09');
  assert.equal(normalizeBirthDate('1971. 10. 9.'), '1971-10-09');
  assert.equal(normalizeBirthDate('1934년 2월 28일'), '1934-02-28');
  assert.equal(normalizeBirthDate('2000-02-29'), '2000-02-29');
});

test('rejects incomplete and impossible dates', () => {
  for (const value of ['', '1971109', '1934-02-29', '2000-13-01', '2000-00-10', '2001-04-31', 'abcd']) {
    assert.equal(normalizeBirthDate(value), null, value);
  }
});
