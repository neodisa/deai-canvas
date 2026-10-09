// Значки PWA «Deai Canvas»: логотип з `app/logo.js` на темно-шавлієвому тлі →
// `icon-192.png`, `icon-512.png`, `icon-maskable-512.png` поруч із цим файлом.
//
//   node app/pwa/make-icons.mjs
//
// PNG ЗАКОМІЧЕНО в репо: застосунок не збирає їх на льоту, а перезапускати
// генератор треба лише коли міняється логотип чи палітра. Розкладку й кольори
// бере з `icon-spec.mjs` — той самий файл читає тест, тож значок і перевірка не
// розходяться. Той самий прийом, що `ops/canvas-app/render-icon.mjs`: Playwright,
// а не qlmanage (той дає мініатюру з білим тлом і без альфи — а `any` мусить
// мати прозорі кути).
//
// Кожен розмір рендериться НАТИВНО у своєму в'юпорті, а не зменшується з
// більшого: так лінії логотипа лягають на піксельну сітку 192, а не розмиті
// ресемплінгом.
import { chromium } from 'playwright';
import { fileURLToPath } from 'node:url';
import { join } from 'node:path';

import { LOGO_SVG } from '../logo.js';
import { ICON_FILES, PALETTE, layoutOf } from './icon-spec.mjs';

const OUT = fileURLToPath(new URL('.', import.meta.url));

// `LOGO_SVG` несе `width="20" height="20"` і колір через змінні смуги (`currentColor`
// рамки, `var(--logo-in)` прямокутника). Розмір перекриває CSS (він сильніший за
// атрибут представлення), кольори задаються тут — розмітку логотипа НЕ копіюємо.
const page = (L) => `<style>
  :root{--logo-in:${PALETTE.inner}}
  html,body{margin:0;background:transparent}
  .tile{width:100vw;height:100vh;background:${PALETTE.bg};border-radius:${L.radius}px;
        display:grid;place-items:center;color:${PALETTE.frame}}
  .tile svg{width:${L.logo}px;height:${L.logo}px}
</style><div class="tile">${LOGO_SVG}</div>`;

const browser = await chromium.launch();
for (const { file, size, purpose } of ICON_FILES) {
  const ctx = await browser.newContext({ viewport: { width: size, height: size }, deviceScaleFactor: 1 });
  const p = await ctx.newPage();
  await p.setContent(page(layoutOf(size, purpose)));
  // `omitBackground` — прозорі кути `any`; у `maskable` кутів нема (радіус 0).
  await p.screenshot({ path: join(OUT, file), omitBackground: true });
  await ctx.close();
  console.log(join(OUT, file));
}
await browser.close();
