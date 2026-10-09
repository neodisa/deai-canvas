/**
 * БУДІВЕЛЬНІ ЛІСИ, не тест. Знімає всі видимі тексти, `title` і `aria-label`
 * застосунку і друкує відсортованим списком. Сенс один: довести, що витяг
 * рядків у словник НЕ змінив жодного видимого символу.
 *
 *   node tests/live/_text-dump.mjs > /tmp/dc-texts-base.txt     # до витягу
 *   node tests/live/_text-dump.mjs > /tmp/dc-texts-after.txt    # після
 *   diff /tmp/dc-texts-base.txt /tmp/dc-texts-after.txt         # мусить бути порожньо
 *
 * Гілку перемикати НЕ треба: база знімається з цієї ж гілки, поки `app.js` не
 * імпортує `i18n.js` — тобто поки жоден рядок рендера не змінений. Це перевірено
 * (`grep i18n app/app.js` порожній), і саме тому крихкий танець із `git switch`
 * тут зайвий.
 *
 * ⚠️ МЕЖА, знайдена на Task 7: знімок робиться в режимі «Макет», який
 * відкривається типово. Карток «Огляду» (їхні підписи, бейджі, кнопка
 * «Відкрити») у ньому НЕМА взагалі — тобто порожній диф не доводить, що
 * не змінилось у «Огляді». Для тих поверхонь охоронці — живі тести
 * `tests/live/canvas.test.mjs` і `overview-viewports.test.mjs`.
 *
 * Підкреслення в імені тримає файл поза глобом `tests/live/*.test.mjs`, тож у
 * `npm run test:live` він не побіжить.
 *
 * ⚠️ План A передбачав видалити цей файл наприкінці. ЛИШАЄМО, і ось чому:
 * інструмент відпрацював у пʼятьох задачах поспіль, а План B переписує смугу
 * й панель з нуля — тобто саме тоді питання «який видимий текст змінився»
 * коштує найдорожче. Відтворення обійшлось би ще в один цикл на зʼясування
 * API фікстури (`taskFixture` чекає html ФУНКЦІЄЮ і віддає `{dir, it1}`,
 * сервер спиняється `child.kill()`) — це вже виміряно ціною однієї помилки.
 */
import { chromium } from "playwright";

import { startServer, taskFixture } from "./fixture.mjs";

/* `taskFixture` кличе `html(page)` — це функція від імені сторінки, не рядок.
   Сама сторінка тут нецікава: міряємо тексти ОБОЛОНКИ, не макета. */
const PAGE = (id) => `<!DOCTYPE html><html lang="uk"><head><meta charset="utf-8"></head><body><h1>${id}</h1></body></html>`;

const { dir } = taskFixture({ html: PAGE });
const { child, url } = await startServer(dir, { portBase: 8900 });
const browser = await chromium.launch();

try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto(`${url}/app/`);
  /* Селектор оновлено під смугу з трьох зон (План B, Task 2/3): старий
     `.cv-tasksel`/`.cv-err` — це розмітка ДОплановобі смуги, якої в DOM
     більше немає взагалі, тож чекання на неї висіло до таймауту незалежно
     від Task 4. Нові еквіваленти — крошка задачі (`crumb--task`) і смуга
     помилки (`errbar`, `bar-model.js`, поле `error`). */
  await page.waitForSelector("#bar .crumb--task, #bar .errbar");

  const dump = await page.evaluate(() => {
    const out = [];
    for (const el of document.querySelectorAll("*")) {
      const title = el.getAttribute("title");
      if (title && title.trim()) out.push(`TITLE\t${title.trim()}`);
      const aria = el.getAttribute("aria-label");
      if (aria && aria.trim()) out.push(`ARIA\t${aria.trim()}`);
      for (const n of el.childNodes) {
        if (n.nodeType === 3 && n.textContent.trim()) {
          out.push(`TEXT\t${n.textContent.trim().replace(/\s+/g, " ")}`);
        }
      }
    }
    return [...new Set(out)].sort();
  });

  console.log(dump.join("\n"));
} finally {
  await browser.close();
  child.kill();
}
