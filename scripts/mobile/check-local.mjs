import assert from 'node:assert/strict';
const pages = await (await fetch('http://127.0.0.1:9222/json/list')).json();
const page = pages.find(page => page.url.startsWith('https://localhost'));
assert.ok(page, 'No Gandang WebView found');
const socket = new WebSocket(page.webSocketDebuggerUrl);
const expression = `(async () => {
  const response = await fetch('/api/v1/health');
  const data = await response.json();
  return { apiOrigin: window.GandangMobile?.apiOrigin, status: response.status, health: data.status };
})()`;
try {
  const result = await new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error('Native API check timed out')), 15000);
    socket.addEventListener('open', () => socket.send(JSON.stringify({ id: 1, method: 'Runtime.evaluate',
      params: { expression, awaitPromise: true, returnByValue: true } })));
    socket.addEventListener('error', () => { clearTimeout(timeout); reject(new Error('WebView debugger connection failed')); });
    socket.addEventListener('message', event => {
      const message = JSON.parse(event.data);
      if (message.id !== 1) return;
      clearTimeout(timeout);
      if (message.error || message.result?.exceptionDetails) reject(new Error('Native API evaluation failed: ' + JSON.stringify(message)));
      else resolve(message.result.result.value);
    });
  });
  assert.equal(result.apiOrigin, 'http://127.0.0.1:8000');
  assert.equal(result.status, 200);
  assert.equal(result.health, 'ok');
  console.log('PASS BlueStacks native fetch -> local server:', JSON.stringify(result));
} finally {
  socket.close();
}
