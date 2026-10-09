import test from 'node:test';
import assert from 'node:assert/strict';
import { handleAppBack } from '../../src/frontend/mobile/back-navigation.mjs';

function context() {
  const events = [];
  return { events, document: { querySelectorAll: () => [], querySelector: () => null,
    getElementById: () => null, documentElement: { classList: { contains: () => false } } },
    window: { history: { back: () => events.push('previous-page') } },
    app: { minimizeApp: async () => events.push('minimize') }, canGoBack: true };
}
test('returns to the previous internal view before leaving the page', () => {
  const c = context(); c.window.GandangPageBack = () => { c.events.push('previous-view'); return true; };
  handleAppBack(c); assert.deepEqual(c.events, ['previous-view']);
});
test('returns through browser history when no internal view remains', () => {
  const c = context(); c.window.GandangPageBack = () => false;
  handleAppBack(c); assert.deepEqual(c.events, ['previous-page']);
});
test('closing an open modal takes priority over leaving the screen', () => {
  const c = context(); c.document.querySelectorAll = selector => selector === 'dialog[open]'
    ? [{ querySelector: () => ({ click: () => c.events.push('close') }) }] : [];
  handleAppBack(c); assert.deepEqual(c.events, ['close']);
});
test('only minimizes when there is no previous view or page', () => {
  const c = context(); c.canGoBack = false; handleAppBack(c);
  assert.deepEqual(c.events, ['minimize']);
});
