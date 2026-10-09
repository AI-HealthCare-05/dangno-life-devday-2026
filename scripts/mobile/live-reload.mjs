import { createReadStream } from 'node:fs';
import { access, copyFile, stat } from 'node:fs/promises';
import { watch } from 'node:fs';
import { createServer } from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { buildMobile } from './build.mjs';

const root = fileURLToPath(new URL('../../', import.meta.url));
const source = path.join(root, 'src/frontend');
const output = path.join(root, 'dist/mobile');
const host = process.env.MOBILE_DEV_HOST || '127.0.0.1';
const port = Number(process.env.MOBILE_DEV_PORT || 4173);
const cssFiles = new Map([
  ['mobile/mobile.css', 'mobile/mobile.css'],
  ['mobile/ios.css', 'mobile/ios.css'],
  ['styles.css', 'static/styles.css'],
  ['navigation.css', 'static/navigation.css'],
]);
const clients = new Set();
const mime = { '.css': 'text/css', '.html': 'text/html', '.js': 'text/javascript',
  '.json': 'application/json', '.svg': 'image/svg+xml', '.png': 'image/png',
  '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp',
  '.ico': 'image/x-icon', '.woff': 'font/woff', '.woff2': 'font/woff2',
  '.mp3': 'audio/mpeg', '.wav': 'audio/wav' };
const reloadScript = `<script>(function(){
  var events = new EventSource('/__mobile_live_reload');
  events.onmessage = function(){
    document.querySelectorAll('link[rel="stylesheet"]').forEach(function(link){
      var url = new URL(link.href, location.href);
      if (url.origin === location.origin) {
        url.searchParams.set('__live', Date.now());
        link.href = url.href;
      }
    });
  };
})();</script>`;

await buildMobile(root);
const server = createServer(async (req, res) => {
  if (req.url?.split('?')[0] === '/__mobile_live_reload') {
    res.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-store',
      Connection: 'keep-alive' });
    res.write(': connected\n\n');
    clients.add(res);
    req.on('close', () => clients.delete(res));
    return;
  }
  try {
    const pathname = decodeURIComponent(new URL(req.url || '/', `http://${host}`).pathname);
    if (pathname === '/mobile/ios.css' || pathname === '/mobile/mobile.css') {
      console.log(`Serving ${pathname}`);
    }
    const target = path.resolve(output, `.${pathname === '/' ? '/index.html' : pathname}`);
    if (!target.startsWith(output + path.sep)) throw new Error('Invalid path');
    const info = await stat(target);
    if (!info.isFile()) throw new Error('Not a file');
    const extension = path.extname(target).toLowerCase();
    res.setHeader('Content-Type', `${mime[extension] || 'application/octet-stream'}${['.html', '.css', '.js', '.json'].includes(extension) ? '; charset=utf-8' : ''}`);
    res.setHeader('Cache-Control', 'no-store');
    if (extension === '.html') {
      const { readFile } = await import('node:fs/promises');
      const html = await readFile(target, 'utf8');
      res.end(html.replace(/<\/head>/i, `${reloadScript}</head>`));
    } else {
      createReadStream(target).pipe(res);
    }
  } catch {
    res.writeHead(404);
    res.end('Not found');
  }
});

server.listen(port, host, () => {
  console.log(`iOS CSS live reload: http://${host}:${port}`);
  console.log('Keep this terminal open. After pnpm sync:ios and pnpm dev:ios:connect, press Run in Xcode.');
});

for (const [input, destination] of cssFiles) {
  const file = path.join(source, input);
  if (!(await access(file).then(() => true, () => false))) continue;
  let timer;
  const watcher = watch(file, () => {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      try {
        await copyFile(file, path.join(output, destination));
        for (const client of clients) client.write('data: css\n\n');
        console.log(`Updated ${input}`);
      } catch (error) {
        console.error(`Could not update ${input}:`, error);
      }
    }, 100);
  });
  watcher.on('error', error => console.error(`Watch error for ${input}:`, error));
}
