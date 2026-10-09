// icon.svg → прозорий PNG 1024 для DesignCanvas.icns (решта кроків — у коментарі icon.svg).
// Playwright, а не qlmanage: той дає мініатюру з білим тлом і без альфи.
import { chromium } from 'playwright';
import { mkdirSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const svg = readFileSync(new URL('./icon.svg', import.meta.url), 'utf8');
const out = join(process.env.TMPDIR || tmpdir(), 'dc-icon');
mkdirSync(out, { recursive: true });

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1024, height: 1024 } });
await page.setContent(`<style>html,body{margin:0;background:transparent}</style>${svg}`);
await page.locator('svg').screenshot({ path: join(out, 'icon-1024.png'), omitBackground: true });
await browser.close();
console.log(join(out, 'icon-1024.png'));
