import { readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

const configPath = fileURLToPath(new URL('../../src/frontend/native/ios/App/App/capacitor.config.json', import.meta.url));
const config = JSON.parse(await readFile(configPath, 'utf8'));
const port = Number(process.env.MOBILE_DEV_PORT || 4173);
if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error('Invalid MOBILE_DEV_PORT');
config.server = { ...config.server, url: `http://127.0.0.1:${port}` };
await writeFile(configPath, `${JSON.stringify(config, null, 2)}\n`);
console.log(`Xcode development app will load http://127.0.0.1:${port}`);
console.log('Select an iOS simulator and press Run in Xcode. Use pnpm sync:ios to restore the bundled app afterward.');
