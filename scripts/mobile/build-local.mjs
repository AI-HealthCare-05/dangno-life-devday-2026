process.env.MOBILE_API_ORIGIN = 'http://127.0.0.1:8000';
const { buildMobile } = await import('./build.mjs');
const { fileURLToPath } = await import('node:url');
const result = await buildMobile(fileURLToPath(new URL('../../', import.meta.url)));
console.log('Local mobile bundle:', result.output);
