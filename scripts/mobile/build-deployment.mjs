import { fileURLToPath } from 'node:url';
import { validateApiOrigin } from '../../src/frontend/mobile/network.mjs';
import { buildMobile } from './build.mjs';

const origin = validateApiOrigin(process.env.MOBILE_API_ORIGIN || 'https://www.dang-no.life');
if (new URL(origin).protocol !== 'https:') throw new Error('Deployment builds require an HTTPS API origin');
process.env.MOBILE_API_ORIGIN = origin;
const result = await buildMobile(fileURLToPath(new URL('../../', import.meta.url)));
console.log(`Deployment mobile bundle: ${origin}, ${result.files} files, ${(result.bytes / 1024 / 1024).toFixed(1)} MiB`);
console.log(result.output);
