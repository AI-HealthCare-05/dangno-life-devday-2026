import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { spawnSync } from 'node:child_process';
const email = `smoke-${randomUUID().slice(0, 8)}@example.com`;
const password = `Test!${randomUUID()}`;
const pages = await (await fetch('http://127.0.0.1:9222/json/list')).json();
const page = pages.find(page => page.url.startsWith('https://localhost'));
assert.ok(page, 'No Gandang WebView found');
const socket = new WebSocket(page.webSocketDebuggerUrl);
try {
  const payload = { email, password, terms_agreed: true };
  const expression = `(async () => {
    const response = await fetch('/api/v1/auth/signup', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: ${JSON.stringify(JSON.stringify(payload))}
    });
    const body = await response.json();
    return { status: response.status, userId: body.data?.user_id };
  })()`;
  const result = await new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error('Signup check timed out')), 15000);
    socket.addEventListener('open', () => socket.send(JSON.stringify({ id: 1,
      method: 'Runtime.evaluate', params: { expression, awaitPromise: true, returnByValue: true } })));
    socket.addEventListener('message', event => {
      const message = JSON.parse(event.data);
      if (message.id !== 1) return;
      clearTimeout(timeout);
      if (message.error || message.result?.exceptionDetails) reject(new Error('Signup evaluation failed'));
      else resolve(message.result.result.value);
    });
    socket.addEventListener('error', () => { clearTimeout(timeout); reject(new Error('Debugger connection failed')); });
  });
  // Remove only this randomly generated synthetic account, including on assertion failure.
  const cleanup = spawnSync('.venv/Scripts/python.exe', ['-c',
    'import sqlite3,sys; c=sqlite3.connect("storage/local_mobile.sqlite3"); c.execute("PRAGMA foreign_keys=ON"); c.execute("DELETE FROM users WHERE email=?", (sys.argv[1],)); c.commit(); c.close()', email], { encoding: 'utf8' });
  assert.equal(cleanup.status, 0, 'Synthetic account cleanup failed');
  assert.equal(result.status, 201);
  assert.ok(result.userId);
  console.log('PASS BlueStacks signup: HTTP 201; synthetic account removed');
} finally { socket.close(); }
