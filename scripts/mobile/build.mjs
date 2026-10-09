import { access, cp, mkdir, readFile, readdir, rm, stat, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { validateApiOrigin } from '../../src/frontend/mobile/network.mjs';

const ROUTES = { forest: '/static/forest.html', service: '/static/index.html' };
const TEXT_EXTENSIONS = new Set(['.html', '.js', '.css', '.json', '.webmanifest']);
const ROOT_EXTENSIONS = new Set(['.html', '.js', '.css', '.ico', '.webmanifest']);
const STATIC_DIRECTORIES = new Set(['assets', 'icons', 'suin', 'vendor']);

// Translate only exact page-route literals. /forest/avatar is an API suffix.
export function rewriteForMobile(text) {
  return text
    .replace(/(<meta\s+name=["']viewport["']\s+content=["'])([^"']*)(["'])/i, (_, start, content, end) => {
      const values = content.split(',').map(value => value.trim()).filter(Boolean);
      if (!values.some(value => value.startsWith('viewport-fit='))) values.push('viewport-fit=cover');
      return start + values.join(', ') + end;
    })
    .replace(/(["'`])\/(forest|service)(?=["'`?#])/g, (_, quote, route) => quote + ROUTES[route])
    .replace(/\["localhost", "127\.0\.0\.1", "::1"\]\.includes\(window\.location\.hostname\)/g, 'false /* native: no prediction demo */')
    .replace(/\["127\.0\.0\.1", "localhost"\]\.includes\(window\.location\.hostname\)/g, 'false /* native: no reset demo */')
    .replace(/(["'])serviceWorker\1\s+in\s+navigator/g, 'false /* assets are bundled in the native app */');
}

export async function buildMobile(root) {
  const apiOrigin = validateApiOrigin(process.env.MOBILE_API_ORIGIN || 'https://www.dang-no.life');
  const repo = path.resolve(root);
  const source = path.join(repo, 'src/frontend');
  const output = path.join(repo, 'dist/mobile');
  // Only this generated directory may be replaced; never delete the web source.
  if (path.relative(repo, output).split(path.sep).join('/') !== 'dist/mobile') {
    throw new Error('Unsafe mobile output directory');
  }
  const entry = await readFile(path.join(source, 'index.html'), 'utf8');
  if (!/<head(?:\s[^>]*)?>/i.test(entry)) throw new Error('index.html requires a head element');
  await rm(output, { recursive: true, force: true });
  await mkdir(path.join(output, 'static'), { recursive: true });
  const runtime = path.join(source, 'mobile/runtime.mjs');
  const hasRuntime = await access(runtime).then(() => true, () => false);
  let files = 0;
  let bytes = 0;
  async function copyFile(from, to) {
    await mkdir(path.dirname(to), { recursive: true });
    if (TEXT_EXTENSIONS.has(path.extname(from))) {
      let data = rewriteForMobile(await readFile(from, 'utf8'));
      if (hasRuntime && path.extname(from) === '.html') {
        data = data.replace(/<head(?:\s[^>]*)?>/i, head => head + '<script src="/mobile/runtime.js"></script>');
        // Runtime marks iOS before this executes; load exactly one native stylesheet
        // after the page styles so platform overrides keep their precedence.
        data = data.replace(/<\/head>/i, `<script>
          { const style = document.createElement('link');
            style.rel = 'stylesheet';
            style.href = document.documentElement.classList.contains('gandang-ios')
              ? '/mobile/ios.css' : '/mobile/mobile.css';
            document.head.append(style); }
        </script></head>`);
        // Native pages opt into viewport-fit=cover so CSS env(safe-area-inset-*) values
        // are available around the iOS status bar, notch and home indicator.
      }
      await writeFile(to, data);
      bytes += Buffer.byteLength(data);
    } else {
      await cp(from, to);
      bytes += (await stat(from)).size;
    }
    files += 1;
  }
  async function copyDirectory(from, to) {
    for (const item of await readdir(from, { withFileTypes: true })) {
      if (item.isSymbolicLink()) throw new Error(`Symlink cannot be packaged: ${item.name}`);
      if (item.name.startsWith('.')) continue;
      const src = path.join(from, item.name), dst = path.join(to, item.name);
      if (item.isDirectory()) await copyDirectory(src, dst);
      else if (item.isFile()) await copyFile(src, dst);
    }
  }
  for (const item of await readdir(source, { withFileTypes: true })) {
    if (item.isSymbolicLink()) throw new Error(`Symlink cannot be packaged: ${item.name}`);
    if (item.isDirectory() && STATIC_DIRECTORIES.has(item.name)) {
      await copyDirectory(path.join(source, item.name), path.join(output, 'static', item.name));
    } else if (item.isFile() && ROOT_EXTENSIONS.has(path.extname(item.name)) &&
               !item.name.includes('-review-') && item.name !== 'forest-sw.js') {
      await copyFile(path.join(source, item.name), path.join(output, 'static', item.name));
    }
  }
  await copyFile(path.join(source, 'index.html'), path.join(output, 'index.html'));
  await copyFile(path.join(source, 'favicon.ico'), path.join(output, 'favicon.ico'));
  await copyFile(path.join(source, 'forest.webmanifest'), path.join(output, 'manifest.webmanifest'));
  if (hasRuntime) {
    const { build } = await import('esbuild');
    await build({ entryPoints: [runtime], bundle: true, format: 'iife', target: ['chrome100', 'safari15'],
      define: { __MOBILE_API_ORIGIN__: JSON.stringify(apiOrigin) }, outfile: path.join(output, 'mobile/runtime.js') });
    await cp(path.join(source, 'mobile/mobile.css'), path.join(output, 'mobile/mobile.css'));
    await cp(path.join(source, 'mobile/ios.css'), path.join(output, 'mobile/ios.css'));
    files += 3;
    bytes += (await stat(path.join(output, 'mobile/runtime.js'))).size +
      (await stat(path.join(output, 'mobile/mobile.css'))).size +
      (await stat(path.join(output, 'mobile/ios.css'))).size;
  }
  return { files, bytes, output };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const root = fileURLToPath(new URL('../../', import.meta.url));
  const result = await buildMobile(root);
  console.log(`Mobile bundle: ${result.files} files, ${(result.bytes / 1024 / 1024).toFixed(1)} MiB`);
  console.log(result.output);
}
